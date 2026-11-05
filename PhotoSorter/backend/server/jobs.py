"""Queue and progress persistence; a single PostgreSQL-backed worker consumes jobs."""
from __future__ import annotations
import json
import re
import time
import uuid
from datetime import datetime,timezone
from pathlib import Path
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from psycopg.types.json import Jsonb
from app.config import DATA_DIR
from app.jobs.runtime import Job
from .database import connect,save_snapshot

router=APIRouter(prefix='/api/runs',tags=['jobs'])
TERMINAL={'completed','completed_with_errors','failed','stopped','interrupted'}

class NewRun(BaseModel):
    batch_id:uuid.UUID
    grouping_threshold:float=Field(default=.50,ge=.50,le=.99,allow_inf_nan=False)

@router.get('')
def list_jobs():
    with connect() as db:
        rows=db.execute('SELECT snapshot FROM jobs ORDER BY created_at DESC LIMIT 100').fetchall()
    return {'runs':[row['snapshot'] for row in rows]}

@router.post('',status_code=202)
def enqueue(data:NewRun):
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(723409133)')
        busy=db.execute("SELECT id FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone()
        if busy:raise HTTPException(409,'Уже выполняется другое задание')
        batch=db.execute('SELECT id,delete_state FROM batches WHERE id=%s FOR UPDATE',(data.batch_id,)).fetchone()
        if not batch:raise HTTPException(404,'Партия ФО не найдена')
        if batch['delete_state']!='active':raise HTTPException(409,'Партия удаляется')
        count=db.execute('SELECT count(*) AS c FROM uploads WHERE kind=\'fo\' AND finalized AND batch_id=%s',
                         (data.batch_id,)).fetchone()['c']
        pending=db.execute('SELECT count(*) AS c FROM uploads WHERE kind=\'fo\' AND batch_id=%s AND NOT finalized',(data.batch_id,)).fetchone()['c']
        if pending:raise HTTPException(422,'Дождитесь завершения загрузки всех ФО')
        ref_count=db.execute("SELECT count(*) AS c FROM uploads WHERE kind='reference' AND finalized").fetchone()['c']
        if count<1 or ref_count<1:raise HTTPException(422,'Загрузите ФО и Образцы перед сортировкой')
        run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]
        info={'id':run_id,'status':'queued','references':str(DATA_DIR/'references'),
              'new_photos':str(DATA_DIR/'uploads'/str(data.batch_id)),
              'output':str(DATA_DIR/'outputs'),'batch_id':str(data.batch_id),
              'selected_models':['megaloc'],'grouping_threshold':data.grouping_threshold,
              'models':{},'progress':{},'started_at':datetime.now(timezone.utc).isoformat()}
        # A new run invalidates the previous whole-archive confirmation.
        db.execute("""UPDATE batches SET download_confirmed_at=NULL,delete_after_at=NULL,
            confirmed_run_id=NULL,upload_state='sealed' WHERE id=%s""",(data.batch_id,))
        db.execute('INSERT INTO jobs(id,batch_id,status,snapshot) VALUES (%s,%s,%s,%s)',
                   (run_id,data.batch_id,'queued',Jsonb(info)))
    return info

@router.get('/{run_id}')
def get_job(run_id:str):
    with connect() as db:
        row=db.execute('SELECT snapshot FROM jobs WHERE id=%s',(run_id,)).fetchone()
    if not row:raise HTTPException(404,'Задание не найдено')
    return row['snapshot']

@router.post('/{run_id}/stop')
def stop(run_id:str):
    with connect() as db:
        row=db.execute('SELECT status,snapshot FROM jobs WHERE id=%s FOR UPDATE',(run_id,)).fetchone()
        if not row:raise HTTPException(404,'Задание не найдено')
        if row['status'] in TERMINAL:raise HTTPException(409,'Задание уже завершено')
        info=row['snapshot'];info['status']='stopping' if row['status']=='running' else 'stopped'
        db.execute('UPDATE jobs SET stop_requested=true,status=%s,snapshot=%s,updated_at=now() WHERE id=%s',
                   (info['status'],Jsonb(info),run_id))
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
                row=db.execute('SELECT stop_requested FROM jobs WHERE id=%s',(self.info['id'],)).fetchone()
                self._db_stopped=bool(row and row['stop_requested'])
        return self._db_stopped
