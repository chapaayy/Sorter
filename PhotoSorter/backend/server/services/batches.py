"""Batch CRUD and safe ownership-aware removal of unprocessed photos."""
from __future__ import annotations
import uuid
import hashlib
from fastapi import HTTPException
from ..database import connect
from ..db.repositories import batches as repository
from ..storage.paths import batch_dir,owned_file
from app.config import DATA_DIR

def uid(value):
    try:return uuid.UUID(str(value))
    except (ValueError,TypeError,AttributeError):raise HTTPException(404,"Партия не найдена")

def _require_active(db,batch_id,lock="FOR UPDATE"):
    row=repository.get(db,batch_id,for_update=bool(lock))
    if not row:raise HTTPException(404,"Партия не найдена")
    if row["delete_state"]!="active":raise HTTPException(409,"Партия удаляется или удалена")
    return row

def create(display_name=None):
    name=(display_name or "").strip()
    if len(name)>120:raise HTTPException(422,"Название слишком длинное")
    batch_id=uuid.uuid4()
    if not name:
        from datetime import datetime,timezone
        name="Фотоотчёт "+datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    with connect() as db:
        repository.insert(db,batch_id,name)
    return {"batch_id":str(batch_id),"display_name":name}

def _serialize(row,counters=None):
    fields=("display_name","created_at","upload_state","thumbnail_state",
            "delete_state","download_confirmed_at","confirmed_run_id",
            "delete_after_at","deleted_at")
    data={"batch_id":str(row["id"])}
    for field in fields:data[field]=row[field]
    # Each batch has the same counter contract, even with no photos/runs.
    data.update({"photos":0,"size_bytes":0,"pending":0,"runs":0})
    if counters:data.update(counters)
    return data

def get(batch_id):
    batch_id=uid(batch_id)
    with connect() as db:
        row=repository.get(db,batch_id)
        if not row:raise HTTPException(404,"Партия не найдена")
        counters=repository.count_photos_and_runs(db,batch_id)
    return _serialize(row,counters)

def list_all(limit=100,offset=0):
    with connect() as db:
        rows,total=repository.list_rows(db,limit,offset)
        identifiers=[row["id"] for row in rows]
        aggregates={}
        if identifiers:
            stats=db.execute("""SELECT b.id,
              count(u.id) FILTER(WHERE u.kind='fo' AND u.finalized) AS photos,
              coalesce(sum(u.declared_size) FILTER(WHERE u.kind='fo' AND u.finalized),0) AS size_bytes,
              count(u.id) FILTER(WHERE u.kind='fo' AND NOT u.finalized) AS pending
              FROM batches b LEFT JOIN uploads u ON u.batch_id=b.id
              WHERE b.id=ANY(%s) GROUP BY b.id""",(identifiers,)).fetchall()
            runs=db.execute("""SELECT batch_id,count(*) AS runs FROM jobs
              WHERE batch_id=ANY(%s) GROUP BY batch_id""",(identifiers,)).fetchall()
            aggregates={r["id"]:dict(r) for r in stats}
            for entry in runs:aggregates.setdefault(entry["batch_id"],{})["runs"]=entry["runs"]
    return {"batches":[_serialize(row,aggregates.get(row["id"],{"photos":0,"pending":0,"size_bytes":0,"runs":0}))
                       for row in rows],"total":total}


def pending_uploads(batch_id):
    """List all incomplete FO sessions, using actual on-disk offsets.

    A complete .part file is still pending until its image is verified and
    finalized. The browser can finalize it without re-uploading the bytes.
    """
    batch_id=uid(batch_id)
    with connect() as db:
        if not repository.get(db,batch_id):
            raise HTTPException(404,"Партия не найдена")
        rows=db.execute("""SELECT id,filename,declared_size,received,updated_at
            FROM uploads WHERE batch_id=%s AND kind='fo' AND NOT finalized
            ORDER BY created_at,id""",(batch_id,)).fetchall()
    base=DATA_DIR/"incoming"
    result=[]
    for row in rows:
        part=base/f"{row['id']}.part"
        exists=part.is_file() and not part.is_symlink()
        actual=part.stat().st_size if exists else 0
        prefix_bytes=min(actual,65536)
        prefix_hash=None
        if prefix_bytes:
            with part.open("rb") as stream:
                prefix_hash=hashlib.sha256(stream.read(prefix_bytes)).hexdigest()
        result.append({
            "id":str(row["id"]),"filename":row["filename"],
            "size":row["declared_size"],"received":actual,
            "updated_at":row["updated_at"],
            "has_part":exists,"can_finalize":exists and actual==row["declared_size"],
            "prefix_bytes":prefix_bytes,"prefix_sha256":prefix_hash
        })
    return {"uploads":result,"total":len(rows)}

def rename(batch_id,name):
    batch_id=uid(batch_id)
    name=name.strip()
    if not name or len(name)>120:raise HTTPException(422,"Название: от 1 до 120 символов")
    with connect() as db:
        _require_active(db,batch_id)
        repository.set_name(db,batch_id,name)
    return get(batch_id)

def photos(batch_id,limit=100,offset=0):
    batch_id=uid(batch_id)
    with connect() as db:
        if not repository.get(db,batch_id):raise HTTPException(404,"Партия не найдена")
        rows,total=repository.list_photos(db,batch_id,limit,offset)
    return {"photos":[{**item,"id":str(item["id"])} for item in rows],"total":total}

def remove_unprocessed_photo(batch_id,photo_id):
    batch_id=uid(batch_id)
    try:photo_id=uuid.UUID(str(photo_id))
    except (ValueError,TypeError):raise HTTPException(404,"ФО не найдено")
    with connect() as db:
        _require_active(db,batch_id)
        if repository.has_runs(db,batch_id):
            raise HTTPException(409,"После запуска обработки удаление отдельного ФО запрещено")
        if repository.has_operations(db,batch_id):
            raise HTTPException(409,"Дождитесь окончания передачи файлов")
        item=repository.photo_row(db,batch_id,photo_id)
        if not item:raise HTTPException(404,"ФО не найдено")
        if item["target_path"]:
            path=owned_file(item["target_path"],batch_dir(batch_id))
            if not repository.path_is_shared(db,item["target_path"],photo_id):
                path.unlink(missing_ok=True)
        else:
            path=owned_file(DATA_DIR/"incoming"/f"{photo_id}.part",DATA_DIR/"incoming")
            path.unlink(missing_ok=True)
        repository.delete_photo_row(db,photo_id)
        repository.refresh_upload_state(db,batch_id)
    return {"deleted":True}
