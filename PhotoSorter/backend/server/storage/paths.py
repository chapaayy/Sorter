"""Trusted batch/run paths; strict containment for existing storage callers."""
from pathlib import Path
import re
import stat
from app.config import DATA_DIR, RUNS_DIR
from app.storage.paths import uuid_key, run_key

UPLOADS = DATA_DIR / "uploads"
OUTPUTS = DATA_DIR / "outputs"
INCOMING = DATA_DIR / "incoming"
RUN_PATTERN = re.compile(r"\d{8}T\d{6}-[a-f0-9]{12}\Z")

def batch_dir(batch_id):
    return UPLOADS / uuid_key(batch_id)

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
