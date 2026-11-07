"""ZIP-only recovery: durable request, no rerun of CPU inference.

The housekeeping worker owns this queue independently of the MegaLoc FIFO,
because regenerating a saved ZIP uses disk IO, not MegaLoc.
"""
from __future__ import annotations
import logging
from datetime import datetime,timezone
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from app.results.repository import run_path
from ..database import connect
from . import operations

log=logging.getLogger(__name__)

def _available(run_id:str)->bool:
    """Cheap structural check; full CRCs are verified before publishing."""
    from . import archives
    from .archive_pipeline import selections
    try:
        return archives.existing(run_id,None,selections(run_id)) is not None
    except (OSError,ValueError,HTTPException):
        return False

def archive_status(run_id:str):
    with connect() as db:
        row=db.execute("SELECT status,snapshot FROM jobs WHERE id=%s",(run_id,)).fetchone()
    if not row:raise HTTPException(404,"Запуск не найден")
    snapshot=row["snapshot"]
    state=snapshot.get("archive_state") or "legacy"
    if state=="ready" and not _available(run_id):
        state="missing"
    model=snapshot.get("models",{}).get("megaloc",{})
    can_retry=model.get("status")=="completed" and (
        (state=="failed" and row["status"] in ("failed","interrupted")) or
        (state=="missing" and row["status"] in ("completed","completed_with_errors")))
    return {"run_id":run_id,"state":state,"can_retry":can_retry}

def request(run_id:str):
    try:run_path(run_id)
    except FileNotFoundError:raise HTTPException(404,"Запуск не найден")
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        row=db.execute("""SELECT j.id,j.batch_id,j.status,j.snapshot,b.delete_state
            FROM jobs j JOIN batches b ON b.id=j.batch_id
            WHERE j.id=%s FOR UPDATE OF j,b""",(run_id,)).fetchone()
        if not row:raise HTTPException(404,"Запуск не найден")
        if row["delete_state"]!="active":
            raise HTTPException(409,"Партия удаляется")
        snapshot=row["snapshot"]
        failed= (row["status"] in ("failed","interrupted") and
                 snapshot.get("archive_state")=="failed")
        # A previously completed ZIP may disappear after a storage incident.
        # Recover it from the saved MegaLoc results, never rerun inference.
        missing=(row["status"] in ("completed","completed_with_errors") and
                 snapshot.get("archive_state")=="ready")
        if not failed and not missing:
            raise HTTPException(409,"Повторная подготовка архива сейчас недоступна")
        if snapshot.get("models",{}).get("megaloc",{}).get("status")!="completed":
            raise HTTPException(409,"Нет завершённых результатов MegaLoc")
        if missing:
            if _available(run_id):
                raise HTTPException(409,"Полный ZIP уже готов")
            info=dict(snapshot)
            info.update(status="failed",archive_state="failed",
                        error="Полный ZIP отсутствует или повреждён")
            db.execute("""UPDATE jobs SET status='failed',snapshot=%s,
                 finished_at=now(),updated_at=now() WHERE id=%s""",
                 (Jsonb(info),run_id))
            db.execute("""UPDATE work_queue SET state='failed',finished_at=now()
                 WHERE fo_run_id=%s AND state IN ('completed','completed_with_errors')""",
                 (run_id,))
        task=db.execute("SELECT state FROM archive_retries WHERE run_id=%s FOR UPDATE",(run_id,)).fetchone()
        if task and task["state"] in ("pending","running"):
            return {"run_id":run_id,"state":task["state"]}
        # ZIP is rebuilt from the published manifest, no changes to original photos.
        db.execute("""INSERT INTO archive_retries(run_id,batch_id,state)
             VALUES (%s,%s,'pending')
             ON CONFLICT(run_id) DO UPDATE SET state='pending',error=NULL,
                 requested_at=now(),updated_at=now(),finished_at=NULL""",
             (run_id,row["batch_id"]))
    return {"run_id":run_id,"state":"pending"}

def _claim():
    with connect() as db:
        row=db.execute("""SELECT r.run_id,r.batch_id FROM archive_retries r
            JOIN batches b ON b.id=r.batch_id
            WHERE b.delete_state='active' AND
             (r.state='pending' OR
               (r.state='running' AND r.updated_at<now()-interval '30 minutes'))
            ORDER BY r.requested_at FOR UPDATE OF r SKIP LOCKED LIMIT 1""").fetchone()
        if row:
            db.execute("""UPDATE archive_retries SET state='running',
                updated_at=now(),error=NULL WHERE run_id=%s""",(row["run_id"],))
        return row

def _finish(run_id,state,error=None):
    with connect() as db:
        db.execute("""UPDATE archive_retries SET state=%s,error=%s,
             finished_at=now(),updated_at=now() WHERE run_id=%s""",
             (state,error,run_id))

def process_pending(limit=1):
    from ..jobs import ServerJob
    from .archive_pipeline import build_for_job
    done=[]
    for _ in range(limit):
        task=_claim()
        if not task:break
        run_id=task["run_id"]
        lease=None
        job=None
        try:
            lease=operations.start(task["batch_id"],"archive_retry")
            with connect() as db:
                row=db.execute("SELECT snapshot FROM jobs WHERE id=%s FOR UPDATE",(run_id,)).fetchone()
                if not row:raise RuntimeError("Запуск удалён")
                info=dict(row["snapshot"])
                if info.get("archive_state") not in ("failed","preparing"):
                    raise RuntimeError("Архив не нуждается в подготовке")
                info.update(status="running",archive_state="preparing",archive_retry=True)
                info.pop("error",None)
                db.execute("""UPDATE jobs SET status='running',stop_requested=false,
                  snapshot=%s,updated_at=now(),finished_at=NULL WHERE id=%s""",
                  (Jsonb(info),run_id))
            job=ServerJob(info)
            job.started_monotonic=__import__("time").monotonic()
            job.save()
            build_for_job(job)
            job.info["status"]="completed"
            job.info["finished_at"]=datetime.now(timezone.utc).isoformat()
            job.info["progress"]["overall_percent"]=100.0
            job.info["progress"]["estimated_remaining_seconds"]=0.0
            job.info["progress"]["eta_status"]="completed"
            job.save()
            with connect() as db:
                db.execute("""UPDATE work_queue SET state='completed',finished_at=now()
                    WHERE fo_run_id=%s AND state IN ('failed','interrupted')""",(run_id,))
            _finish(run_id,"completed")
            done.append((run_id,"completed"))
        except Exception as exc:
            log.exception("ZIP-only retry failed for %s",run_id)
            reason=f"{type(exc).__name__}: {exc}"[:800]
            if job:
                job.info.update(status="failed",archive_state="failed",error=reason,
                    finished_at=datetime.now(timezone.utc).isoformat())
                try:job.save()
                except Exception:log.exception("Could not save ZIP retry failure")
            _finish(run_id,"failed",reason)
            done.append((run_id,"failed"))
        finally:
            if lease:operations.finish(lease)
    return done
