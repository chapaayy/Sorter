"""MegaLoc queue REST API; PostgreSQL serializes scheduling, never invent progress."""
from __future__ import annotations
import time,uuid
from datetime import datetime,timezone
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from psycopg.types.json import Jsonb
from app.config import DATA_DIR
from app.jobs.runtime import Job
from .database import connect,save_snapshot
from .db.repositories import queue

router=APIRouter(prefix="/api/runs",tags=["jobs"])
TERMINAL=set(queue.TERMINAL)

class NewRun(BaseModel):
    batch_id:uuid.UUID
    grouping_threshold:float=Field(default=.50,ge=.50,le=.99,allow_inf_nan=False)

@router.get("")
def list_jobs(limit:int=100,offset:int=0):
    if limit<1 or limit>200 or offset<0:raise HTTPException(422,"Неверная пагинация")
    with connect() as db:
        rows=db.execute("""SELECT id,snapshot,status,created_at,started_at,finished_at
            FROM jobs ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s""",
            (limit,offset)).fetchall()
        total=db.execute("SELECT count(*) AS n FROM jobs").fetchone()["n"]
        result=[queue.decorated(db,row) for row in rows]
    return {"runs":result,"total":total}

@router.post("",status_code=202)
def enqueue(data:NewRun):
    with connect() as db:
        # Shared with manual batch deletion and reference mutation.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        if queue.queue_count(db)>=queue.MAX_WAITING:
            raise HTTPException(429,"Очередь заполнена: максимум 20 ожидающих запусков")
        batch=db.execute("SELECT id,delete_state,upload_manifest_state FROM batches WHERE id=%s FOR UPDATE",
                         (data.batch_id,)).fetchone()
        if not batch:raise HTTPException(404,"Партия ФО не найдена")
        if batch["delete_state"]!="active":raise HTTPException(409,"Партия удаляется")
        if batch['upload_manifest_state']=='waiting':
            raise HTTPException(422,'Дождитесь завершения всех файлов манифеста ФО')
        if db.execute("""SELECT 1 FROM jobs WHERE batch_id=%s
                   AND status IN ('queued','running','stopping') LIMIT 1""",
                   (data.batch_id,)).fetchone():
            raise HTTPException(409,"Эта партия уже стоит в очереди или обрабатывается")
        count=db.execute("""SELECT count(*) AS n FROM uploads
            WHERE kind='fo' AND finalized AND batch_id=%s""",(data.batch_id,)).fetchone()["n"]
        pending=db.execute("""SELECT count(*) AS n FROM uploads
            WHERE kind='fo' AND batch_id=%s AND NOT finalized""",
            (data.batch_id,)).fetchone()["n"]
        if pending:raise HTTPException(422,"Дождитесь завершения загрузки всех ФО")
        refs=db.execute("SELECT count(*) AS n FROM uploads WHERE kind='reference' AND finalized").fetchone()["n"]
        if count<1 or refs<1:raise HTTPException(422,"Загрузите ФО и Образцы перед сортировкой")
        now=datetime.now(timezone.utc)
        run_id=now.strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:12]
        info={"id":run_id,"status":"queued","references":str(DATA_DIR/"references"),
              "new_photos":str(DATA_DIR/"uploads"/str(data.batch_id)),
              "output":str(DATA_DIR/"outputs"),"batch_id":str(data.batch_id),
              "selected_models":["megaloc"],"grouping_threshold":data.grouping_threshold,
              "models":{},"progress":{},"enqueued_at":now.isoformat(),
              "started_at":now.isoformat()}
        db.execute("""UPDATE batches SET download_confirmed_at=NULL,
            delete_after_at=NULL,confirmed_run_id=NULL,upload_state='sealed'
            WHERE id=%s""",(data.batch_id,))
        db.execute("INSERT INTO jobs(id,batch_id,status,snapshot) VALUES (%s,%s,'queued',%s)",
                   (run_id,data.batch_id,Jsonb(info)))
        position=queue.queue_position(db,run_id)
    return {**info,"queue_position":position}

@router.get("/{run_id}")
def get_job(run_id:str):
    with connect() as db:
        row=db.execute("""SELECT id,snapshot,status,created_at,started_at,finished_at
            FROM jobs WHERE id=%s""",(run_id,)).fetchone()
        if not row:raise HTTPException(404,"Задание не найдено")
        return queue.decorated(db,row)

@router.post("/{run_id}/stop")
def stop(run_id:str):
    with connect() as db:
        row=db.execute("SELECT status,snapshot FROM jobs WHERE id=%s FOR UPDATE",
                       (run_id,)).fetchone()
        if not row:raise HTTPException(404,"Задание не найдено")
        if row["status"] in TERMINAL:raise HTTPException(409,"Задание уже завершено")
        info=dict(row["snapshot"])
        info["status"]="stopping" if row["status"]!="queued" else "stopped"
        db.execute("""UPDATE jobs SET stop_requested=true,status=%s,snapshot=%s,
            finished_at=CASE WHEN %s='stopped' THEN now() ELSE finished_at END,
            updated_at=now() WHERE id=%s""",
            (info["status"],Jsonb(info),info["status"],run_id))
    return info

class ServerJob(Job):
    def __init__(self,info):
        super().__init__(info)
        self._last_db_stop=0.0
        self._db_stopped=False
    def save(self):
        super().save()
        save_snapshot(self.snapshot())
    def stopped(self):
        if self.cancel_event.is_set():return True
        if time.monotonic()-self._last_db_stop>1:
            self._last_db_stop=time.monotonic()
            with connect() as db:
                row=db.execute("SELECT stop_requested FROM jobs WHERE id=%s",
                               (self.info["id"],)).fetchone()
                self._db_stopped=bool(row and row["stop_requested"])
        return self._db_stopped
