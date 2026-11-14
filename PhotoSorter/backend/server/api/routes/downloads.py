"""Completed result ZIP as a cached seekable file with Range/206 support."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app.config import DATA_DIR
from ...database import connect
from ...services import operations,archives
from ...security.access_policy import current_user,is_viewer,require_published
from .results import safe_manifest
from .images import file_allowed

router=APIRouter(prefix="/api/download",tags=["downloads"])
archive_member=archives.archive_member

@router.get("/{run_id}")
def download_results(run_id:str,sam:str|None=None,request:Request=None):
    viewer = is_viewer(request)
    with connect() as db:
        if viewer:
            require_published(db,run_id,current_user(request)["id"])
        row=db.execute("SELECT batch_id,status,snapshot FROM jobs WHERE id=%s",(run_id,)).fetchone()
    if not row:raise HTTPException(404,"Запуск не найден")
    lease=operations.start(row["batch_id"],"download")
    try:
        rows=safe_manifest(run_id)
        selected=[]
        for item in rows:
            if sam and item["assigned_sam"]!=sam:continue
            source=file_allowed(Path(item["copy"]))
            if viewer and not source.resolve().is_relative_to((DATA_DIR/"outputs").resolve()):
                raise HTTPException(404,"Готовый файл не найден")
            selected.append((source,archive_member(item["assigned_sam"],source.name)))
        # New runs publish their full ZIP before the completed state.
        # Legacy runs retain on-demand creation for backward compatibility.
        if sam is None and row["snapshot"].get("archive_state") is not None:
            if row["status"] not in ("completed","completed_with_errors") or row["snapshot"].get("archive_state")!="ready":
                raise HTTPException(409,"Архив ещё не готов")
            file=archives.existing(run_id,sam,selected)
            if file is None:
                raise HTTPException(409,"Архив отсутствует. Повторите его подготовку")
        else:
            file=archives.prepare(run_id,sam,selected)
        return FileResponse(file,media_type="application/zip",
            filename=f"photosorter-{run_id}.zip",
            headers={"Cache-Control":"private, no-store",
                     "X-Content-Type-Options":"nosniff"},
            background=BackgroundTask(operations.finish,lease))
    except BaseException:
        operations.finish(lease)
        raise
