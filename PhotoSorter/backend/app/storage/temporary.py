"""Private process-owned scratch; crash GC and durable leases are stage 5."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import uuid
from .categories import Category
from .paths import app_key
from .filesystem import parent_fd
import stat

@contextmanager
def temporary_operation(root, service):
    key = app_key(Category.SCRATCH, service=service, operation_id=uuid.uuid4()).relative
    with parent_fd(root, key, create=True) as (fd, name):
        os.mkdir(name, mode=0o700, dir_fd=fd)
        try:
            yield Path(root) / key
        finally:
            # Linux shutil.rmtree is fd-relative and resists symlink attacks.
            shutil.rmtree(name, dir_fd=fd)

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
