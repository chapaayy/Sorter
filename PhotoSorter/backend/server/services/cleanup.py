"""Idempotent, batch-ID-scoped deletion; never traverse references or Models."""
from __future__ import annotations
import shutil
import time
from psycopg.types.json import Jsonb
from ..database import connect
from ..storage.batch_cleanup import remove_batch_files
from ..storage.paths import run_dir,owned_directory
from app.config import DATA_DIR,RUNS_DIR
from .batches import uid

IN_USE = ("queued","running","stopping")
PROGRESS_INTERVAL_SECONDS=.1

def request(batch_id, *, only_if_due=False):
    batch_id=uid(batch_id)
    with connect() as db:
        # Same queue gate as creating a job, and per-batch lock as uploading.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        batch=db.execute("SELECT delete_state,download_confirmed_at,delete_after_at FROM batches WHERE id=%s FOR UPDATE",
                         (batch_id,)).fetchone()
        if not batch: return {"batch_id":str(batch_id),"state":"not_found"}
        if only_if_due:
            # Recheck inside the queue lock: retention may have been disabled.
            due=db.execute("""SELECT 1 FROM batches WHERE id=%s
                AND delete_state='active' AND delete_after_at<=now()
                AND EXISTS (SELECT 1 FROM retention_preferences
                            WHERE id=1 AND enabled)""",(batch_id,)).fetchone()
            if not due:return {"batch_id":str(batch_id),"state":"skipped"}
        if batch["delete_state"]=="deleted":
            return {"batch_id":str(batch_id),"state":"deleted"}
        if batch["delete_state"]=="deleting":
            return {"batch_id":str(batch_id),"state":"deleting"}
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
        db.execute("""INSERT INTO cleanup_tasks(batch_id,state,progress) VALUES (%s,'pending',%s)
            ON CONFLICT(batch_id) DO UPDATE SET state='pending',error=NULL,
            progress=EXCLUDED.progress,updated_at=now()""",(batch_id,_progress("queued")))
    return {"batch_id":str(batch_id),"state":"deleting"}

def get_status(batch_id):
    batch_id=uid(batch_id)
    with connect() as db:
        batch=db.execute("""
            SELECT b.delete_state,b.deleted_at,
                CASE WHEN c.batch_id IS NOT NULL THEN jsonb_build_object(
                    'state',c.state,'attempts',c.attempts,'error',c.error,
                    'completed_at',c.completed_at,'progress',c.progress)
                END AS task
            FROM batches b LEFT JOIN cleanup_tasks c ON c.batch_id=b.id
            WHERE b.id=%s
        """,(batch_id,)).fetchone()
        if not batch:return {"state":"not_found","batch_id":str(batch_id)}
    return {"batch_id":str(batch_id),**batch}

def _progress(phase,done=0,total=None):
    return Jsonb({"phase":phase,"done":done,"total":total})

def _save_progress(db,batch_id,snapshot):
    db.execute("""UPDATE cleanup_tasks SET progress=%s,updated_at=now()
        WHERE batch_id=%s""",(snapshot,batch_id))

def _files(batch_id,run_ids,upload_ids,report):
    return remove_batch_files(batch_id,run_ids,upload_ids,DATA_DIR,RUNS_DIR,report)

def _reporter(db,batch_id):
    last_phase=None
    last_update=0.0
    def report(phase,done=0,total=None):
        nonlocal last_phase,last_update
        now=time.monotonic()
        checkpoint=phase=="files" and done in (1,total-1)
        if phase==last_phase and not checkpoint and now-last_update<PROGRESS_INTERVAL_SECONDS:
            return
        _save_progress(db,batch_id,_progress(phase,done,total))
        db.commit()
        last_phase,last_update=phase,now
    return report

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
                _save_progress(db,batch_id,_progress("stopping_jobs" if active else "waiting_operations"))
                db.commit()
                return "waiting"
            jobs=db.execute("SELECT id FROM jobs WHERE batch_id=%s",(batch_id,)).fetchall()
            files=db.execute("SELECT id FROM uploads WHERE batch_id=%s",(batch_id,)).fetchall()
            db.execute("""UPDATE cleanup_tasks SET state='running',
                attempts=attempts+1,progress=%s,updated_at=now() WHERE batch_id=%s""",
                (_progress("scanning"),batch_id))
            db.commit()
            try:
                report=_reporter(db,batch_id)
                total=_files(batch_id,[r["id"] for r in jobs],[r["id"] for r in files],report)
                report("database",total-1,total)
                # Repeatable: if previous run deleted paths and crashed, this is harmless.
                db.execute("DELETE FROM download_confirmations WHERE batch_id=%s",(batch_id,))
                db.execute("DELETE FROM uploads WHERE batch_id=%s",(batch_id,))
                db.execute("DELETE FROM jobs WHERE batch_id=%s",(batch_id,))
                db.execute("""UPDATE batches SET delete_state='deleted',deleted_at=now(),
                    download_confirmed_at=NULL,confirmed_run_id=NULL,delete_after_at=NULL
                    WHERE id=%s""",(batch_id,))
                db.execute("""UPDATE cleanup_tasks SET state='completed',
                    completed_at=now(),error=NULL,progress=%s,updated_at=now() WHERE batch_id=%s""",
                    (_progress("completed",total,total),batch_id))
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
            WHERE state IN ('pending','running')
            ORDER BY updated_at,requested_at,batch_id LIMIT %s""",
            (limit,)).fetchall()
    return [(str(r["batch_id"]),cleanup_one(r["batch_id"])) for r in rows]

def reconcile_incomplete_exports(limit=100, grace_seconds=3600):
    """Remove stale unpublished staging only for confirmed terminal runs.

    No generic recursive temp purge: a running inference may still be writing.
    """
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
