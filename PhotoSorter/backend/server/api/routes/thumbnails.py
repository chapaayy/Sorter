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
