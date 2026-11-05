"""Immutable export: exclusive hard links, verified fallback, never overwrite originals."""
from __future__ import annotations
import errno
import hashlib
import os
import shutil
from pathlib import Path

COPY_FALLBACK = {errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.EROFS}

def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def link_or_copy(source: Path, target: Path, *, expected_stamp=None, expected_hash=None):
    source, target = Path(source), Path(target)
    before = source.stat()
    if not source.is_file() or source.is_symlink():
        raise ValueError("Unsafe photo source")
    if expected_stamp and (before.st_size, before.st_mtime_ns) != tuple(expected_stamp):
        raise ValueError("Photo changed after matching")
    digest = sha256(source)
    if expected_hash and digest != expected_hash:
        raise ValueError("Photo checksum mismatch before export")
    method = "hardlink"
    created = False
    try:
        try:
            os.link(source, target, follow_symlinks=False)
            created = True
        except OSError as error:
            if error.errno not in COPY_FALLBACK:
                raise
            method = "copy"
            with source.open("rb") as src:
                with target.open("xb") as dst:
                    created = True
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                    dst.flush()
                    os.fsync(dst.fileno())
            shutil.copystat(source, target)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev) != (
                after.st_size, after.st_mtime_ns, after.st_ino, after.st_dev):
            raise ValueError("Photo changed during export")
        result = target.stat()
        if method == "hardlink" and (result.st_ino, result.st_dev) != (before.st_ino, before.st_dev):
            raise ValueError("Hard link verification failed")
        if sha256(target) != digest or sha256(source) != digest:
            raise ValueError("Photo checksum changed during export")
        return method
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
