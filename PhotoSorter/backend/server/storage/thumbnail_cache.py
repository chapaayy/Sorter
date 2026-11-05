"""Versioned content-addressed preview paths. Never write into uploads or references."""
from __future__ import annotations
import re
from pathlib import Path
from app.config import DATA_DIR

VERSION=1
MAX_SIDE=480
QUALITY=78
PIXEL_LIMIT=30_000_000
ROOT=DATA_DIR/"cache"/"thumbnails"

def location(checksum:str,version:int=VERSION)->Path:
    if not re.fullmatch(r"[0-9a-f]{64}",str(checksum)) or version!=VERSION:
        raise ValueError("Invalid thumbnail key or version")
    return ROOT/f"v{version}"/checksum[:2]/f"{checksum}.webp"

def safe_location(path:Path)->Path:
    root=ROOT.resolve()
    value=Path(path)
    if value.is_symlink() or not value.resolve().is_relative_to(root):
        raise ValueError("Unsafe thumbnail path")
    return value
