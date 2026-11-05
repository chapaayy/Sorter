"""Read-only data-mount capacity and approximate logical/physical category usage."""
from __future__ import annotations
import os
from pathlib import Path
from app.config import DATA_DIR, MODELS_DIR
from .disk_guard import reserve
from ..database import connect
from app.config import RUNS_DIR

def _size(root,seen):
    total=0
    if not root.exists():return 0
    for directory,subdirs,files in os.walk(root,followlinks=False):
        subdirs[:]=[d for d in subdirs if not (Path(directory)/d).is_symlink()]
        for name in files:
            path=Path(directory)/name
            try:
                if path.is_symlink():continue
                s=path.stat()
            except OSError:continue
            ident=(s.st_dev,s.st_ino)
            if ident not in seen:
                seen.add(ident)
                total+=s.st_size
    return total

def usage():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    s=os.statvfs(DATA_DIR)
    total=s.f_frsize*s.f_blocks
    free=s.f_frsize*s.f_bavail
    used=total-(s.f_frsize*s.f_bfree)
    seen=set()
    groups={}
    groups["logs"]=_size_logfiles(RUNS_DIR,seen)
    for key,root in (("photos",DATA_DIR/"uploads"),("results",DATA_DIR/"outputs"),
                      ("references",DATA_DIR/"references"),("thumbnails",DATA_DIR/"cache"/"thumbnails"),
                      ("reference_cache",DATA_DIR/"cache"/"megaloc"),("models",MODELS_DIR),
                      ("runs",DATA_DIR/"runs"),("incoming",DATA_DIR/"incoming")):
        groups[key]=_size(root,seen)
    groups["other"]= _size(DATA_DIR,seen)
    db_size=None
    try:
        with connect() as db:
            db_size=db.execute("SELECT pg_database_size(current_database()) AS bytes").fetchone()["bytes"]
    except Exception:
        pass
    fraction=used/total if total else 0
    required=reserve(total)
    return {"disk":{"total_bytes":total,"used_bytes":used,"available_bytes":free,
            "reserved_bytes":required,"admission_ok":free>required,
            "used_fraction":fraction,"warning":"critical" if fraction>=.90
            else "warning" if fraction>=.80 else None},
            "categories_bytes":groups,
            "database_estimated_bytes":db_size,
            "not_scanned":["postgres_WAL","Docker_logs","Caddy_volumes"],
            "counting":"physical_inode_deduplicated"}

def _size_logfiles(root,seen):
    total=0
    if not root.exists():return total
    for file in root.glob("*/events.jsonl*"):
        try:
            if file.is_symlink() or not file.is_file():continue
            stat=file.stat()
        except OSError:continue
        key=(stat.st_dev,stat.st_ino)
        if key not in seen:
            seen.add(key)
            total+=stat.st_size
    return total
