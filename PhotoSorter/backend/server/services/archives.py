"""Reusable, seekable ZIP archives for completed MegaLoc runs.

Build only on request, atomically; expire after one hour under archive_cache.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from fastapi import HTTPException
from . import archive_cache
from app.storage.categories import Category
from app.storage.paths import managed_prefix
from app.storage.filesystem import directory_fd
from ..storage import paths as storage_paths
from ..storage.paths import owned_file, owned_directory

def existing(run_id:str,sam:str|None,selected:list[tuple[Path,str]])->Path|None:
    """Only return validated complete ZIPs; never create one on download."""
    target=_cache_path(run_id,sam,selected)
    if archive_cache.fresh(target) and zipfile.is_zipfile(target):
        return owned_file(target,archive_folder(run_id))
    return None

def output_root()->Path:
    # Common filesystem for reservation locking, not a result namespace.
    from app.config import APP_STORAGE_ROOT
    return APP_STORAGE_ROOT

def archive_folder(run_id):
    folder=managed_prefix(Category.ZIP_RESULTS,run_id=run_id)
    return owned_directory(folder,output_root())

def published(run_id:str,filename:str)->Path|None:
    """Look up a saved archive by its validated run-local cache filename."""
    if not re.fullmatch(r"[a-f0-9]{12}-[a-f0-9]{20}\.zip",filename):
        return None
    folder=archive_folder(run_id)
    target=owned_file(folder/filename,folder)
    return target if archive_cache.fresh(target) and zipfile.is_zipfile(target) else None

def archive_member(sam:str,filename:str)->str:
    if (not sam or sam in (".","..") or
        any(c in sam for c in "/\\\x00") or
        not filename or filename in (".","..") or
        any(c in filename for c in "/\\\x00")):
        raise HTTPException(422,"Недопустимое имя в ZIP")
    result=PurePosixPath(sam)/filename
    if result.is_absolute() or ".." in result.parts:
        raise HTTPException(422,"Недопустимый путь в ZIP")
    return result.as_posix()

def _cache_path(run_id:str, sam:str|None, selected:list[tuple[Path,str]])->Path:
    # Every output is uniquely identified by its immutable input manifest.
    digest=hashlib.sha256()
    media=storage_paths.result_media_dir(run_id)
    for file,name in selected:
        info=owned_file(file,media).stat()
        digest.update(json.dumps([str(file),name,info.st_size,info.st_mtime_ns],
                    ensure_ascii=False).encode())
    token=hashlib.sha256((sam or "all").encode()).hexdigest()[:12]
    folder=archive_folder(run_id)
    if folder.is_symlink():raise HTTPException(409,"Недопустимый каталог архивов")
    with directory_fd(output_root(),folder.relative_to(output_root()),create=True):pass
    return folder/(token+"-"+digest.hexdigest()[:20]+".zip")

def prepare(run_id:str,sam:str|None,selected:list[tuple[Path,str]],*,progress=None,should_stop=None)->Path:
    if not selected:raise HTTPException(404,"Нет фотографий для архива")
    target=_cache_path(run_id,sam,selected)
    total=sum(source.stat().st_size for source,_ in selected)
    lock=target.with_suffix(".lock")
    with archive_cache.pin(target.parent), os.fdopen(os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a+b") as handle:
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
        root=storage_paths.result_media_dir(run_id)
        try:
            if target.exists():
                owned_file(target,archive_folder(run_id))
                if archive_cache.fresh(target) and zipfile.is_zipfile(target):
                    if progress:progress(total,total)
                    return target
                # Keep old inode until the verified replacement is ready.
            with archive_cache.build_space(output_root(),total+1024*1024+len(selected)*2048):
                return _build(target,selected,total,progress,should_stop,root)
        finally:
            fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

def _build(target,selected,total,progress,should_stop,root):
    fd,tmp=tempfile.mkstemp(dir=target.parent,prefix=".archive-",suffix=".tmp")
    try:
        with os.fdopen(fd,"wb") as output:
            with zipfile.ZipFile(output,mode="w",compression=zipfile.ZIP_STORED,
                                 allowZip64=True) as archive:
                done=0
                for source,name in selected:
                    if should_stop and should_stop():
                        raise InterruptedError("Подготовка архива остановлена")
                    owned_file(source,root)
                    # JPEG already compressed: store without recompressing.
                    archive.write(source,arcname=name,compress_type=zipfile.ZIP_STORED)
                    done+=source.stat().st_size
                    if progress:progress(done,total)
            output.flush()
            os.fsync(output.fileno())
        # Publishing an archive is atomic: verify
        # every entry's CRC and count before making the ZIP visible.
        with zipfile.ZipFile(tmp,"r") as verified:
            if len(verified.infolist())!=len(selected):
                raise OSError("ZIP не содержит все фотографии")
            corrupt=verified.testzip()
            if corrupt is not None:
                raise OSError("Ошибка проверки ZIP: "+corrupt)
        os.utime(tmp,None)
        os.chmod(tmp,0o444)
        os.replace(tmp,target)
        with directory_fd(output_root(),target.parent.relative_to(output_root())) as parent:os.fsync(parent)
        return target
    finally:
        Path(tmp).unlink(missing_ok=True)
