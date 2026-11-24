"""Linux dirfd-based filesystem operations; never follow symlink components.

Authorization and object lifetime coordination belong to the caller. Only
new files are writable through these helpers; existing hardlinks are never
opened for in-place modification.
"""
import os
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from .paths import relative_key

_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

@contextmanager
def directory_fd(root, key=None, *, create=False):
    root = Path(root)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("Expected absolute trusted root")
    fd = os.open("/", _DIR)
    try:
        parts = list(root.parts[1:])
        root_count = len(parts)
        if key is not None:
            parts.extend(relative_key(str(key)).parts)
        for index, part in enumerate(parts):
            if create and index >= root_count:
                try:
                    os.mkdir(part, mode=0o750, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, _DIR, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)

@contextmanager
def parent_fd(root, key, *, create=False):
    path = relative_key(str(key))
    with directory_fd(root, None if len(path.parts) == 1 else path.parent, create=create) as fd:
        yield fd, path.name

@contextmanager
def safe_read(root, key):
    with parent_fd(root, key) as (fd, name):
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(handle).st_mode):
                raise ValueError("Not a regular file")
            with os.fdopen(handle, "rb", closefd=False) as stream:
                yield stream
        finally:
            os.close(handle)

def _regular_target(fd, name, *, missing_ok=False):
    try:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Not a regular storage file")
    return info

def safe_unlink(root, key, *, missing_ok=False):
    try:
        with parent_fd(root, key) as (fd, name):
            if _regular_target(fd, name, missing_ok=missing_ok) is None:
                return
            os.unlink(name, dir_fd=fd)
            os.fsync(fd)
    except FileNotFoundError:
        if not missing_ok:
            raise

def atomic_publish(root, staged, target):
    """Atomic same-mount publication of a verified regular staged file.

    The caller owns the staging operation and coordinates competing writers.
    Failure leaves the source intact unless rename itself already succeeded.
    """
    with parent_fd(root, staged) as (src_fd, src_name), parent_fd(root, target, create=True) as (dst_fd, dst_name):
        _regular_target(src_fd, src_name)
        _regular_target(dst_fd, dst_name, missing_ok=True)
        fd = os.open(src_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=src_fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Not a regular staged file")
            os.fsync(fd)
            os.replace(src_name, dst_name, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
            os.fsync(dst_fd)
            os.fsync(src_fd)
        finally:
            os.close(fd)

def file_stat(root, key):
    with safe_read(root, key) as stream:
        info = os.fstat(stream.fileno())
        return {"logical": info.st_size, "allocated": info.st_blocks * 512,
                "device": info.st_dev, "inode": info.st_ino, "links": info.st_nlink}

@contextmanager
def atomic_write(root, key):
    """Publish on successful exit; preserve existing inode on failed writes."""
    with parent_fd(root, key, create=True) as (fd, name):
        fragment = "atomic-" + uuid.uuid4().hex + ".tmp"
        handle = os.open(fragment, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=fd)
        try:
            with os.fdopen(handle, "wb") as stream:
                yield stream
                stream.flush()
                os.fsync(stream.fileno())
            _regular_target(fd, name, missing_ok=True)
            os.replace(fragment, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(fragment, dir_fd=fd)
            except FileNotFoundError:
                pass
