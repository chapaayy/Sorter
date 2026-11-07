"""Isolated, immutable staging objects for reference import sessions.

The old data/references tree is never written here. All file names used on disk
are UUID-derived; source paths are verified and no symlinks are accepted.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import HTTPException
from PIL import Image,UnidentifiedImageError

from app.config import DATA_DIR
from .thumbnail_cache import PIXEL_LIMIT

ROOT = DATA_DIR / "reference_staging"
LEGACY_ROOT = DATA_DIR / "references"
CHUNK_LIMIT = 16 * 1024 * 1024

def session_root(session_id):
    return ROOT / str(session_id)

def partial(session_id,upload_id):
    return session_root(session_id) / "incoming" / (str(upload_id) + ".part")

def object_path(session_id,upload_id,filename):
    return session_root(session_id) / "files" / (str(upload_id) + Path(filename).suffix.lower())

def verify(path,root,size,*,digest=None):
    """Verify immutable owned bytes, checking every path component for symlinks."""
    path=Path(path)
    root=Path(root).resolve()
    if not path.is_absolute() or not path.is_relative_to(root):
        raise ValueError("Reference file is outside its trusted directory")
    cur=path
    while cur!=root:
        if cur.is_symlink():
            raise ValueError("Symlink reference file is forbidden")
        cur=cur.parent
    if not path.is_file() or path.stat().st_size!=size:
        raise ValueError("Reference file is missing or has a wrong size")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Reference file resolves outside its trusted directory")
    if digest is not None:
        with path.open("rb") as stream:
            if hashlib.file_digest(stream,"sha256").hexdigest()!=digest:
                raise ValueError("Reference content checksum mismatch")
    return path

def _safe_directory(path):
    """Fail closed before any writes if a staging parent is a symlink."""
    path=Path(path)
    root=Path(ROOT)
    if not path.is_relative_to(root):
        raise HTTPException(409,"Путь вне временного хранилища")
    current=root
    if current.is_symlink():
        raise HTTPException(409,"Ссылка вместо staging каталога")
    for segment in path.relative_to(root).parts:
        current=current/segment
        if current.is_symlink():
            raise HTTPException(409,"Ссылка внутри staging каталога")
    path.mkdir(parents=True,exist_ok=True)
    if not path.resolve().is_relative_to(root.resolve()):
        raise HTTPException(409,"Путь вне временного хранилища")

def create_partial(session_id,upload_id):
    target=partial(session_id,upload_id)
    _safe_directory(target.parent)
    if target.is_symlink():
        raise HTTPException(409,"Некорректный временный файл")
    if not target.exists():
        try:
            with target.open("xb"):
                pass
        except FileExistsError:
            pass
    return target

def offset(session_id,upload_id,expected_size):
    path=partial(session_id,upload_id)
    if path.is_symlink():
        raise HTTPException(409,"Некорректный временный файл")
    if not path.exists():
        return 0
    length=path.stat().st_size
    if length>expected_size:
        raise HTTPException(409,"Временный файл превышает заявленный размер")
    return length

def append(session_id,upload_id,expected,size,data):
    if not data or len(data)>CHUNK_LIMIT:
        raise HTTPException(413,"Неверный размер блока")
    path=create_partial(session_id,upload_id)
    with path.open("r+b") as stream:
        actual=stream.seek(0,os.SEEK_END)
        if actual!=expected:
            raise HTTPException(409,{"expected_offset":actual})
        if actual+len(data)>size:
            raise HTTPException(413,"Превышен размер образца")
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
        return actual+len(data)

def verify_picture(path):
    try:
        with Image.open(path) as picture:
            if picture.width*picture.height>PIXEL_LIMIT:
                raise HTTPException(422,"Слишком высокое разрешение")
            picture.verify()
    except (OSError,UnidentifiedImageError,ValueError) as exc:
        raise HTTPException(422,"Файл не является корректным изображением") from exc

def publish_staged_file(session_id,upload_id,filename,size,digest):
    """Hardlink-first, recoverable after a process crash before the SQL commit.

    Keep the partial file until the surrounding DB transaction is committed.
    A retry checks an existing destination's checksum rather than overwriting.
    """
    source=verify(partial(session_id,upload_id),session_root(session_id),size,digest=digest)
    target=object_path(session_id,upload_id,filename)
    _safe_directory(target.parent)
    if target.is_symlink():
        raise HTTPException(409,"Неверный путь образца")
    if not target.exists():
        try:
            os.link(source,target,follow_symlinks=False)
        except FileExistsError:
            pass
    try:
        verify(target,session_root(session_id),size,digest=digest)
    except ValueError as exc:
        raise HTTPException(409,"Конфликт сохранения образца") from exc
    target.chmod(0o444)
    return target

def remove_partial_after_commit(session_id,upload_id):
    path=partial(session_id,upload_id)
    if not path.is_symlink():
        path.unlink(missing_ok=True)
