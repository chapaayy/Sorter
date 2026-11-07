"""Unified read-only queue and explicit, idempotent preparation recovery."""
from __future__ import annotations
import uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from ...database import connect
from ...db.repositories import work_queue
router=APIRouter(prefix="/api",tags=["work-queue"])

class PreparationAction(BaseModel):
    idempotency_key:uuid.UUID

@router.get("/work-queue")
def list_work_queue(limit:int=100,offset:int=0):
    if not 1<=limit<=200 or offset<0:
        raise HTTPException(422,"Неверная пагинация")
    with connect() as db:
        total=db.execute("SELECT count(*) AS n FROM work_queue").fetchone()["n"]
        entries=db.execute("""
            SELECT w.seq,w.kind,w.fo_run_id,w.reference_job_id,w.state,
                   w.created_at,w.started_at,w.finished_at,
                   p.total_count,p.completed_count,p.failed_count,p.error
            FROM work_queue w LEFT JOIN reference_preparation_jobs p
                 ON p.id=w.reference_job_id
            ORDER BY w.seq DESC LIMIT %s OFFSET %s
        """,(limit,offset)).fetchall()
    return {"tasks":entries,"total":total}

@router.get("/reference-preparations/{job_id}")
def get_preparation(job_id:uuid.UUID):
    with connect() as db:
        row=db.execute("""
            SELECT p.*,w.seq AS queue_seq,w.state AS queue_state
            FROM reference_preparation_jobs p JOIN work_queue w
            ON w.reference_job_id=p.id WHERE p.id=%s
        """,(job_id,)).fetchone()
        if not row:
            raise HTTPException(404,"Подготовка не найдена")
        errors=db.execute("""
            SELECT upload_id,detail,occurred_at FROM reference_preparation_errors
            WHERE job_id=%s ORDER BY occurred_at LIMIT 100
        """,(job_id,)).fetchall()
    return {**row,"errors":errors}

def _action(job_id,idempotency_key,action):
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        prep=db.execute("""
            SELECT id,session_id,state FROM reference_preparation_jobs
            WHERE id=%s FOR UPDATE
        """,(job_id,)).fetchone()
        if not prep:raise HTTPException(404,"Подготовка не найдена")
        exists=db.execute("""
            SELECT action FROM reference_preparation_actions
            WHERE job_id=%s AND idempotency_key=%s
        """,(job_id,idempotency_key)).fetchone()
        if exists:
            if exists["action"]!=action:
                raise HTTPException(409,"Ключ действия уже использован")
            return {"id":str(job_id),"state":prep["state"],"already_applied":True}
        if action=="retry":
            if prep["state"] not in ("failed","interrupted"):
                raise HTTPException(409,"Повторить можно только неудачную подготовку")
            db.execute("""
                UPDATE reference_preparation_jobs SET state='queued',error=NULL,
                    completed_count=0,failed_count=0,stop_requested=false,
                    started_at=NULL,finished_at=NULL,updated_at=now()
                WHERE id=%s
            """,(job_id,))
            db.execute("UPDATE work_queue SET state='queued',started_at=NULL,finished_at=NULL WHERE reference_job_id=%s",(job_id,))
            db.execute("UPDATE reference_import_sessions SET preparation_state='queued',error=NULL WHERE id=%s",(prep["session_id"],))
            db.execute("DELETE FROM reference_preparation_errors WHERE job_id=%s",(job_id,))
            state="queued"
        else:
            if prep["state"] not in ("queued","failed","interrupted"):
                raise HTTPException(409,"Нельзя пропустить выполняемую или завершённую подготовку")
            db.execute("""
                UPDATE reference_preparation_jobs SET state='stopped',
                    error='Пропущено администратором',finished_at=now(),updated_at=now()
                WHERE id=%s
            """,(job_id,))
            db.execute("UPDATE work_queue SET state='stopped',finished_at=now() WHERE reference_job_id=%s",(job_id,))
            db.execute("UPDATE reference_import_sessions SET preparation_state='stopped' WHERE id=%s",(prep["session_id"],))
            state="stopped"
        db.execute("""
            INSERT INTO reference_preparation_actions(job_id,idempotency_key,action)
            VALUES (%s,%s,%s)
        """,(job_id,idempotency_key,action))
    return {"id":str(job_id),"state":state,"already_applied":False}

@router.post("/reference-preparations/{job_id}/retry")
def retry(job_id:uuid.UUID,action:PreparationAction):
    return _action(job_id,action.idempotency_key,"retry")

@router.post("/reference-preparations/{job_id}/skip")
def skip(job_id:uuid.UUID,action:PreparationAction):
    return _action(job_id,action.idempotency_key,"skip")
