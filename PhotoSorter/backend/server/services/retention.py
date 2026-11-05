"""Explicit whole-ZIP confirmation, calendar-month retention and warnings."""
from __future__ import annotations
import uuid
from fastapi import HTTPException
from ..database import connect
from ..storage.paths import run_dir
from .batches import uid, _require_active
from app.config import DATA_DIR

def confirm(batch_id,run_id):
    batch_id=uid(batch_id)
    with connect() as db:
        _require_active(db,batch_id)
        job=db.execute("SELECT status FROM jobs WHERE batch_id=%s AND id=%s",
                       (batch_id,run_id)).fetchone()
        if not job or job["status"] not in ("completed","completed_with_errors"):
            raise HTTPException(409,"Нет завершённого запуска этой партии")
        # Do not start a deletion timer for nonexistent/failed result archives.
        try: manifest=run_dir(run_id,DATA_DIR/"outputs")/"megaloc"/"manifest.json"
        except ValueError:raise HTTPException(422,"Неверный запуск")
        if not manifest.is_file():
            raise HTTPException(409,"Полный результат не опубликован")
        row=db.execute("""UPDATE batches SET download_confirmed_at=now(),
           confirmed_run_id=%s,delete_after_at=((now() AT TIME ZONE 'UTC')+interval '2 months') AT TIME ZONE 'UTC'
           WHERE id=%s RETURNING download_confirmed_at,delete_after_at""",
           (run_id,batch_id)).fetchone()
        db.execute("""INSERT INTO download_confirmations(id,batch_id,run_id,event)
             VALUES (%s,%s,%s,'confirmed')""",(uuid.uuid4(),batch_id,run_id))
    return {**row,"batch_id":str(batch_id),"confirmed_run_id":run_id}

def extend(batch_id):
    batch_id=uid(batch_id)
    with connect() as db:
        row=_require_active(db,batch_id)
        if not row["delete_after_at"]:
            raise HTTPException(409,"Архив ещё не подтверждён")
        data=db.execute("""UPDATE batches SET
            delete_after_at=(((greatest(delete_after_at,now()) AT TIME ZONE 'UTC')+interval '2 months') AT TIME ZONE 'UTC')
            WHERE id=%s RETURNING download_confirmed_at,delete_after_at,confirmed_run_id""",
            (batch_id,)).fetchone()
        db.execute("""INSERT INTO download_confirmations(id,batch_id,run_id,event)
            VALUES (%s,%s,%s,'extended')""",
            (uuid.uuid4(),batch_id,data["confirmed_run_id"]))
    return {**data,"batch_id":str(batch_id)}

def status(batch_id):
    batch_id=uid(batch_id)
    with connect() as db:
        row=db.execute("""SELECT delete_state,download_confirmed_at,delete_after_at,
             confirmed_run_id,delete_after_at IS NOT NULL AND
             delete_after_at <= now()+interval '7 days' AS warning,
             download_confirmed_at IS NULL AND created_at<=now()-interval '30 days'
             AS stale_unconfirmed
             FROM batches WHERE id=%s""",(batch_id,)).fetchone()
        if not row:raise HTTPException(404,"Партия не найдена")
    return {**row,"batch_id":str(batch_id)}

def due_batch_ids(limit=20):
    with connect() as db:
        rows=db.execute("""SELECT id FROM batches WHERE delete_state='active'
               AND download_confirmed_at IS NOT NULL AND delete_after_at <= now()
               ORDER BY delete_after_at LIMIT %s""",(limit,)).fetchall()
    return [r["id"] for r in rows]
