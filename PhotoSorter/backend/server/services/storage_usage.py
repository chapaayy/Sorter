"""Read-only data-mount capacity and approximate logical/physical category usage."""
from __future__ import annotations
import os
import json
from pathlib import Path
from app.config import DATA_DIR, MODELS_DIR, MODEL_CACHE_DIR
from app.storage.paths import managed_prefix,category_prefix
from app import config
from .storage_breakdown import _kind
from app.storage.categories import Category
from .disk_guard import reserve
from ..database import connect
from app.logging.events import RUNS_DIR

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
    groups.update(photos=0,results=0,incoming=0,thumbnails=0,reference_thumbnails=0,references=0,reference_cache=0,reference_uploads=0)
    # Walk only managed personal and temp trees, with inode dedup shared with other groups.
    for prefix in (category_prefix(Category.FO_ORIGINAL),category_prefix(Category.REFERENCE_OBJECT).parent,category_prefix(Category.PROCESSING_STAGING).parent):
        root=config.APP_STORAGE_ROOT/prefix
        for directory,subdirs,files in os.walk(root,followlinks=False):
            subdirs[:]=[d for d in subdirs if not (Path(directory)/d).is_symlink()]
            for name in files:
                path=Path(directory)/name
                try:
                    if path.is_symlink() or not path.is_file():continue
                    st=path.stat()
                except OSError:continue
                identity=(st.st_dev,st.st_ino)
                if identity in seen:continue
                seen.add(identity)
                category=_kind(path.relative_to(config.APP_STORAGE_ROOT).parts)
                key={"originals":"photos","normalized":"photos","incoming":"incoming","reference_objects":"references","reference_gallery":"references","reference_cache":"reference_cache","reference_thumbnails":"reference_thumbnails","thumbnails":"thumbnails","reference_uploads":"reference_uploads"}.get(category,"results")
                groups[key]+=st.st_size
    for key,root in (
                      ("references",DATA_DIR/"references"),("thumbnails",DATA_DIR/"cache"/"thumbnails"),
                      ("reference_cache",DATA_DIR/"cache"/"megaloc"),("models",MODELS_DIR),
                      ("runs",DATA_DIR/"runs")):
        groups[key]=groups.get(key,0)+_size(root,seen)
    groups["models"]+=_size(MODEL_CACHE_DIR,seen)
    groups["other"]= _size(DATA_DIR,seen)
    db_size=None
    try:
        with connect() as db:
            db_size=db.execute("SELECT pg_database_size(current_database()) AS bytes").fetchone()["bytes"]
    except Exception:
        pass
    fraction=used/total if total else 0
    required=reserve(total)
    from app.storage.categories import LOG_BUDGETS_MIB
    journals={"at":None,"services":{name:{"bytes":None,"budget_bytes":n*1024*1024,"partial":True} for name,n in LOG_BUDGETS_MIB.items()}}
    try:
        report=json.loads(Path("/run/map-updater/log-usage.json").read_text())
        journals["at"]=report.get("at")
        for name,row in journals["services"].items():
            sample=report.get("services",{}).get(name,{})
            if isinstance(sample.get("bytes"),int) and sample["bytes"]>=0:
                row.update(bytes=sample["bytes"],partial=bool(sample.get("partial")))
    except (OSError,ValueError,TypeError,AttributeError):pass
    return {"journals":journals,"disk":{"total_bytes":total,"used_bytes":used,"available_bytes":free,
            "reserved_bytes":required,"admission_ok":free>required,
            "used_fraction":fraction,"warning":"critical" if fraction>=.90
            else "warning" if fraction>=.80 else None},
            "categories_bytes":groups,
            "database_estimated_bytes":db_size,
            "not_scanned":["postgres_WAL","Docker_logs","Caddy_state"],
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
