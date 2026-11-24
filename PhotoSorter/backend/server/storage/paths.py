"""Trusted batch/run paths; strict containment for existing storage callers."""
from pathlib import Path
import re
import stat
from app.config import DATA_DIR, RUNS_DIR
from app.storage.paths import uuid_key, run_key, managed_prefix, managed_path
from app.storage.categories import Category

OUTPUTS = DATA_DIR / "outputs"
RUN_PATTERN = re.compile(r"\d{8}T\d{6}-[a-f0-9]{12}\Z")

def batch_owner(batch_id, db=None):
    from ..database import connect
    batch_id=uuid_key(batch_id)
    if db is None:
        with connect() as conn:
            return batch_owner(batch_id,conn)
    row=db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch_id,)).fetchone()
    if not row:
        raise FileNotFoundError("Unknown batch")
    return row["owner_id"]

def batch_dir(batch_id, owner_id=None):
    owner_id=batch_owner(batch_id) if owner_id is None else owner_id
    return managed_prefix(Category.FO_ORIGINAL,user_id=owner_id,batch_uuid=batch_id)

def batch_root(batch_id, owner_id=None):
    return batch_dir(batch_id,owner_id).parent

def original_path(batch_id, upload_id, ext, owner_id=None):
    owner_id=batch_owner(batch_id) if owner_id is None else owner_id
    return managed_path(Category.FO_ORIGINAL,user_id=owner_id,batch_uuid=batch_id,upload_uuid=upload_id,ext=ext)

def normalized_path(batch_id, upload_id, ext, owner_id=None):
    owner_id=batch_owner(batch_id) if owner_id is None else owner_id
    return managed_path(Category.FO_NORMALIZED,user_id=owner_id,batch_uuid=batch_id,upload_uuid=upload_id,ext=ext)

def normalized_dir(batch_id, owner_id=None):
    owner_id=batch_owner(batch_id) if owner_id is None else owner_id
    return managed_prefix(Category.FO_NORMALIZED,user_id=owner_id,batch_uuid=batch_id)

def part_path(batch_id, upload_id):
    return managed_path(Category.FO_UPLOAD_PART,batch_uuid=batch_id,upload_uuid=upload_id)

def run_dir(run_id, root=None):
    return Path(OUTPUTS if root is None else root) / run_key(run_id)

def _contained(path, root):
    root, candidate = Path(root), Path(path)
    if not root.is_absolute() or not candidate.is_absolute() or ".." in candidate.parts or ".." in root.parts:
        raise ValueError("File outside owned storage")
    if root.resolve() != root or not candidate.is_relative_to(root):
        raise ValueError("File outside owned storage")
    current = root
    # Reject all symlink components, even links resolving inside the root.
    for part in candidate.relative_to(root).parts:
        current = current / part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ValueError("Symlink inside owned storage")
        except FileNotFoundError:
            break
    return candidate

def owned_file(path, root):
    return _contained(path, root)

def owned_directory(path, root):
    return _contained(path, root)
