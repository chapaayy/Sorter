"""Private scratch and downloader workspaces protected by kernel leases."""
from contextlib import contextmanager
import os
import fcntl
import time
import tempfile
from pathlib import Path
import shutil
import uuid
from .categories import Category
from .paths import app_key,category_prefix,uuid_key
from .filesystem import parent_fd,directory_fd
import stat
from .changes import changed

@contextmanager
def leased_operation(root,category,**fields):
    """Parent gate closes the create/open versus sweep race; child flock lives
    for the operation. Crash releases the kernel lease even without DB access."""
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    key=app_key(category,**fields).relative
    with parent_fd(root,key,create=True) as (parent,name):
        fcntl.flock(parent,fcntl.LOCK_EX)
        try:
            os.mkdir(name,mode=0o700,dir_fd=parent)
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            fcntl.flock(fd,fcntl.LOCK_EX)
        finally:
            fcntl.flock(parent,fcntl.LOCK_UN)
        try:
            yield root/key,fd
        finally:
            try:shutil.rmtree(name,dir_fd=parent)
            finally:
                os.close(fd)
                changed(root/key,subtree=True)

@contextmanager
def temporary_operation(root,service):
    with leased_operation(root,Category.SCRATCH,service=service,operation_id=uuid.uuid4()) as (path,_):
        yield path

@contextmanager
def download_operation(root):
    with leased_operation(root,Category.MODEL_DOWNLOAD,task_id=uuid.uuid4()) as (path,fd):
        yield path,fd

@contextmanager
def temporary_file(service="worker"):
    from app.config import APP_STORAGE_ROOT
    with temporary_operation(APP_STORAGE_ROOT,service) as directory:
        with tempfile.TemporaryFile(dir=directory) as stream:
            yield stream

def collect_abandoned(root,*,grace_seconds=None,now=None,limit=100):
    from .categories import TEMPORARY_GRACE_SECONDS
    now=time.time() if now is None else now
    grace_seconds=TEMPORARY_GRACE_SECONDS if grace_seconds is None else grace_seconds
    removed=0
    scopes=[(category_prefix(Category.SCRATCH,service=service),Category.SCRATCH,{"service":service})
            for service in ("api","worker","thumbnail","cleanup","models")]
    scopes.append((category_prefix(Category.MODEL_DOWNLOAD),Category.MODEL_DOWNLOAD,{}))
    for prefix,category,fields in scopes:
        try:
            with directory_fd(root,prefix) as parent:
                try:fcntl.flock(parent,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:continue
                for name in os.listdir(parent):
                    if removed>=limit:return removed
                    try:
                        uid=uuid_key(name)
                        key=app_key(category,**fields,**({"operation_id":uid} if fields else {"task_id":uid})).relative
                        if key.parent!=prefix:continue
                        fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                        try:
                            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                            except BlockingIOError:continue
                            if now-os.fstat(fd).st_mtime<grace_seconds:continue
                            shutil.rmtree(name,dir_fd=parent)
                            changed(root/key,subtree=True)
                            removed+=1
                        finally:os.close(fd)
                    except (OSError,ValueError):continue
        except (OSError,ValueError):continue
    return removed

@contextmanager
def pipeline_directory(category, **fields):
    """A FIFO-worker-owned directory, removed after success, failure or stop.

    Call only under the exclusive processing leader and the associated
    batch/task lease. A retry may remove its own interrupted staging.
    """
    from app.config import APP_STORAGE_ROOT
    if category not in (Category.TRANSCODE_TEMP, Category.VIDEO_FRAMES, Category.PROCESSING_STAGING):
        raise ValueError("Not a pipeline staging category")
    key = app_key(category, **fields).relative
    with parent_fd(APP_STORAGE_ROOT, key, create=True) as (fd, name):
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("Invalid pipeline staging object")
            shutil.rmtree(name, dir_fd=fd)
        os.mkdir(name, mode=0o700, dir_fd=fd)
        try:
            yield APP_STORAGE_ROOT / key
        finally:
            shutil.rmtree(name, dir_fd=fd)
