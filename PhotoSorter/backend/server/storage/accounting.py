"""Registry-backed totals; physical, logical and prospective charge are independent."""
from __future__ import annotations
import os,json
from pathlib import Path
from psycopg.types.json import Jsonb
from ..database import connect
from app import config
from ..services.disk_guard import reserve

SUMS="""count(*) AS files,coalesce(sum(logical_bytes),0)::bigint AS logical_bytes,
 coalesce(sum(physical_bytes),0)::bigint AS allocated_bytes,
 coalesce(sum(charged_bytes),0)::bigint AS charged_bytes,
 count(*) FILTER(WHERE physical_rank>1) AS hardlink_paths,
 coalesce(sum(logical_bytes) FILTER(WHERE physical_rank>1),0)::bigint AS hardlink_reused_bytes"""
def aggregate(db):
    categories={r.pop("category"):r for r in db.execute("SELECT category,"+SUMS+" FROM storage_accounted_files GROUP BY category")}
    owners={str(r.pop("owner_id")):r for r in db.execute("SELECT owner_id,"+SUMS+" FROM storage_accounted_files WHERE scope='personal' AND owner_id IS NOT NULL GROUP BY owner_id")}
    temporary=db.execute("SELECT "+SUMS+" FROM storage_accounted_files WHERE scope='temporary'").fetchone()
    issues={r["issue"]:r["n"] for r in db.execute("SELECT issue,count(*) AS n FROM storage_files WHERE issue IS NOT NULL GROUP BY issue")}
    # Existing business metadata is the expected-file index, not copied into a second table.
    missing=db.execute("""SELECT count(*) AS n FROM (
      SELECT target_path AS path FROM uploads WHERE finalized AND target_path IS NOT NULL
      UNION SELECT media_output_path FROM uploads WHERE media_output_path IS NOT NULL
      UNION SELECT cache_path FROM reference_cache
    ) e WHERE starts_with(e.path,%s) AND NOT EXISTS
      (SELECT 1 FROM storage_files f WHERE f.path='app/'||substr(e.path,%s))""",
      (str(config.APP_STORAGE_ROOT)+"/",len(str(config.APP_STORAGE_ROOT))+2)).fetchone()["n"]
    conflicts=db.execute("""SELECT count(*) AS n FROM (
      SELECT device,inode FROM storage_files WHERE scope='personal' GROUP BY device,inode
      HAVING count(DISTINCT owner_id)>1) x""").fetchone()["n"]
    reserved=db.execute("SELECT coalesce(sum(requested_bytes),0)::bigint AS bytes FROM storage_reservations").fetchone()["bytes"]
    return {"categories":categories,"owners":owners,"temporary":temporary,"issues":issues,
            "missing_expected":missing,"cross_owner_inode_conflicts":conflicts,"reserved_bytes":reserved,
            "allocated_bytes":sum(r["allocated_bytes"] for r in categories.values()),
            "logical_bytes":sum(r["logical_bytes"] for r in categories.values())}
def refresh(db):
    # A single SQL aggregate snapshot for all consumers; no disk traversal on GET.
    row=db.execute("SELECT sampled_at,now()-sampled_at<interval '15 seconds' AS fresh FROM storage_accounting_state").fetchone()
    if row["fresh"]:return
    summary=aggregate(db)
    db.execute("""UPDATE storage_accounting_state SET summary=%s,sampled_at=now(),
      temporary_peak_bytes=greatest(temporary_peak_bytes,%s)""",(Jsonb(summary),summary["temporary"]["allocated_bytes"]))
def snapshot():
    with connect() as db:
        row=db.execute("SELECT * FROM storage_accounting_state").fetchone()
        pending=db.execute("SELECT count(*) AS n FROM storage_dirty").fetchone()["n"]
    summary=dict(row["summary"])
    for field in ("sampled_at","reconciled_at","started_at"):
        summary[field]=row[field].isoformat() if row[field] else None
    summary.update(pending_changes=pending,errors=row["errors"],temporary_peak_bytes=row["temporary_peak_bytes"],
                   partial=row["reconciled_at"] is None or bool(row["errors"]))
    return summary
def disk():
    fs=os.statvfs(config.APP_STORAGE_ROOT)
    total=fs.f_frsize*fs.f_blocks;free=fs.f_frsize*fs.f_bavail
    used=total-fs.f_frsize*fs.f_bfree
    return {"device":os.stat(config.APP_STORAGE_ROOT).st_dev,"total_bytes":total,"used_bytes":used,
            "available_bytes":free,"reserved_bytes":reserve(total),"admission_ok":free>reserve(total),
            "used_fraction":used/total if total else 0,"warning":"critical" if used>=total*.90 else "warning" if used>=total*.80 else None}
