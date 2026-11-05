"""Batch CRUD and safe ownership-aware removal of unprocessed photos."""
from __future__ import annotations
import uuid
from pathlib import Path
from fastapi import HTTPException
from ..database import connect
from ..storage.paths import batch_dir, owned_file
from app.config import DATA_DIR

def uid(value):
    try: return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError): raise HTTPException(404, "Партия не найдена")

def _require_active(db, batch_id, lock="FOR UPDATE"):
    row = db.execute(f"SELECT * FROM batches WHERE id=%s {lock}", (batch_id,)).fetchone()
    if not row: raise HTTPException(404, "Партия не найдена")
    if row["delete_state"] != "active":
        raise HTTPException(409, "Партия удаляется или удалена")
    return row

def create(display_name=None):
    name = (display_name or "").strip()
    if len(name) > 120: raise HTTPException(422, "Название слишком длинное")
    batch_id = uuid.uuid4()
    if not name:
        from datetime import datetime,timezone
        name = "Фотоотчёт " + datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    with connect() as db:
        db.execute("INSERT INTO batches(id,display_name) VALUES (%s,%s)", (batch_id,name))
    return {"batch_id":str(batch_id), "display_name":name}

def _serialize(row, counters=None):
    data = {
        "batch_id":str(row["id"]), "display_name":row["display_name"],
        "created_at":row["created_at"], "upload_state":row["upload_state"],
        "thumbnail_state":row["thumbnail_state"],"delete_state":row["delete_state"],
        "download_confirmed_at":row["download_confirmed_at"],
        "confirmed_run_id":row["confirmed_run_id"],"delete_after_at":row["delete_after_at"],
        "deleted_at":row["deleted_at"]
    }
    if counters: data.update(counters)
    return data

def get(batch_id):
    batch_id=uid(batch_id)
    with connect() as db:
        row=db.execute("SELECT * FROM batches WHERE id=%s",(batch_id,)).fetchone()
        if not row: raise HTTPException(404,"Партия не найдена")
        counts=db.execute("""SELECT count(*) FILTER (WHERE finalized) AS photos,
           coalesce(sum(declared_size) FILTER (WHERE finalized),0) AS size_bytes,
           count(*) FILTER (WHERE NOT finalized) AS pending
           FROM uploads WHERE kind='fo' AND batch_id=%s""",(batch_id,)).fetchone()
        runs=db.execute("SELECT count(*) AS runs FROM jobs WHERE batch_id=%s",(batch_id,)).fetchone()
    return _serialize(row,{**counts,**runs})

def list_all(limit=100, offset=0):
    with connect() as db:
        rows=db.execute("SELECT * FROM batches ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (limit,offset)).fetchall()
        total=db.execute("SELECT count(*) AS c FROM batches").fetchone()["c"]
    return {"batches":[_serialize(r) for r in rows],"total":total}

def rename(batch_id, name):
    batch_id=uid(batch_id)
    name=name.strip()
    if not name or len(name)>120: raise HTTPException(422,"Название: от 1 до 120 символов")
    with connect() as db:
        _require_active(db,batch_id)
        db.execute("UPDATE batches SET display_name=%s WHERE id=%s",(name,batch_id))
    return get(batch_id)

def photos(batch_id,limit=100,offset=0):
    batch_id=uid(batch_id)
    with connect() as db:
        row=db.execute("SELECT id FROM batches WHERE id=%s",(batch_id,)).fetchone()
        if not row:raise HTTPException(404,"Партия не найдена")
        items=db.execute("""SELECT id,filename,declared_size,checksum,finalized,created_at
            FROM uploads WHERE kind='fo' AND batch_id=%s ORDER BY created_at,id
            LIMIT %s OFFSET %s""",(batch_id,limit,offset)).fetchall()
        total=db.execute("SELECT count(*) AS c FROM uploads WHERE kind='fo' AND batch_id=%s",
                         (batch_id,)).fetchone()["c"]
    return {"photos":[{**item,"id":str(item["id"])} for item in items],"total":total}

def remove_unprocessed_photo(batch_id,photo_id):
    batch_id=uid(batch_id)
    try: photo_id=uuid.UUID(str(photo_id))
    except (ValueError,TypeError):raise HTTPException(404,"ФО не найдено")
    with connect() as db:
        _require_active(db,batch_id)
        if db.execute("SELECT 1 FROM jobs WHERE batch_id=%s LIMIT 1",(batch_id,)).fetchone():
            raise HTTPException(409,"После запуска обработки удаление отдельного ФО запрещено")
        if db.execute("SELECT 1 FROM batch_operations WHERE batch_id=%s LIMIT 1",(batch_id,)).fetchone():
            raise HTTPException(409,"Дождитесь окончания передачи файлов")
        item=db.execute("""SELECT id,target_path FROM uploads
            WHERE id=%s AND batch_id=%s AND kind='fo' FOR UPDATE""",
            (photo_id,batch_id)).fetchone()
        if not item:raise HTTPException(404,"ФО не найдено")
        if item["target_path"]:
            path=owned_file(item["target_path"],batch_dir(batch_id))
            shared=db.execute("SELECT 1 FROM uploads WHERE target_path=%s AND id<>%s LIMIT 1",
                              (item["target_path"],photo_id)).fetchone()
            if not shared: path.unlink(missing_ok=True)
        else:
            path=owned_file(DATA_DIR/"incoming"/f"{photo_id}.part",DATA_DIR/"incoming")
            path.unlink(missing_ok=True)
        db.execute("DELETE FROM uploads WHERE id=%s",(photo_id,))
    return {"deleted":True}
