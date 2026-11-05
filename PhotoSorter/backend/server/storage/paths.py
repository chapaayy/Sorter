"""Trusted, UUID/validated-run derived filesystem ownership boundaries."""
from pathlib import Path
import re
import uuid
from app.config import DATA_DIR, RUNS_DIR

UPLOADS = DATA_DIR / "uploads"
OUTPUTS = DATA_DIR / "outputs"
INCOMING = DATA_DIR / "incoming"
RUN_PATTERN = re.compile(r"\d{8}T\d{6}-[a-f0-9]{12}\Z")

def batch_dir(batch_id):
    return UPLOADS / str(uuid.UUID(str(batch_id)))

def run_dir(run_id, root=OUTPUTS):
    if not RUN_PATTERN.fullmatch(str(run_id)):
        raise ValueError("Invalid run identifier")
    return Path(root) / str(run_id)

def owned_file(path, root):
    """Reject all symlink escapes; never trust arbitrary database target_path blindly."""
    root = Path(root).resolve()
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
        raise ValueError("File outside owned storage")
    return candidate

def owned_directory(path, root):
    root = Path(root).resolve()
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
        raise ValueError("Directory outside owned storage")
    return candidate
