"""Build temporary seekable ZIPs exclusively on download requests."""
from __future__ import annotations
import errno
from fastapi import APIRouter,HTTPException,Request
from ...database import connect
from ...services import operations,archives,archive_pipeline,archive_cache
from ...storage.paths import owned_directory,run_dir
from ..file_response import LeasedFileResponse
from ...security.access_policy import current_user,is_viewer,require_published

router=APIRouter(prefix="/api/download",tags=["downloads"])
archive_member=archives.archive_member

@router.get("/{run_id}")
def download_results(run_id:str,sam:str|None=None,request:Request=None):
    with connect() as db:
        if is_viewer(request):
            require_published(db,run_id,current_user(request)["id"])
        row=db.execute("""SELECT j.batch_id,j.status,b.display_name
            FROM jobs j JOIN batches b ON b.id=j.batch_id WHERE j.id=%s""",(run_id,)).fetchone()
    if not row:raise HTTPException(404,"Запуск не найден")
    if row["status"] not in ("completed","completed_with_errors"):
        raise HTTPException(409,"Сортировка ещё не завершена")
    lease=operations.start(row["batch_id"],"download")
    pin=None
    try:
        root=archives.output_root()
        folder=owned_directory(run_dir(run_id,root)/".archives",root)
        pin=archive_cache.pin(folder)
        plan=archive_pipeline.named_plan(run_id,row["batch_id"],row["display_name"],sam)
        file=archives.prepare(run_id,sam,plan.files)
        return LeasedFileResponse(file,lease=lease,archive_pin=pin,media_type="application/zip",
            filename=plan.title+".zip",headers={"Cache-Control":"private, no-store",
                                                "X-Content-Type-Options":"nosniff"})
    except BaseException as exc:
        if pin is not None:pin.close()
        operations.finish(lease)
        if isinstance(exc,(FileNotFoundError,ValueError)):
            raise HTTPException(404,"Готовые файлы результата не найдены") from exc
        if isinstance(exc,OSError) and exc.errno==errno.ENOSPC:
            raise HTTPException(507,"Недостаточно места для временного ZIP") from exc
        raise
