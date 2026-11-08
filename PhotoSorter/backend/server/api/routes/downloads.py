"""Completed result ZIP as a cached seekable file with Range/206 support."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from ...database import connect
from ...services import operations,archives,archive_pipeline
from .results import safe_manifest
from .images import file_allowed

router=APIRouter(prefix="/api/download",tags=["downloads"])
archive_member=archives.archive_member

@router.get("/{run_id}")
def download_results(run_id:str,sam:str|None=None):
    with connect() as db:
        row=db.execute("SELECT batch_id,status,snapshot FROM jobs WHERE id=%s",(run_id,)).fetchone()
    if not row:raise HTTPException(404,"Запуск не найден")
    lease=operations.start(row["batch_id"],"download")
    try:
        rows=safe_manifest(run_id)
        selected=[]
        for item in rows:
            if sam and item["assigned_sam"]!=sam:continue
            source=file_allowed(Path(item["copy"]))
            selected.append((source,archive_member(item["assigned_sam"],source.name)))
        # Same immutable selection as the initial ZIP and ZIP-only repair.
        if row["snapshot"].get("ad_pipeline",{}).get("enabled"):
            integrated=archive_pipeline.selections(run_id)
            if sam is None:
                selected=integrated
            else:
                # A per-construction archive includes its confirmed/review best
                # photos, but excludes other SAMs and global metadata.
                prefix=archive_member(sam,"photo.jpg").rsplit("/",1)[0]+"/"
                selected=[(source,name) for source,name in integrated
                          if name.startswith(prefix) or
                             name.startswith("Best_by_layout/"+prefix) or
                             name.startswith("Review_required/"+prefix)]
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
