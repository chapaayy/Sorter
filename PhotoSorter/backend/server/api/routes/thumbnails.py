"""Versioned, authenticated, upload-ID-owned previews; do not expose file paths."""
from __future__ import annotations
import uuid
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from ...database import connect
from ...storage import thumbnail_cache as cache
from ...services import thumbnails

router=APIRouter(prefix="/api/thumbnails",tags=["thumbnails"])

@router.get("/{photo_id}")
def thumbnail(photo_id:str):
    try:uid=uuid.UUID(photo_id)
    except ValueError:raise HTTPException(404,"Фотография не найдена")
    with connect() as db:
        row=db.execute("""SELECT t.state,t.checksum,t.version,
           u.kind,u.batch_id,b.delete_state
           FROM uploads u LEFT JOIN thumbnail_tasks t ON t.upload_id=u.id
           LEFT JOIN batches b ON b.id=u.batch_id WHERE u.id=%s AND u.finalized""",
           (uid,)).fetchone()
    if not row or (row["batch_id"] and row["delete_state"]!="active"):
        raise HTTPException(404,"Фотография не найдена")
    if row["state"]!="ready":raise HTTPException(202,"Миниатюра готовится")
    try:file=cache.safe_location(cache.location(row["checksum"],row["version"]))
    except ValueError:raise HTTPException(404,"Миниатюра недоступна")
    if not file.is_file():raise HTTPException(202,"Миниатюра готовится")
    return FileResponse(file,media_type="image/webp",
                        headers={"Cache-Control":"private, max-age=3600"})

@router.get("/status/{batch_id}/counts")
def counts(batch_id:str):
    try:uid=uuid.UUID(batch_id)
    except ValueError:raise HTTPException(404,"Партия не найдена")
    with connect() as db:
        row=db.execute("SELECT delete_state FROM batches WHERE id=%s",(uid,)).fetchone()
        if not row:raise HTTPException(404,"Партия не найдена")
    return {**thumbnails.counts(uid),"batch_id":str(uid)}

@router.post("/{photo_id}/retry",status_code=202)
def retry(photo_id:str):
    try:uid=uuid.UUID(photo_id)
    except ValueError:raise HTTPException(404,"Фотография не найдена")
    with connect() as db:
        row=db.execute("""SELECT t.state,u.batch_id,b.delete_state FROM thumbnail_tasks t
           JOIN uploads u ON u.id=t.upload_id
           LEFT JOIN batches b ON b.id=u.batch_id
           WHERE t.upload_id=%s FOR UPDATE OF t""",(uid,)).fetchone()
        if not row:raise HTTPException(404,"Миниатюра не найдена")
        if row["batch_id"] and row["delete_state"]!="active":
            raise HTTPException(409,"Партия удаляется")
        if row["state"] not in ("failed","queued"):
            raise HTTPException(409,"Миниатюра уже готова или обрабатывается")
        db.execute("""UPDATE thumbnail_tasks SET state='queued',attempts=0,
            lease_until=NULL,last_error=NULL,updated_at=now() WHERE upload_id=%s""",(uid,))
    return {"status":"queued","photo_id":str(uid)}
