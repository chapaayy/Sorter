"""Completed result ZIP as a cached seekable file with Range/206 support."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from psycopg.types.json import Jsonb
from ...database import connect
from ...services import operations,archives,archive_pipeline
from ...security.access_policy import current_user,is_viewer,require_published

router=APIRouter(prefix="/api/download",tags=["downloads"])
archive_member=archives.archive_member

@router.get("/{run_id}")
def download_results(run_id:str,sam:str|None=None,request:Request=None):
    viewer = is_viewer(request)
    with connect() as db:
        if viewer:
            require_published(db,run_id,current_user(request)["id"])
        row=db.execute("""SELECT j.batch_id,j.status,j.snapshot,b.display_name
            FROM jobs j JOIN batches b ON b.id=j.batch_id WHERE j.id=%s""",(run_id,)).fetchone()
    if not row:raise HTTPException(404,"Запуск не найден")
    lease=operations.start(row["batch_id"],"download")
    try:
        snapshot=row["snapshot"]
        if sam is None and snapshot.get("archive_state") is not None:
            if row["status"] not in ("completed","completed_with_errors") or snapshot["archive_state"]!="ready":
                raise HTTPException(409,"Архив ещё не готов")
            if filename:=snapshot.get("archive_file"):
                file=archives.published(run_id,filename)
                if file is None:
                    raise HTTPException(409,"Архив отсутствует. Повторите его подготовку")
                title=snapshot["archive_title"]
            else:
                file=None
        else:
            file=None
        if file is None:
            # Old full ZIPs are rebuilt in the new layout on the first
            # download, using the saved results, not running MegaLoc again.
            plan=archive_pipeline.named_plan(run_id,row["batch_id"],row["display_name"],sam)
            if not plan.files:
                raise HTTPException(404,"Нет фотографий для архива")
            if sam is None and snapshot.get("archive_state")=="ready" and not archives.existing(
                run_id,None,archive_pipeline.legacy_selections(run_id)
            ):
                raise HTTPException(409,"Архив отсутствует. Повторите его подготовку")
            file=archives.prepare(run_id,sam,plan.files)
            title=plan.title
            if sam is None and row["status"] in ("completed","completed_with_errors"):
                with connect() as db:
                    db.execute("""UPDATE jobs SET snapshot=snapshot || %s
                        WHERE id=%s AND status IN ('completed','completed_with_errors')
                          AND NOT (snapshot ? 'archive_file')""",
                        (Jsonb({"archive_file":file.name,"archive_title":title,
                                "archive_bytes":file.stat().st_size,"archive_state":"ready"}),run_id))
        return FileResponse(file,media_type="application/zip",
            filename=title+".zip",
            headers={"Cache-Control":"private, no-store",
                     "X-Content-Type-Options":"nosniff"},
            background=BackgroundTask(operations.finish,lease))
    except (FileNotFoundError,ValueError) as exc:
        operations.finish(lease)
        raise HTTPException(404,"Готовые файлы результата не найдены") from exc
    except BaseException:
        operations.finish(lease)
        raise
