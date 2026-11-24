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

TTL_SECONDS=3600
FO_NAME=re.compile(r"[a-f0-9]{12}-[a-f0-9]{20}\.(?:zip|lock)")
REF_NAME=re.compile(r"[a-f0-9]{64}\.(?:zip|lock)")
FO_TMP=re.compile(r"\.archive-[A-Za-z0-9_-]+\.tmp")
REF_TMP=re.compile(r"\.references-[A-Za-z0-9_-]+\.tmp")

def pin(directory:Path):
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
def build_space(root,needed):
    """Serialize archive allocations across results/reference caches on data mount."""
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        total,available=disk_guard.stat(root)
        if available-needed<disk_guard.reserve(total):
            raise HTTPException(507,"Недостаточно места для временного ZIP")
        yield
    finally:
        os.close(fd)

def sweep_folder(folder,*,reference=False,now=None):
    """Delete only expired, recognized archives/fragments/locks, never active ones."""
    now=time.time() if now is None else now
    try:
        fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    except OSError:
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
                removed+=1
            except OSError:
                continue
        return removed
    finally:
        os.close(fd)

def collect():
    from . import archives,reference_archives
    from ..database import connect
    from ..storage.paths import run_dir,owned_directory
    with connect() as db:
        rows=db.execute("""SELECT j.id,j.batch_id,b.owner_id FROM jobs j
            JOIN batches b ON b.id=j.batch_id
            WHERE j.status IN ('completed','completed_with_errors')""").fetchall()
    removed=0
    for row in rows:
        try:
            run=run_dir(row["id"],identity=(row["batch_id"],row["owner_id"]))
            folder=owned_directory(run/".archives",archives.output_root())
            removed+=sweep_folder(folder)
        except (OSError,ValueError):
            continue
    if not reference_archives.EXPORTS.is_symlink():
        removed+=sweep_folder(reference_archives.EXPORTS,reference=True)
    return removed
