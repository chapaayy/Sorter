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
def list_work_queue(limit:int=100,offset:int=0,scope:str="active"):
    if not 1<=limit<=200 or offset<0 or scope not in ("active","history","all"):
        raise HTTPException(422,"Неверная выборка очереди")
    where={
        "active":""" WHERE (w.state IN ('queued','running','blocked') OR
                 (w.kind IN ('reference_preparation','layout_preparation') AND w.state IN ('failed','interrupted')))""",
        "history":""" WHERE w.state IN ('completed','completed_with_errors','stopped') OR
                 (w.kind='fo_processing' AND w.state IN ('failed','interrupted'))""",
        "all":""
    }[scope]
    direction="ASC" if scope=="active" else "DESC"
    with connect() as db:
        total=db.execute("SELECT count(*) AS n FROM work_queue w"+where).fetchone()["n"]
        entries=db.execute("""
            SELECT w.seq,w.kind,w.fo_run_id,w.reference_job_id,w.layout_job_id,w.state,
                   w.created_at,w.started_at,w.finished_at,
                   p.session_id,
                   CASE WHEN lp.id IS NOT NULL THEN 100 ELSE p.total_count END AS total_count,
                   CASE WHEN lp.id IS NOT NULL THEN lp.progress_percent ELSE p.completed_count END AS completed_count,
                   CASE WHEN lp.id IS NOT NULL THEN (CASE WHEN lp.state='failed' THEN 1 ELSE 0 END)
                        ELSE p.failed_count END AS failed_count,
                   coalesce(lp.progress_stage,p.progress_stage) AS progress_stage,
                   coalesce(lp.error,p.error) AS error,p.stop_requested,
                   l.name AS layout_name,lp.layout_id,
                   j.batch_id,j.snapshot->>'source' AS fo_source,
                   j.snapshot->'progress' AS fo_progress,
                   b.display_name AS batch_name,b.delete_state AS batch_delete_state,
                   (SELECT count(*)::integer FROM uploads photos
                     WHERE photos.batch_id=j.batch_id AND photos.kind='fo'
                       AND photos.finalized) AS fo_photo_count,
                   cover.thumbnail_id AS fo_thumbnail_id
            FROM work_queue w LEFT JOIN reference_preparation_jobs p
                 ON p.id=w.reference_job_id
            LEFT JOIN ad_layout_preparation_jobs lp ON lp.id=w.layout_job_id
            LEFT JOIN ad_layouts l ON l.id=lp.layout_id
            LEFT JOIN jobs j ON j.id=w.fo_run_id
            LEFT JOIN batches b ON b.id=j.batch_id
            LEFT JOIN LATERAL (
                SELECT u.id AS thumbnail_id
                FROM uploads u JOIN thumbnail_tasks t ON t.upload_id=u.id
                WHERE u.batch_id=j.batch_id AND u.kind='fo' AND u.finalized
                  AND t.state='ready'
                ORDER BY u.created_at,u.id LIMIT 1
            ) cover ON true
            """+where+" ORDER BY w.seq "+direction+" LIMIT %s OFFSET %s",
            (limit,offset)).fetchall()
    for task in entries:
        thumb=task.pop("fo_thumbnail_id")
        task["fo_thumbnail_url"]="/api/thumbnails/"+str(thumb) if thumb else None
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
                UPDATE reference_preparation_jobs SET state='queued',progress_stage='queued',error=NULL,
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

@router.post("/reference-preparations/{job_id}/stop")
def stop_running(job_id:uuid.UUID):
    """Request cooperative cancellation; never silently bypass a publication.

    An interrupted preparation remains a FIFO barrier until explicit retry/skip.
    """
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        prep=db.execute("""
            SELECT state,stop_requested FROM reference_preparation_jobs
            WHERE id=%s FOR UPDATE
        """,(job_id,)).fetchone()
        if not prep:
            raise HTTPException(404,"Подготовка не найдена")
        if prep["state"]=="running":
            db.execute("""
                UPDATE reference_preparation_jobs
                SET stop_requested=true,updated_at=now() WHERE id=%s
            """,(job_id,))
            return {"id":str(job_id),"stop_requested":True,
                    "state":"stopping"}
        if prep["state"]=="interrupted" and prep["stop_requested"]:
            return {"id":str(job_id),"stop_requested":True,
                    "state":"interrupted"}
        raise HTTPException(409,"Остановка доступна только для выполняемой подготовки")

@router.get("/layout-preparations/{job_id}")
def layout_preparation(job_id:uuid.UUID):
    with connect() as db:
        row=db.execute("""SELECT p.*,l.name AS layout_name,w.seq AS queue_seq,
            w.state AS queue_state FROM ad_layout_preparation_jobs p
            JOIN work_queue w ON w.layout_job_id=p.id
            LEFT JOIN ad_layouts l ON l.id=p.layout_id WHERE p.id=%s""",
            (job_id,)).fetchone()
    if not row:raise HTTPException(404,"Подготовка макета не найдена")
    return row

@router.post("/layout-preparations/{job_id}/retry")
def retry_layout(job_id:uuid.UUID):
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        row=db.execute("""SELECT p.state,p.layout_id FROM ad_layout_preparation_jobs p
            WHERE p.id=%s FOR UPDATE""",(job_id,)).fetchone()
        if not row or not row["layout_id"]:
            raise HTTPException(404,"Подготовка макета не найдена")
        if row["state"] not in ("failed","interrupted"):
            raise HTTPException(409,"Повтор доступен только после ошибки")
        db.execute("""UPDATE ad_layout_preparation_jobs SET state='queued',
            progress_stage='queued',progress_percent=0,error=NULL,
            started_at=NULL,finished_at=NULL WHERE id=%s""",(job_id,))
        db.execute("""UPDATE ad_layouts SET preparation_state='queued',
            preparation_stage='queued',preparation_progress=0,
            preparation_error=NULL WHERE id=%s""",(row["layout_id"],))
        db.execute("""UPDATE work_queue SET state='queued',started_at=NULL,
            finished_at=NULL WHERE layout_job_id=%s""",(job_id,))
    return {"id":str(job_id),"state":"queued"}

@router.post("/layout-preparations/{job_id}/skip")
def skip_layout(job_id:uuid.UUID):
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        row=db.execute("""SELECT state,layout_id FROM ad_layout_preparation_jobs
            WHERE id=%s FOR UPDATE""",(job_id,)).fetchone()
        if not row:raise HTTPException(404,"Подготовка макета не найдена")
        if row["state"] not in ("queued","failed","interrupted"):
            raise HTTPException(409,"Выполняемую подготовку пропустить нельзя")
        db.execute("""UPDATE ad_layout_preparation_jobs SET state='stopped',
            progress_stage='stopped',error='Пропущено администратором',
            finished_at=now() WHERE id=%s""",(job_id,))
        db.execute("""UPDATE work_queue SET state='stopped',finished_at=now()
            WHERE layout_job_id=%s""",(job_id,))
        if row["layout_id"]:
            db.execute("""UPDATE ad_layouts SET preparation_state='failed',
                preparation_stage='stopped',preparation_error='Подготовка пропущена'
                WHERE id=%s""",(row["layout_id"],))
    return {"id":str(job_id),"state":"stopped"}
