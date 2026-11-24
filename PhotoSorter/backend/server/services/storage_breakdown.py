"""Bounded read-only disk diagnostics.

Manual-only endpoint. No file content reads, re-encoding, cleanup, or writes.
Stats report allocated blocks by unique (device,inode), with logical directory
sizes shown separately to explain hard links. Concurrent mutations may make
the snapshot approximate; skipped paths are reported rather than invented.
"""
from __future__ import annotations

import os
import stat as statlib
import time
from datetime import datetime,timezone
from pathlib import Path
from ..database import connect
from app.config import DATA_DIR,MODELS_DIR,MODEL_CACHE_DIR

MAX_FILES=250_000
MAX_SECONDS=10.0
BUCKETS=(
    "originals","normalized","results_files","results_zip",
    "results_temporary","reference_objects","reference_gallery",
    "references_zip","reference_uploads","reference_other",
    "thumbnails","reference_cache","other_cache",
    "runs","logs","incoming","models","other",
)
BATCH_METRICS=("originals","normalized","results_files","results_zip","results_temporary")
ROOT_ORDER=("uploads","outputs","reference_staging","references",
            "reference_exports","cache","runs","incoming")

def _kind(parts: tuple[str,...]) -> str:
    if not parts:return "other"
    section=parts[0]
    if section=="uploads":
        return "normalized" if len(parts)>2 and parts[2]==".normalized" else "originals"
    if section=="outputs":
        if len(parts)>2 and parts[2]==".archives":
            return "results_zip" if parts[-1].lower().endswith(".zip") else "results_temporary"
        if len(parts)>2 and (parts[2].endswith(".building") or parts[2].startswith(".archive-")):
            return "results_temporary"
        return "results_files"
    if section=="reference_staging":
        if len(parts)>2 and parts[2]=="files":return "reference_objects"
        if len(parts)>2 and parts[2]=="incoming":return "reference_uploads"
        return "reference_other"
    if section=="references":return "reference_gallery"
    if section=="reference_exports":
        return "references_zip" if parts[-1].lower().endswith(".zip") else "reference_other"
    if section=="cache":
        if len(parts)>1 and parts[1]=="thumbnails":return "thumbnails"
        if len(parts)>1 and parts[1]=="megaloc":return "reference_cache"
        return "other_cache"
    if section=="runs":
        if parts[-1].startswith("events.jsonl"):return "logs"
        return "runs"
    if section=="incoming":return "incoming"
    return "other"

def _counter():
    return {"allocated_bytes":0,"logical_bytes":0,"hardlink_reused_bytes":0,
            "files":0,"hardlink_paths":0}

def _metadata():
    """One small DB lookup, never an N+1 query during the filesystem walk."""
    with connect() as db:
        batches={str(row["id"]):row["display_name"] for row in
                 db.execute("SELECT id,display_name FROM batches WHERE delete_state='active'")}
        jobs={row["id"]:str(row["batch_id"]) for row in
              db.execute("""SELECT j.id,j.batch_id FROM jobs j
                  JOIN batches b ON b.id=j.batch_id WHERE b.delete_state='active'""")}
    return batches,jobs

def _scan(data_dir:Path,models_dir:Path,batch_names:dict,run_to_batch:dict,
          *,max_files=MAX_FILES,max_seconds=MAX_SECONDS,model_cache_dir=None):
    """Standalone scanner, also used by tests; no database or write access."""
    groups={key:_counter() for key in BUCKETS}
    batches={}
    seen=set()
    skipped=0
    partial=False
    scanned=0
    started=time.monotonic()
    stop_at=started+max_seconds

    def owner(parts):
        if len(parts)<2:return None
        if parts[0]=="uploads":return parts[1] if parts[1] in batch_names else None
        if parts[0] in ("outputs","runs"):return run_to_batch.get(parts[1])
        return None

    def add(path,category,batch_id=None):
        nonlocal skipped,scanned
        try:
            if path.is_symlink():return
            stat=path.stat(follow_symlinks=False)
            if not statlib.S_ISREG(stat.st_mode):return
        except OSError:
            skipped+=1
            return
        scanned+=1
        key=(stat.st_dev,stat.st_ino)
        duplicate=key in seen
        if not duplicate:seen.add(key)
        allocated=0 if duplicate else max(0,stat.st_blocks*512)
        logical=max(0,stat.st_size)
        def update(counter):
            counter["files"]+=1
            counter["logical_bytes"]+=logical
            counter["allocated_bytes"]+=allocated
            if duplicate:
                counter["hardlink_paths"]+=1
                counter["hardlink_reused_bytes"]+=logical
        update(groups[category])
        if batch_id:
            item=batches.setdefault(batch_id,{"batch_id":batch_id,
                "display_name":batch_names.get(batch_id,"Партия"),
                **{metric:_counter() for metric in BATCH_METRICS},
                "allocated_bytes":0,"logical_bytes":0,"hardlink_reused_bytes":0})
            if category in BATCH_METRICS:update(item[category])
            item["allocated_bytes"]+=allocated
            item["logical_bytes"]+=logical
            if duplicate:item["hardlink_reused_bytes"]+=logical

    def onerror(_):
        nonlocal skipped
        skipped+=1

    def walk(root,model=False):
        nonlocal partial,skipped
        if root.is_symlink():
            skipped+=1
            return
        if not root.exists():return
        for folder,subdirs,names in os.walk(root,followlinks=False,onerror=onerror):
            if scanned>=max_files or time.monotonic()>stop_at:
                partial=True
                return
            subdirs[:]=[d for d in subdirs if not (Path(folder)/d).is_symlink()]
            if Path(folder)==root and not model:
                priority={name:i for i,name in enumerate(ROOT_ORDER)}
                subdirs.sort(key=lambda name:(priority.get(name,100),name))
            else:subdirs.sort()
            for name in sorted(names):
                if scanned>=max_files or time.monotonic()>stop_at:
                    partial=True
                    return
                file=Path(folder)/name
                parts=file.relative_to(root).parts
                add(file,"models" if model else _kind(parts),
                    None if model else owner(parts))

    walk(data_dir)
    if not partial:walk(models_dir,True)
    if not partial and model_cache_dir is not None:walk(model_cache_dir,True)
    rows=sorted(batches.values(),key=lambda row:(-row["allocated_bytes"],row["batch_id"]))
    return {"categories":groups,"batches":rows[:50],"total_batches":len(rows),
            "unlisted_batches":max(0,len(rows)-50),"files_scanned":scanned,
            "hardlink_paths":sum(g["hardlink_paths"] for g in groups.values()),
            "hardlink_reused_bytes":sum(g["hardlink_reused_bytes"] for g in groups.values()),
            "allocated_total_bytes":sum(g["allocated_bytes"] for g in groups.values()),
            "scan_seconds":round(time.monotonic()-started,2),
            "partial":partial or skipped>0,"skipped_paths":skipped,
            "captured_at":datetime.now(timezone.utc).isoformat(),
            "basis":"st_blocks_512_inode_deduplicated"}

def breakdown():
    """Triggered only by the explicit UI button, never the 20s polling."""
    names,lookup={},{}
    metadata_available=True
    try:names,lookup=_metadata()
    except Exception:metadata_available=False
    report=_scan(DATA_DIR,MODELS_DIR,names,lookup,model_cache_dir=MODEL_CACHE_DIR)
    report["batch_metadata_available"]=metadata_available
    return report
