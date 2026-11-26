"""Fixed lifecycle actions; preview is read-only and execution rechecks leases.

No paths or shell commands from HTTP, no general-purpose cache deletion.
"""
import logging
from fastapi import HTTPException
from ..database import connect
from app.storage.categories import ARCHIVE_TTL_SECONDS,TEMPORARY_GRACE_SECONDS
from app import config
from ..storage.accounting import snapshot

KINDS={
 "expired_archives":(("zip_results","zip_construction","zip_references","zip_fragment","archive_lock"),ARCHIVE_TTL_SECONDS),
 "unused_thumbnails":(("fo_thumbnail","reference_thumbnail"),86400),
 "abandoned_scratch":(("scratch","atomic_fragment","model_download"),TEMPORARY_GRACE_SECONDS),
}
LOCK=723409191

def preview(kind):
    if kind not in KINDS:raise HTTPException(422,"Недопустимая операция")
    categories,seconds=KINDS[kind]
    with connect() as db:
        # Age-based upper estimate only. Existing GC owns dependency/lease
        # checks and may remove fewer or no candidates.
        row=db.execute("""SELECT count(*) AS files,coalesce(sum(physical_bytes),0)::bigint AS allocated_bytes
          FROM storage_accounted_files WHERE category=ANY(%s) AND kind='file' AND issue IS NULL
          AND mtime_ns<=extract(epoch FROM now())*1000000000-%s*1000000000::numeric""",
          (list(categories),seconds)).fetchone()
    data=snapshot()
    return dict(row,kind=kind,sampled_at=data["sampled_at"],partial=data["partial"],
                basis="age_based_observed_candidates_not_guaranteed_reclaim")

def host_preview(kind):
    if kind=="storage-cache":
        data=snapshot()
        row=data.get("categories",{}).get("technical_cache")
        return {"kind":kind,"files":row["files"] if row else (0 if data["sampled_at"] else None),
            "allocated_bytes":row["allocated_bytes"] if row else (0 if data["sampled_at"] else None),
            "sampled_at":data["sampled_at"],"partial":data["partial"],
            "basis":"typed_provider_cache_offline_only"}
    if kind=="storage-logs":
        from .storage_usage import _host
        from app.storage.categories import LOG_BUDGETS_MIB
        report=_host("log-usage.json")
        row=report.get("services",{}).get("postgres",{})
        logical=row.get("bytes")
        return {"kind":kind,"files":None,"allocated_bytes":None,
            "logical_excess_bytes":max(0,logical-LOG_BUDGETS_MIB["postgres"]*1024*1024) if logical is not None else None,
            "sampled_at":report.get("at"),"partial":row.get("partial",True),
            "basis":"postgres_closed_segments_over_budget_only"}
    raise HTTPException(422,"Недопустимая операция")

def status():
    with connect() as db:
        return db.execute("SELECT * FROM storage_maintenance ORDER BY kind").fetchall()

def enqueue(kind,confirmed):
    if kind not in KINDS or confirmed is not True:raise HTTPException(422,"Требуется подтверждение разрешённой операции")
    with connect() as db:
        row=db.execute("""INSERT INTO storage_maintenance(kind,state) VALUES(%s,'queued')
          ON CONFLICT(kind) DO UPDATE SET state='queued',requested_at=now(),started_at=NULL,
          finished_at=NULL,removed=NULL,detail=NULL,available_delta_bytes=NULL WHERE storage_maintenance.state NOT IN ('queued','running')
          RETURNING *""",(kind,)).fetchone()
        if not row:row=db.execute("SELECT * FROM storage_maintenance WHERE kind=%s",(kind,)).fetchone()
    return row

def run_pending():
    # Only the cleanup worker runs these existing routines. Session lock
    # prevents multiple workers and releases on death; an interrupted action
    # is reported, not silently replayed as a successful delete.
    with connect() as db:
        if not db.execute("SELECT pg_try_advisory_lock(%s) AS ok",(LOCK,)).fetchone()["ok"]:return
        db.execute("""UPDATE storage_maintenance SET state='interrupted',finished_at=now(),detail='worker_interrupted'
          WHERE state='running'""")
        row=db.execute("""SELECT kind FROM storage_maintenance WHERE state='queued'
          ORDER BY requested_at,kind LIMIT 1 FOR UPDATE""").fetchone()
        if not row:return
        kind=row["kind"]
        db.execute("UPDATE storage_maintenance SET state='running',started_at=now() WHERE kind=%s",(kind,))
        db.commit()
        before=None
        try:
            from ..storage.accounting import disk
            before=disk()["available_bytes"]
            if kind=="expired_archives":
                from .archive_cache import collect
                removed=collect()
            elif kind=="unused_thumbnails":
                from .thumbnails import gc_unowned
                removed=gc_unowned(limit=200)
            elif kind=="abandoned_scratch":
                from app.storage.temporary import collect_abandoned
                removed=collect_abandoned(config.APP_STORAGE_ROOT,limit=100)
            else:raise ValueError("Unexpected maintenance kind")
        except Exception:
            logging.exception("Storage maintenance action failed")
            db.execute("UPDATE storage_maintenance SET state='failed',finished_at=now(),detail='cleanup_failed' WHERE kind=%s",(kind,))
        else:
            try:delta=disk()["available_bytes"]-before
            except OSError:delta=None
            db.execute("UPDATE storage_maintenance SET state='completed',finished_at=now(),removed=%s,available_delta_bytes=%s WHERE kind=%s",(removed,delta,kind))
