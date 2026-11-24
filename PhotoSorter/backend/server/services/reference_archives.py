"""Atomic, cached ZIP export of the currently published reference library.

Only immutable version members are exported; the mutable gallery, staged imports
and historical versions are not sources of truth for downloads.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from app.config import DATA_DIR
from ..database import connect
from ..db.repositories import reference_versions
from ..storage import reference_objects
from ..storage.paths import owned_directory, owned_file
from . import archives, archive_cache
from .archive_layout import _unique, portable_name
from .construction_catalog import construction_title

EXPORTS = DATA_DIR / "reference_exports"


@dataclass(frozen=True)
class ReferenceExport:
    version: int
    key: str
    files: list[tuple[Path, str, int]]


def build_plan(version, members, constructions) -> ReferenceExport:
    """Build portable names with collision handling, without touching a live gallery."""
    if not members:
        raise HTTPException(404, "В библиотеке нет готовых образцов")
    titles = {
        item["sam"]: construction_title(item["sam"], item["kind"], item["address"])
        for item in constructions
    }
    groups = defaultdict(list)
    for item in members:
        if item["source_kind"] != "staged":
            raise HTTPException(409, "В библиотеке найден неподдерживаемый образец")
        source = Path(item["target_path"])
        try:
            reference_objects.verify(source, reference_objects.ROOT, item["declared_size"])
        except (OSError, ValueError) as exc:
            raise HTTPException(409, "Не удалось прочитать один из опубликованных образцов") from exc
        groups[item["sam"]].append((source, item))
    labels = sorted(groups)
    directories = dict(zip(labels, _unique(
        [portable_name(titles.get(sam, sam), "Конструкция") for sam in labels]
    )))
    files = []
    identity = []
    for sam in labels:
        photos = groups[sam]
        names = list(_unique([
            portable_name(item["filename"], "Образец", file=True)
            for _, item in photos
        ], file=True))
        for (source, item), name in zip(photos, names):
            member = archives.archive_member(directories[sam], name)
            files.append((source, member, item["declared_size"]))
            identity.append((str(item["reference_id"]), item["source_hash"], member))
    fingerprint = hashlib.sha256(json.dumps(
        [str(version["id"]), version["manifest_digest"], identity],
        ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return ReferenceExport(int(version["version_number"]), fingerprint, files)


def current_plan() -> ReferenceExport:
    with connect() as db:
        version = reference_versions.current(db)
        if not version or version["id"] is None:
            raise HTTPException(409, "Библиотека образцов ещё не инициализирована")
        members = reference_versions.members(db, version["id"])
        labels = sorted({row["sam"] for row in members})
        constructions = db.execute(
            "SELECT sam,kind,address FROM reference_constructions WHERE sam=ANY(%s)",
            (labels,)
        ).fetchall() if labels else []
    return build_plan(version, members, constructions)


def prepare(plan: ReferenceExport) -> Path:
    """Build once under a file lock, then publish only a complete, validated ZIP."""
    if EXPORTS.is_symlink():
        raise HTTPException(409, "Небезопасный каталог ZIP образцов")
    EXPORTS.mkdir(parents=True, exist_ok=True)
    directory = owned_directory(EXPORTS, EXPORTS.parent)
    target = directory / (plan.key + ".zip")
    lock = directory / (plan.key + ".lock")
    if lock.is_symlink() or target.is_symlink():
        raise HTTPException(409, "Небезопасный путь ZIP образцов")
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with archive_cache.pin(directory), os.fdopen(descriptor, "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if target.exists():
                owned_file(target, directory)
                if zipfile.is_zipfile(target):
                    return target
                target.unlink()
            # ZIP_STORED needs almost as much free space as the source images.
            with archive_cache.build_space(EXPORTS.parent,sum(size for _, _, size in plan.files)+1024*1024+len(plan.files)*2048):
                return _build(plan,target,directory)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise HTTPException(507, "Недостаточно места для ZIP образцов") from exc
            raise
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _build(plan,target,directory):
    fd, temporary = tempfile.mkstemp(prefix=".references-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as output:
            with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED,
                                 allowZip64=True) as archive:
                for source, name, size in plan.files:
                    reference_objects.verify(source, reference_objects.ROOT, size)
                    archive.write(source, arcname=name, compress_type=zipfile.ZIP_STORED)
            output.flush()
            os.fsync(output.fileno())
        with zipfile.ZipFile(temporary) as archive:
            if len(archive.infolist()) != len(plan.files) or archive.testzip() is not None:
                raise OSError("Проверка целостности ZIP образцов не пройдена")
        os.chmod(temporary, 0o444)
        os.replace(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)
