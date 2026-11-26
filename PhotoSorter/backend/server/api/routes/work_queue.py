"""Unified read-only queue and explicit, idempotent preparation recovery."""
from __future__ import annotations
import uuid
from fastapi import APIRouter,HTTPException,Request
from ...security.access_policy import current_user,is_owner
from ...security.roles import has
from ...security.route_permissions import owner_filter
from pydantic import BaseModel
from ...database import connect
from ...db.repositories import work_queue
router=APIRouter(prefix="/api",tags=["work-queue"])

class PreparationAction(BaseModel):
    idempotency_key:uuid.UUID

@router.get("/work-queue")
def list_work_queue(limit:int=100,offset:int=0,scope:str="active",request:Request=None):
    if not 1<=limit<=200 or offset<0 or scope not in ("active","history","all"):
        raise HTTPException(422,"Неверная выборка очереди")
    where={
        "active":""" WHERE (w.state IN ('queued','running','blocked') OR
                 (w.kind='reference_preparation' AND w.state IN ('failed','interrupted')))""",
        "history":""" WHERE w.state IN ('completed','completed_with_errors','stopped') OR
                 (w.kind IN ('fo_processing','media_preparation','reference_deletion')
                  AND w.state IN ('failed','interrupted'))""",
        "all":""
    }[scope]
    user=current_user(request)
    owner=owner_filter(user,"queue.view")
    shared=not user or is_owner(user) or has(user,"queue.shared")
    clause="((coalesce(j.batch_id,w.media_batch_id) IS NOT NULL AND (%s::bigint IS NULL OR b.owner_id=%s)) OR (%s AND coalesce(j.batch_id,w.media_batch_id) IS NULL))"
    where=(" WHERE ("+where.removeprefix(" WHERE ")+") AND "+clause) if where else " WHERE "+clause
    args=(owner,owner,shared)
    direction="ASC" if scope=="active" else "DESC"
    with connect() as db:
        total=db.execute("SELECT count(*) AS n FROM work_queue w LEFT JOIN jobs j ON j.id=w.fo_run_id LEFT JOIN batches b ON b.id=coalesce(j.batch_id,w.media_batch_id)"+where,args).fetchone()["n"]
        entries=db.execute("""
            SELECT w.seq,w.kind,w.fo_run_id,w.reference_job_id,w.media_batch_id,w.reference_deletion_id,
                   d.sam AS deletion_sam,d.reference_id AS deletion_photo_id,w.state,
                   w.created_at,w.started_at,w.finished_at,
                   p.session_id,coalesce(w.media_total_count,p.total_count) AS total_count,
                   coalesce(w.media_completed_count,p.completed_count) AS completed_count,
                   coalesce(w.media_failed_count,p.failed_count) AS failed_count,
                   coalesce(w.media_error,p.error,d.error) AS error,p.stop_requested,
                   coalesce(j.batch_id,w.media_batch_id) AS batch_id,j.snapshot->>'source' AS fo_source,
                   j.snapshot->'progress' AS fo_progress,j.snapshot->'selected_regions' AS fo_selected_regions,
                   w.media_progress_percent,w.media_eta_seconds,w.media_current_file,
                   b.owner_id::text AS owner_id,b.display_name AS batch_name,b.delete_state AS batch_delete_state,
                   c.progress AS batch_deletion_progress,
                   (SELECT count(*)::integer FROM uploads photos
                     WHERE photos.batch_id=j.batch_id AND photos.kind='fo'
                       AND photos.finalized AND (photos.original_media_type IS NULL OR photos.media_action IS NOT NULL)) AS fo_photo_count,
                   cover.thumbnail_id AS fo_thumbnail_id
            FROM work_queue w LEFT JOIN reference_preparation_jobs p
                 ON p.id=w.reference_job_id
            LEFT JOIN reference_deletion_tasks d ON d.id=w.reference_deletion_id
            LEFT JOIN jobs j ON j.id=w.fo_run_id
            LEFT JOIN batches b ON b.id=coalesce(j.batch_id,w.media_batch_id)
            LEFT JOIN cleanup_tasks c ON c.batch_id=b.id
            LEFT JOIN LATERAL (
                SELECT u.id AS thumbnail_id
                FROM uploads u JOIN thumbnail_tasks t ON t.upload_id=u.id
                WHERE u.batch_id=j.batch_id AND u.kind='fo' AND u.finalized
                  AND t.state='ready'
                ORDER BY u.created_at,u.id LIMIT 1
            ) cover ON true
            """+where+" ORDER BY w.seq "+direction+" LIMIT %s OFFSET %s",
            (*args,limit,offset)).fetchall()
    for task in entries:
        thumb=task.pop("fo_thumbnail_id")
        task["fo_thumbnail_url"]="/api/thumbnails/"+str(thumb) if thumb and (not user or is_owner(user) or (has(user,"photos.view") and has(user,"photos.media"))) else None
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
            from ...services.reference_gc import mark_candidates
            mark_candidates(db)
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
