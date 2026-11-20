"""Authenticated original image viewer by UUID, with batch read leases."""
from __future__ import annotations
import mimetypes,uuid
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter,HTTPException
from app.config import DATA_DIR
from app.photos.reader import EXTS
from ...database import connect
from ...media.preview import INLINE_TYPES
from ...storage.paths import owned_file
from ...services import operations
from ..file_response import LeasedFileResponse

router=APIRouter(prefix="/api/photos",tags=["photos"])

@router.get("/{photo_id}/prepared")
def prepared(photo_id:uuid.UUID):
    from ...services.media_preparation import playable
    with connect() as db:
        row=db.execute("""SELECT u.batch_id,u.target_path,u.media_output_path,u.media_action,
            u.original_media_type,b.media_image_format,b.media_video_format
            FROM uploads u JOIN batches b ON b.id=u.batch_id
            WHERE u.id=%s AND u.kind='fo' AND u.finalized""",(photo_id,)).fetchone()
    if not row:raise HTTPException(404,"Файл не найден")
    token=operations.start(row['batch_id'],'original')
    try:
        path=playable(row,DATA_DIR/'uploads'/str(row['batch_id']))
        if not path.is_file():raise FileNotFoundError()
        video=(row['original_media_type'] or '').startswith('video/')
        mime=(
            ('video/webm' if row['media_video_format']=='webm' else 'video/mp4')
            if video else ('image/png' if row['media_image_format']=='png' else 'image/jpeg')
        )
        return LeasedFileResponse(path,lease=token,media_type=mime,
                            headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
    except (ValueError,OSError):
        operations.finish(token)
        raise HTTPException(404,"Файл не готов к просмотру")
    except BaseException:
        operations.finish(token)
        raise

@router.get("/{photo_id}/preview")
def preview(photo_id:uuid.UUID):
    """Serve eligible originals inline, with Range support for video."""
    with connect() as db:
        row=db.execute("""SELECT batch_id,target_path,original_media_type
             FROM uploads WHERE id=%s AND kind='fo' AND finalized""",(photo_id,)).fetchone()
    if not row or not row["batch_id"] or not row["target_path"] or row["original_media_type"] not in INLINE_TYPES:
        raise HTTPException(404,"Файл недоступен для просмотра")
    token=operations.start(row["batch_id"],"original")
    try:
        path=owned_file(Path(row["target_path"]),DATA_DIR/"uploads"/str(row["batch_id"]))
        if not path.is_file():raise FileNotFoundError()
        return LeasedFileResponse(path,lease=token,media_type=row["original_media_type"],
                            headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
    except (ValueError,OSError):
        operations.finish(token)
        raise HTTPException(404,"Файл недоступен для просмотра")
    except BaseException:
        operations.finish(token)
        raise


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
            # Renaming updates the UUID gallery index, not the immutable hardlink path.
            root=DATA_DIR/"references"
        path=owned_file(Path(row["target_path"]),root)
        attachment=row["kind"]=="fo" and row["original_media_type"] is not None
        if not path.is_file() or (not attachment and path.suffix.lower() not in EXTS):
            raise HTTPException(404,"Фотография не найдена")
        content_type="application/octet-stream" if attachment else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}
        if attachment:
            headers["Content-Disposition"]="attachment; filename*=UTF-8''"+quote(row["filename"],safe="")
        return LeasedFileResponse(path,lease=token,media_type=content_type,headers=headers)
    except BaseException:
        operations.finish(token)
        raise
