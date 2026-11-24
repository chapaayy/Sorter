"""Restrict photo serving to trusted persisted storage locations."""
from pathlib import Path
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import FileResponse
from ...database import connect
from ...services import operations
from ..file_response import LeasedFileResponse
from ...storage.paths import owned_file,batch_root,result_media_dir
from ...storage import thumbnail_cache as cache
from ...storage.reference_objects import object_root
from app.config import DATA_DIR
from app.photos.reader import EXTS
from ...security.access_policy import check_published,is_viewer
from .results import safe_manifest

router=APIRouter(prefix="/api/images",tags=["images"])

def file_allowed(file:Path, run_id=None, kind=None):
    if run_id is not None:
        with connect() as db:
            row=db.execute("SELECT batch_id FROM jobs WHERE id=%s",(run_id,)).fetchone()
        if not row:raise HTTPException(404,"Запуск не найден")
        roots=([batch_root(row["batch_id"])] if kind=="query" else
               [result_media_dir(run_id)] if kind=="copy" else
               [object_root()])
    else:
        roots=[object_root()]
    for root in roots:
        try:
            owned_file(file,root)
            break
        except (ValueError,OSError):
            continue
    else:raise HTTPException(404,"Файл недоступен")
    if not file.is_file() or (kind!="reference" and file.suffix.lower() not in EXTS):
        raise HTTPException(404,"Файл не найден")
    return file

@router.get("/{run_id}/megaloc/{index}")
def image(run_id:str,index:int,kind:str="query",candidate:int=0,request:Request=None):
    if is_viewer(request):
        check_published(request,run_id)
        if kind not in ("copy","poster"):
            raise HTTPException(403,"Доступны только готовые фотографии")
    rows=safe_manifest(run_id)
    if index<0 or index>=len(rows):raise HTTPException(404,"Фотография не найдена")
    row=rows[index]
    if kind in ("copy","poster") and row.get("media_kind")=="video":
        return _video(run_id,row,kind)
    if kind=="query":filename=row["query"]
    elif kind=="copy":filename=row["copy"]
    elif kind=="reference":
        top=row.get("top",[])
        if not 0<=candidate<len(top):raise HTTPException(404,"Образец не найден")
        filename=top[candidate]["reference"]
    else:raise HTTPException(422,"Неверный тип изображения")
    file = file_allowed(Path(filename),run_id,kind)
    return FileResponse(file, media_type="application/octet-stream" if kind=="reference" else None, headers={"Cache-Control":"private, no-store"})


def _video(run_id,row,kind):
    with connect() as db:
        job=db.execute("SELECT batch_id FROM jobs WHERE id=%s",(run_id,)).fetchone()
        if not job:raise HTTPException(404,"Видео не найдено")
        thumb=None
        if kind=="poster":
            thumb=db.execute("""SELECT t.checksum,t.version FROM thumbnail_tasks t
                JOIN uploads u ON u.id=t.upload_id WHERE u.id=%s AND u.batch_id=%s AND t.state='ready'""",
                (row.get("upload_id"),job["batch_id"])).fetchone()
    token=operations.start(job["batch_id"],"original")
    try:
        if kind=="poster":
            if not thumb:raise FileNotFoundError()
            file=cache.safe_location(cache.location(thumb["checksum"],thumb["version"]))
            mime="image/webp"
        else:
            file=owned_file(Path(row["copy"]),result_media_dir(run_id))
            mime="video/webm" if Path(row["export_name"]).suffix.lower()==".webm" else "video/mp4"
        if not file.is_file():raise FileNotFoundError()
        return LeasedFileResponse(file,lease=token,media_type=mime,
                            headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
    except (OSError,ValueError):
        operations.finish(token)
        raise HTTPException(404,"Видео или обложка не найдены")
    except BaseException:
        operations.finish(token)
        raise
