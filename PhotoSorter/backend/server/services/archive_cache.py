"""Temporary ZIP lifecycle shared by FO and reference exports.

Directory flock pins protect the entire build/HTTP response from expiry.
Cleanup never follows symlinks or removes a directory, only known cache names.
"""
from __future__ import annotations
import fcntl
import os
import re
import stat
import time
from pathlib import Path
from contextlib import contextmanager
from . import disk_guard
from fastapi import HTTPException

from app.storage.categories import ARCHIVE_TTL_SECONDS,Category
from app.storage.paths import managed_prefix,run_key
from app.storage.filesystem import directory_fd
from app.storage.changes import changed
from app import config

TTL_SECONDS=ARCHIVE_TTL_SECONDS

def fresh(path,*,now=None):
    try:
        info=path.stat(follow_symlinks=False)
        return stat.S_ISREG(info.st_mode) and (time.time() if now is None else now)-info.st_mtime<TTL_SECONDS
    except FileNotFoundError:return False
FO_NAME=re.compile(r"[a-f0-9]{12}-[a-f0-9]{20}\.(?:zip|lock)")
REF_NAME=re.compile(r"[a-f0-9]{64}\.(?:zip|lock)")
FO_TMP=re.compile(r"\.archive-[A-Za-z0-9_-]+\.tmp")
REF_TMP=re.compile(r"\.references-[A-Za-z0-9_-]+\.tmp")

def pin(directory:Path):
    directory=Path(directory)
    if directory.is_relative_to(config.APP_STORAGE_ROOT):
        with directory_fd(config.APP_STORAGE_ROOT,directory.relative_to(config.APP_STORAGE_ROOT),create=True) as opened:fd=os.dup(opened)
    else:
        # Standalone test paths; production callers always use managed paths.
        directory.mkdir(parents=True,exist_ok=True)
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_SH)
        return DirectoryPin(fd)
    except BaseException:
        os.close(fd)
        raise

class DirectoryPin:
    def __init__(self,fd):
        self.fd=fd
    def close(self):
        if self.fd is not None:
            fd,self.fd=self.fd,None
            os.close(fd)
    def __enter__(self):
        return self
    def __exit__(self,*_):
        self.close()

@contextmanager
def build_space(root,needed,*,message="Недостаточно места для временного ZIP",kind="archive"):
    """Serialize archive allocations across results/reference caches on data mount."""
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        total,available=disk_guard.stat(root)
        if available-needed<disk_guard.reserve(total):
            raise HTTPException(507,message)
        from ..storage.reservations import reservation
        with reservation(kind,needed):yield
    finally:
        os.close(fd)

def sweep_folder(folder,*,reference=False,now=None):
    """Delete only expired, recognized archives/fragments/locks, never active ones."""
    now=time.time() if now is None else now
    try:
        folder=Path(folder)
        if folder.is_relative_to(config.APP_STORAGE_ROOT):
            with directory_fd(config.APP_STORAGE_ROOT,folder.relative_to(config.APP_STORAGE_ROOT)) as opened:fd=os.dup(opened)
        else:
            fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    except (OSError,ValueError):
        return 0
    removed=0
    pattern,tmp=(REF_NAME,REF_TMP) if reference else (FO_NAME,FO_TMP)
    try:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        for name in os.listdir(fd):
            if not (pattern.fullmatch(name) or tmp.fullmatch(name)):
                continue
            try:
                info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    continue
                if now-info.st_mtime<TTL_SECONDS:
                    continue
                if name.endswith(".lock"):
                    # Keep a lock while its archive is present. Exclusive folder
                    # lease proves there are no users of the lock inode.
                    try:
                        os.stat(name[:-5]+".zip",dir_fd=fd,follow_symlinks=False)
                        continue
                    except FileNotFoundError:
                        pass
                os.unlink(name,dir_fd=fd)
                changed(folder/name)
                removed+=1
            except OSError:
                continue
        return removed
    finally:
        os.close(fd)

def collect():
    """Scan only typed archive folders, including runs removed after a crash."""
    root=managed_prefix(Category.ZIP_RESULTS)
    removed=0
    if root.is_dir() and not root.is_symlink():
        for folder in root.iterdir():
            try:
                if folder!=managed_prefix(Category.ZIP_RESULTS,run_id=run_key(folder.name)):continue
                if folder.is_symlink() or not folder.is_dir():continue
                removed+=sweep_folder(folder)
            except (OSError,ValueError):continue
    removed+=sweep_folder(managed_prefix(Category.ZIP_REFERENCES),reference=True)
    return removed
