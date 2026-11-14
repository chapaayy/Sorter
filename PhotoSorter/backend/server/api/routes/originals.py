"""Authenticated original image viewer by UUID, with batch read leases."""
from __future__ import annotations
import asyncio,mimetypes,time,uuid
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter,HTTPException
from fastapi.responses import StreamingResponse
from app.config import DATA_DIR
from app.photos.reader import EXTS
from app.photos.labels import check_label
from ...database import connect
from ...storage.paths import owned_file
from ...services import operations

router=APIRouter(prefix="/api/photos",tags=["photos"])

@router.get("/{photo_id}/original")
def original(photo_id:str):
    try:uid=uuid.UUID(photo_id)
    except ValueError:raise HTTPException(404,"Фотография не найдена")
    with connect() as db:
        row=db.execute("""SELECT u.kind,u.batch_id,u.sam,u.filename,u.target_path,u.finalized,u.original_media_type,
            b.delete_state FROM uploads u LEFT JOIN batches b ON b.id=u.batch_id
            WHERE u.id=%s""",(uid,)).fetchone()
    if not row or not row["finalized"]:raise HTTPException(404,"Фотография не найдена")
    token=operations.start(row["batch_id"],"original") if row["batch_id"] else None
    try:
        if row["kind"]=="fo":
            root=DATA_DIR/"uploads"/str(row["batch_id"])
        else:
            root=DATA_DIR/"references"/check_label(row["sam"])
        path=owned_file(Path(row["target_path"]),root)
        attachment=row["kind"]=="fo" and row["original_media_type"] is not None
        if not path.is_file() or (not attachment and path.suffix.lower() not in EXTS):
            raise HTTPException(404,"Фотография не найдена")
        size=path.stat().st_size
        content_type="application/octet-stream" if attachment else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers={"Content-Length":str(size),"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}
        if attachment:
            headers["Content-Disposition"]="attachment; filename*=UTF-8''"+quote(row["filename"],safe="")
        async def stream():
            last=time.monotonic()
            try:
                with path.open("rb") as f:
                    while chunk:=await asyncio.to_thread(f.read,512*1024):
                        if token and time.monotonic()-last>=5:
                            await asyncio.to_thread(operations.heartbeat,token)
                            last=time.monotonic()
                        yield chunk
            finally:
                if token:await asyncio.to_thread(operations.finish,token)
        return StreamingResponse(stream(),media_type=content_type,headers=headers)
    except Exception:
        if token:operations.finish(token)
        raise
