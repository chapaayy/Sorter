"""Idempotent, batch-ID-scoped deletion; never traverse references or Models."""
from __future__ import annotations
import shutil
from pathlib import Path
from ..database import connect
from ..storage.paths import batch_dir,run_dir,owned_directory,owned_file
from app.config import DATA_DIR,RUNS_DIR
from .batches import uid

IN_USE = ("queued","running","stopping")

def request(batch_id, *, only_if_due=False):
    batch_id=uid(batch_id)
    with connect() as db:
        # Same queue gate as creating a job, and per-batch lock as uploading.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        batch=db.execute("SELECT delete_state,download_confirmed_at,delete_after_at FROM batches WHERE id=%s FOR UPDATE",
                         (batch_id,)).fetchone()
        if not batch: return {"batch_id":str(batch_id),"state":"not_found"}
        if only_if_due:
            due=db.execute("""SELECT 1 FROM batches WHERE id=%s
                AND delete_state='active' AND download_confirmed_at IS NOT NULL
                AND delete_after_at<=now()""",(batch_id,)).fetchone()
            if not due:return {"batch_id":str(batch_id),"state":"skipped"}
        if batch["delete_state"]=="deleted":
            return {"batch_id":str(batch_id),"state":"deleted"}
        db.execute("""UPDATE batches SET delete_state='deleting',
            delete_after_at=NULL WHERE id=%s""",(batch_id,))
        db.execute("""UPDATE jobs SET
            stop_requested=true,
            status=CASE WHEN status='queued' THEN 'stopped' ELSE 'stopping' END,
            snapshot=jsonb_set(snapshot,'{status}',
               to_jsonb(CASE WHEN status='queued' THEN 'stopped' ELSE 'stopping' END)),
            updated_at=now()
            WHERE batch_id=%s AND status IN ('queued','running','stopping')""",(batch_id,))
        db.execute("""UPDATE work_queue w SET state='stopped',finished_at=now()
            FROM jobs j WHERE w.fo_run_id=j.id AND j.batch_id=%s
            AND w.state='queued' AND j.status='stopped'""",(batch_id,))
        db.execute("""INSERT INTO cleanup_tasks(batch_id,state) VALUES (%s,'pending')
            ON CONFLICT(batch_id) DO UPDATE SET state='pending',error=NULL,
            updated_at=now()""",(batch_id,))
    return {"batch_id":str(batch_id),"state":"deleting"}

def get_status(batch_id):
    batch_id=uid(batch_id)
    with connect() as db:
        batch=db.execute("SELECT delete_state,deleted_at FROM batches WHERE id=%s",
                         (batch_id,)).fetchone()
        if not batch:return {"state":"not_found","batch_id":str(batch_id)}
        task=db.execute("""SELECT state,attempts,error,completed_at FROM cleanup_tasks
            WHERE batch_id=%s""",(batch_id,)).fetchone()
    return {"batch_id":str(batch_id),**batch,"task":task}

def _rmdir(root, location):
    path=owned_directory(location,root)
    if path.exists():
        shutil.rmtree(path)

def _files(batch_id,run_ids,upload_ids):
    # Names derive solely from verified DB UUIDs/run IDs, never from client paths.
    for run_id in run_ids:
        _rmdir(DATA_DIR/"outputs",run_dir(run_id))
        _rmdir(RUNS_DIR,run_dir(run_id,RUNS_DIR))
    for upload_id in upload_ids:
        path=owned_file(DATA_DIR/"incoming"/f"{upload_id}.part",DATA_DIR/"incoming")
        path.unlink(missing_ok=True)
    _rmdir(DATA_DIR/"uploads",batch_dir(batch_id))

