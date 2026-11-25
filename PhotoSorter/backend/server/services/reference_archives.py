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
from app.storage.changes import changed
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from app import config
from app.storage.categories import Category
from app.storage.paths import managed_path,managed_prefix
from app.storage.filesystem import directory_fd
from ..database import connect
from ..db.repositories import reference_versions
from ..storage import reference_objects
from ..storage.paths import owned_directory, owned_file
from . import archives, archive_cache
from .archive_layout import _unique, portable_name
from .construction_catalog import construction_title
from .reference_sides import SIDES

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA = "map-reference-library-v1"
UNASSIGNED = "Неназначенные"

def export_folder():
    return managed_prefix(Category.ZIP_REFERENCES)


@dataclass(frozen=True)
class ReferenceExport:
    version: int
    key: str
    files: list[tuple[Path, str, int]]
    manifest: bytes


def build_plan(version, members, constructions, sides=None) -> ReferenceExport:
    """Portable, deterministic export of a single published library snapshot."""
    if not members:
        raise HTTPException(404, "В библиотеке нет готовых образцов")
    sides = sides or {}
    catalog = {item["sam"]: dict(item) for item in constructions}
    groups = defaultdict(list)
    for item in members:
        if item["source_kind"] != "staged":
            raise HTTPException(409, "В библиотеке найден неподдерживаемый образец")
        source = Path(item["target_path"])
        try:
            reference_objects.verify_object(source,item["declared_size"],digest=item["source_hash"])
        except (OSError, ValueError) as exc:
            raise HTTPException(409, "Не удалось прочитать один из опубликованных образцов") from exc
        groups[item["sam"]].append((source, item))
    labels = sorted(set(groups) | set(catalog))
    directories = dict(zip(labels, _unique([
        portable_name(construction_title(sam, catalog.get(sam, {}).get("kind", "standard"),
                                       catalog.get(sam, {}).get("address")), "Конструкция")
        for sam in labels
    ])))
    # Reserve the manifest basename even for a custom construction with that name.
    directories = dict(zip(labels, list(_unique([MANIFEST_NAME] + list(directories.values())))[1:]))
    records = []
    files = []
    for sam in labels:
        side_groups = defaultdict(list)
        for source,item in groups[sam]:
            side_groups[sides.get(str(item["reference_id"]))].append((source,item))
        # Keep exact historical labels in the manifest; never silently clear them.
        # Reserve all supported labels and the unassigned name before allocating
        # a portable folder for a nonstandard historical label.
        standard = [None, *sorted(SIDES)]
        reserved = [UNASSIGNED, *sorted(SIDES)]
        legacy = sorted(side for side in side_groups if side not in standard)
        legacy_folders = list(_unique(reserved + [
            portable_name("Историческая сторона — " + side, "Историческая сторона")
            for side in legacy
        ]))[len(reserved):]
        side_dirs = dict(zip(standard + legacy, reserved + legacy_folders))
        for side in sorted(side_groups, key=lambda value:(value is not None, value or "")):
            photos = sorted(side_groups[side], key=lambda pair:str(pair[1]["reference_id"]))
            names = _unique([portable_name(item["filename"], "Образец", file=True)
                             for _,item in photos], file=True)
            for (source,item),name in zip(photos,names):
                member = archives.archive_member(directories[sam],side_dirs[side]) + "/" + name
                # Validate all path components, including the filename.
                archives.archive_member(side_dirs[side],name)
                files.append((source,member,item["declared_size"]))
                records.append({"path":member,"sam":sam,"filename":item["filename"],
                                "sha256":item["source_hash"],"size":item["declared_size"],"side":side})
    manifest = json.dumps({
        "schema":MANIFEST_SCHEMA,
        "library_version":int(version["version_number"]),
        "constructions":[{
            "sam":sam,"directory":directories[sam],
            "kind":catalog.get(sam,{}).get("kind","standard"),
            "city_code":catalog.get(sam,{}).get("city_code"),
            "number":catalog.get(sam,{}).get("construction_number"),
            "address":catalog.get(sam,{}).get("address")
        } for sam in labels],
        "photos":records
    },ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    fingerprint = hashlib.sha256(manifest).hexdigest()
    return ReferenceExport(int(version["version_number"]), fingerprint, files, manifest)


def current_plan() -> ReferenceExport:
    with connect() as db:
        # The HTTP caller already holds a ReadPin. Do not take the FIFO lock:
        # GC takes locks in the reverse order. A repeatable-read snapshot keeps
        # members, construction names and mutable side metadata consistent.
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        version = reference_versions.current(db)
        if not version or version["id"] is None:
            raise HTTPException(409, "Библиотека образцов ещё не инициализирована")
        members = reference_versions.members(db, version["id"])
        constructions = db.execute(
            "SELECT sam,kind,city_code,construction_number,address FROM reference_constructions ORDER BY sam"
        ).fetchall()
        ids = [row["reference_id"] for row in members]
        sides = {str(row["reference_id"]):row["side"] for row in db.execute(
            "SELECT reference_id,side FROM reference_photo_sides WHERE reference_id=ANY(%s)",(ids,)
        ).fetchall()} if ids else {}
    return build_plan(version, members, constructions, sides)


def prepare(plan: ReferenceExport) -> Path:
    """Build once under a file lock, then publish only a complete, validated ZIP."""
    folder=export_folder()
    if folder.is_symlink():
        raise HTTPException(409, "Небезопасный каталог ZIP образцов")
    with directory_fd(config.APP_STORAGE_ROOT,folder.relative_to(config.APP_STORAGE_ROOT),create=True):pass
    directory = owned_directory(folder, config.APP_STORAGE_ROOT)
    target = managed_path(Category.ZIP_REFERENCES,cache_key=plan.key)
    lock = directory / (plan.key + ".lock")
    if lock.is_symlink() or target.is_symlink():
        raise HTTPException(409, "Небезопасный путь ZIP образцов")
    with archive_cache.pin(directory), os.fdopen(os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if target.exists():
                owned_file(target, directory)
                if archive_cache.fresh(target) and zipfile.is_zipfile(target):
                    return target
                # Preserve the previous inode until publication succeeds.
            # ZIP_STORED needs almost as much free space as the source images.
            with archive_cache.build_space(config.APP_STORAGE_ROOT,sum(size+2*len(name.encode("utf8"))+512 for _,name,size in plan.files)+len(plan.manifest)+1024*1024) as lease:
                return _build(plan,target,directory,lease=lease)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise HTTPException(507, "Недостаточно места для ZIP образцов") from exc
            raise
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _build(plan,target,directory,*,lease=None):
    fd, temporary = tempfile.mkstemp(prefix=".references-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as output:
            if lease:
                lease.track(Path(temporary));lease.publish(target)
                from ..storage.bounded import BoundedWriter
                output=BoundedWriter(output,lease.limit)
            with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED,
                                 allowZip64=True) as archive:
                for source, name, size in plan.files:
                    reference_objects.verify_object(source,size,digest=source.name)
                    archive.write(source, arcname=name, compress_type=zipfile.ZIP_STORED)
                archive.writestr(MANIFEST_NAME, plan.manifest, compress_type=zipfile.ZIP_STORED)
            output.flush()
            os.fsync(output.fileno())
        with zipfile.ZipFile(temporary) as archive:
            if (len(archive.infolist()) != len(plan.files)+1 or archive.testzip() is not None
                    or archive.read(MANIFEST_NAME) != plan.manifest):
                raise OSError("Проверка целостности ZIP образцов не пройдена")
        os.utime(temporary, None)
        os.chmod(temporary, 0o444)
        os.replace(temporary, target)
        changed(target,Path(temporary),target.with_suffix('.lock'))
        with directory_fd(config.APP_STORAGE_ROOT,directory.relative_to(config.APP_STORAGE_ROOT)) as parent:os.fsync(parent)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)
        changed(Path(temporary))
