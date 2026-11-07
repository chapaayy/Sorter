"""Create immutable, checksum-verified copies of legacy reference images.

Legacy files can be renamed/deleted by older routes. Version snapshots never
point at those mutable names. All storage is owned by PhotoSorter/data.
"""
from __future__ import annotations
import hashlib
import os
import shutil
import uuid
from pathlib import Path
from app.config import DATA_DIR
from .reference_objects import verify

ROOT=DATA_DIR/"reference_objects"
LEGACY_ROOT=DATA_DIR/"references"

def stable_legacy(row):
    """Return an immutable path; never chmod or unlink the original."""
    original=verify(row["target_path"],LEGACY_ROOT,row["declared_size"])
    with original.open("rb") as stream:
        digest=hashlib.file_digest(stream,"sha256").hexdigest()
    if row["checksum"] and row["checksum"]!=digest:
        raise ValueError("Legacy reference SHA-256 differs from DB")
    dest=ROOT/"legacy"/str(row["id"])/ (digest+original.suffix.lower())
    if dest.exists():
        verify(dest,ROOT,row["declared_size"],digest=digest)
        return dest,digest
    if dest.parent.is_symlink() or ROOT.is_symlink() or (ROOT/"legacy").is_symlink():
        raise ValueError("Unsafe immutable reference directory")
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_name("."+uuid.uuid4().hex+".tmp")
    try:
        with original.open("rb") as src,temp.open("xb") as out:
            shutil.copyfileobj(src,out,1024*1024)
            out.flush()
            os.fsync(out.fileno())
        verify(temp,ROOT,row["declared_size"],digest=digest)
        temp.chmod(0o444)
        try:
            os.link(temp,dest,follow_symlinks=False)
        except FileExistsError:
            verify(dest,ROOT,row["declared_size"],digest=digest)
    finally:
        temp.unlink(missing_ok=True)
    verify(dest,ROOT,row["declared_size"],digest=digest)
    return dest,digest

def verify_member(member):
    from .reference_objects import ROOT as STAGING
    kind=member["source_kind"]
    root=ROOT if kind=="legacy" else STAGING
    return verify(member["target_path"],root,member["declared_size"],
                  digest=member["source_hash"])
