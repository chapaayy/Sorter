"""Configurable automatic retention for newly finished runs.

Existing batches keep their pre-upgrade deadlines. Nothing is deleted on saving
preferences: the cleanup service only acts on an explicitly recorded due date.
"""
from __future__ import annotations
import uuid
from fastapi import HTTPException
from ..database import connect
from ..storage.paths import run_dir
from .batches import uid, _require_active
from app.config import DATA_DIR

UNITS={"minutes":"minute","hours":"hour","days":"day","months":"month"}

def _preference(db):
    row=db.execute("SELECT enabled,value,unit FROM retention_preferences WHERE id=1").fetchone()
    return dict(row) if row else {"enabled":True,"value":2,"unit":"months"}

def settings():
    with connect() as db:
        return _preference(db)

def update_settings(enabled:bool,value:int,unit:str):
    if unit not in UNITS or not 1<=value<=525600:
        raise HTTPException(422,"Неверный срок хранения")
    if value>120 and unit=="months":
        raise HTTPException(422,"Максимум 120 месяцев")
    with connect() as db:
        # Serialize preference edits with automatic deletion requests and enqueue.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        previous=_preference(db)
        db.execute("""UPDATE retention_preferences SET enabled=%s,value=%s,unit=%s,updated_at=now()
             WHERE id=1""",(enabled,value,unit))
        if enabled and not previous["enabled"]:
            # Expired while disabled? Give a full new period on re-enabling.
            db.execute("""UPDATE batches SET
                delete_after_at=now() + (%s * %s::interval)
                WHERE delete_state='active' AND delete_after_at IS NOT NULL
                  AND delete_after_at<=now()""",(value,"1 "+UNITS[unit]))
    return settings()

def _deadline(db,after_sql="now()"):
    # Only trusted fixed SQL constants, not client-controlled SQL fragments.
    pref=_preference(db)
    if not pref["enabled"]:return None
    interval=UNITS[pref["unit"]]
    return pref["value"],interval

def schedule(db,batch_id,run_id):
    pref=_deadline(db)
    if pref is None:
        db.execute("UPDATE batches SET delete_after_at=NULL WHERE id=%s AND delete_state='active'",(batch_id,))
        return
    value,unit=pref
    db.execute("""UPDATE batches SET
      delete_after_at=now() + (%s * %s::interval),
      confirmed_run_id=%s
      WHERE id=%s AND delete_state='active'""",(value,"1 "+unit,run_id,batch_id))

def confirm(batch_id,run_id):
    """Legacy confirmation: never overwrite an automatically assigned deadline."""
    batch_id=uid(batch_id)
    with connect() as db:
        _require_active(db,batch_id)
        latest=db.execute("""SELECT id,status FROM jobs WHERE batch_id=%s
            ORDER BY created_at DESC,id DESC LIMIT 1""",(batch_id,)).fetchone()
        if not latest or latest["id"]!=run_id:
            raise HTTPException(409,"Подтвердите последний запуск этой партии")
        if latest["status"] not in ("completed","completed_with_errors"):
            raise HTTPException(409,"Последний запуск ещё не завершён")
        try:manifest=run_dir(run_id,DATA_DIR/"outputs")/"megaloc"/"manifest.json"
        except ValueError:raise HTTPException(422,"Неверный запуск")
        if not manifest.is_file():raise HTTPException(409,"Полный результат не опубликован")
        pref=_deadline(db)
        if pref is None:
            row=db.execute("""UPDATE batches SET download_confirmed_at=now(),confirmed_run_id=%s
                 WHERE id=%s RETURNING download_confirmed_at,delete_after_at""",(run_id,batch_id)).fetchone()
        else:
            value,unit=pref
            row=db.execute("""UPDATE batches SET download_confirmed_at=now(),confirmed_run_id=%s,
              delete_after_at=coalesce(delete_after_at,now() + (%s * %s::interval))
              WHERE id=%s RETURNING download_confirmed_at,delete_after_at""",
              (run_id,value,"1 "+unit,batch_id)).fetchone()
        db.execute("""INSERT INTO download_confirmations(id,batch_id,run_id,event)
             VALUES (%s,%s,%s,'confirmed')""",(uuid.uuid4(),batch_id,run_id))
    return {**row,"batch_id":str(batch_id),"confirmed_run_id":run_id}

def extend(batch_id):
    batch_id=uid(batch_id)
    with connect() as db:
        row=_require_active(db,batch_id)
        if not row["delete_after_at"]:
            raise HTTPException(409,"Автоудаление для этой партии не назначено")
        pref=_deadline(db) or (2,"month")
        value,unit=pref
        data=db.execute("""UPDATE batches SET
            delete_after_at=greatest(delete_after_at,now()) + (%s * %s::interval)
            WHERE id=%s RETURNING download_confirmed_at,delete_after_at,confirmed_run_id""",
            (value,"1 "+unit,batch_id)).fetchone()
        db.execute("""INSERT INTO download_confirmations(id,batch_id,run_id,event)
            VALUES (%s,%s,%s,'extended')""",
            (uuid.uuid4(),batch_id,data["confirmed_run_id"] or "manual"))
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
        if not _preference(db)["enabled"]:
            return []
        rows=db.execute("""SELECT id FROM batches WHERE delete_state='active'
               AND delete_after_at IS NOT NULL AND delete_after_at<=now()
               ORDER BY delete_after_at LIMIT %s""",(limit,)).fetchall()
    return [r["id"] for r in rows]