def cleanup_one(batch_id):
    batch_id=uid(batch_id)
    with connect() as db:
        # Session-level lock held across all filesystem and DB steps.
        locked=db.execute("SELECT pg_try_advisory_lock(714932,hashtext(%s))",
                          (str(batch_id),)).fetchone()
        if not locked or not next(iter(locked.values())):
            return "busy"
        try:
            batch=db.execute("SELECT delete_state FROM batches WHERE id=%s FOR UPDATE",
                             (batch_id,)).fetchone()
            if not batch or batch["delete_state"] not in ("deleting","delete_failed"):
                db.commit()
                return "skipped"
            # Crash recovery: abandoned IO leases cannot block cleanup forever.
            db.execute("""DELETE FROM batch_operations WHERE batch_id=%s
                AND heartbeat_at<now()-interval '12 hours'""",(batch_id,))
            active=db.execute("""SELECT 1 FROM jobs WHERE batch_id=%s AND
                status IN ('queued','running','stopping') LIMIT 1""",(batch_id,)).fetchone()
            leases=db.execute("SELECT 1 FROM batch_operations WHERE batch_id=%s LIMIT 1",
                              (batch_id,)).fetchone()
            if active or leases:
                db.commit()
                return "waiting"
            jobs=db.execute("SELECT id FROM jobs WHERE batch_id=%s",(batch_id,)).fetchall()
            files=db.execute("SELECT id FROM uploads WHERE batch_id=%s",(batch_id,)).fetchall()
            db.execute("""UPDATE cleanup_tasks SET state='running',
                attempts=attempts+1,updated_at=now() WHERE batch_id=%s""",(batch_id,))
            db.commit()
            try:
                _files(batch_id,[r["id"] for r in jobs],[r["id"] for r in files])
                # Repeatable: if previous run deleted paths and crashed, this is harmless.
                db.execute("DELETE FROM download_confirmations WHERE batch_id=%s",(batch_id,))
                db.execute("DELETE FROM uploads WHERE batch_id=%s",(batch_id,))
                db.execute("DELETE FROM jobs WHERE batch_id=%s",(batch_id,))
                db.execute("""UPDATE batches SET delete_state='deleted',deleted_at=now(),
                    download_confirmed_at=NULL,confirmed_run_id=NULL,delete_after_at=NULL
                    WHERE id=%s""",(batch_id,))
                db.execute("""UPDATE cleanup_tasks SET state='completed',
                    completed_at=now(),error=NULL,updated_at=now() WHERE batch_id=%s""",
                    (batch_id,))
                db.commit()
                return "completed"
            except Exception as exc:
                db.rollback()
                db.execute("UPDATE batches SET delete_state='delete_failed' WHERE id=%s",
                           (batch_id,))
                db.execute("""UPDATE cleanup_tasks SET state='failed',error=%s,
                    updated_at=now() WHERE batch_id=%s""",
                    (f"{type(exc).__name__}: {exc}"[:1000],batch_id))
                db.commit()
                return "failed"
        finally:
            db.execute("SELECT pg_advisory_unlock(714932,hashtext(%s))",(str(batch_id),))
            db.commit()

def process_pending(limit=20):
    with connect() as db:
        rows=db.execute("""SELECT batch_id FROM cleanup_tasks
            WHERE state IN ('pending','running') ORDER BY requested_at LIMIT %s""",
            (limit,)).fetchall()
    return [(str(r["batch_id"]),cleanup_one(r["batch_id"])) for r in rows]

def reconcile_incomplete_exports(limit=100, grace_seconds=3600):
    """Remove stale unpublished staging only for confirmed terminal runs.

    No generic recursive temp purge: a running inference may still be writing.
    """
    import time
    from ..storage.paths import owned_directory
    with connect() as db:
        rows=db.execute("""SELECT j.id FROM jobs j
             WHERE j.status IN ('completed','completed_with_errors','failed',
                                'interrupted','stopped')
             ORDER BY j.updated_at DESC LIMIT %s""",(limit,)).fetchall()
    removed=[]
    for record in rows:
        try:
            staging=run_dir(record["id"])/".megaloc.building"
            staging=owned_directory(staging,DATA_DIR/"outputs")
            if not staging.is_dir():continue
            if time.time()-staging.stat().st_mtime<grace_seconds:continue
            # A late worker update must not race the final cleanup decision.
            with connect() as db:
                current=db.execute("SELECT status FROM jobs WHERE id=%s",(record["id"],)).fetchone()
                if not current or current["status"] in IN_USE:continue
                if db.execute("""SELECT 1 FROM batch_operations b
                    JOIN jobs j ON j.batch_id=b.batch_id WHERE j.id=%s LIMIT 1""",
                    (record["id"],)).fetchone():continue
            shutil.rmtree(staging)
            removed.append(record["id"])
        except (OSError,ValueError):
            # Never delete an untrusted or inaccessible path; leave for inspection.
            continue
    return removed
