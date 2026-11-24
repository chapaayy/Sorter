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

from app import config
from app.storage.categories import Category
from app.storage.paths import managed_path,managed_prefix,digest_key
from app.storage.filesystem import parent_fd,safe_read,safe_unlink
from .paths import owned_file
import stat
from .thumbnail_cache import PIXEL_LIMIT

CHUNK_LIMIT = 16 * 1024 * 1024

def object_root():
    return managed_prefix(Category.REFERENCE_OBJECT)

def session_root(session_id):
    return managed_prefix(Category.REFERENCE_UPLOAD_PART,session_uuid=session_id)

def partial(session_id,upload_id):
    return managed_path(Category.REFERENCE_UPLOAD_PART,session_uuid=session_id,upload_uuid=upload_id)

def object_path(digest):
    digest=digest_key(digest)
    return managed_path(Category.REFERENCE_OBJECT,prefix=digest[:2],sha256=digest)

def verify(path,root,size,*,digest=None):
    path=owned_file(Path(path),root)
    with safe_read(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT)) as stream:
        if os.fstat(stream.fileno()).st_size!=size:
            raise ValueError("Reference file has wrong size")
        if digest is not None and hashlib.file_digest(stream,"sha256").hexdigest()!=digest:
            raise ValueError("Reference checksum mismatch")
    return path

def verify_object(path,size,*,digest):
    if Path(path)!=object_path(digest):
        raise ValueError("Noncanonical reference object")
    return verify(path,object_root(),size,digest=digest)

def create_partial(session_id,upload_id):
    target=partial(session_id,upload_id)
    try:
        with parent_fd(config.APP_STORAGE_ROOT,target.relative_to(config.APP_STORAGE_ROOT),create=True) as (fd,name):
            try:
                handle=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                os.close(handle)
            except FileExistsError:
                if not stat.S_ISREG(os.stat(name,dir_fd=fd,follow_symlinks=False).st_mode):raise ValueError("Invalid part")
    except (OSError,ValueError) as exc:
        raise HTTPException(409,"Некорректный временный файл") from exc
    return target

def offset(session_id,upload_id,expected_size):
    path=partial(session_id,upload_id)
    try:
        with safe_read(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT)) as stream:
            length=os.fstat(stream.fileno()).st_size
    except FileNotFoundError:return 0
    except (OSError,ValueError) as exc:raise HTTPException(409,"Некорректный временный файл") from exc
    if length>expected_size:raise HTTPException(409,"Временный файл превышает заявленный размер")
    return length

def append(session_id,upload_id,expected,size,data):
    if not data or len(data)>CHUNK_LIMIT:raise HTTPException(413,"Неверный размер блока")
    path=create_partial(session_id,upload_id)
    with parent_fd(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT)) as (fd,name), os.fdopen(os.open(name,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd),"r+b") as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise HTTPException(409,"Файл уже опубликован")
        actual=stream.seek(0,os.SEEK_END)
        if actual!=expected:raise HTTPException(409,{"expected_offset":actual})
        if actual+len(data)>size:raise HTTPException(413,"Превышен размер образца")
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
    """Caller holds FIFO publication lock; keep part until SQL commits."""
    source=verify(partial(session_id,upload_id),session_root(session_id),size,digest=digest)
    target=object_path(digest)
    root=config.APP_STORAGE_ROOT
    with parent_fd(root,target.relative_to(root),create=True) as (dst,name):
        try:
            with parent_fd(root,source.relative_to(root)) as (src,part):
                os.link(part,name,src_dir_fd=src,dst_dir_fd=dst,follow_symlinks=False)
        except FileExistsError:pass
        try:
            verify_object(target,size,digest=digest)
        except (OSError,ValueError) as exc:raise HTTPException(409,"Конфликт сохранения образца") from exc
        with safe_read(root,target.relative_to(root)) as stream:
            os.fchmod(stream.fileno(),0o444)
            os.fsync(stream.fileno())
        os.fsync(dst)
    return target

def remove_partial_after_commit(session_id,upload_id):
    path=partial(session_id,upload_id)
    safe_unlink(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT),missing_ok=True)
