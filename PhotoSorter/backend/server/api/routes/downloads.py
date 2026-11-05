"""Preserve zipstream-ng output; lease prevents deleting files mid-stream."""
from __future__ import annotations
import time
import zipfile
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import StreamingResponse
from ...database import connect
from ...services import operations
from .results import safe_manifest
from .images import file_allowed

router=APIRouter(prefix="/api/download",tags=["downloads"])

@router.get("/{run_id}")
def download_results(run_id:str,sam:str|None=None):
    import zipstream
    with connect() as db:
        row=db.execute("SELECT batch_id FROM jobs WHERE id=%s",(run_id,)).fetchone()
    if not row:raise HTTPException(404,"Запуск не найден")
    lease=operations.start(row["batch_id"],"download")
    try:
        rows=safe_manifest(run_id)
        selected=[]
        for item in rows:
            if sam and item["assigned_sam"]!=sam:continue
            file=file_allowed(Path(item["copy"]))
            selected.append((file,f'{item["assigned_sam"]}/{file.name}'))
        if not selected:raise HTTPException(404,"Нет фотографий для архива")
        stream=zipstream.ZipStream(compress_type=zipfile.ZIP_STORED)
        for file,name in selected:stream.add_path(file,arcname=name)
    except Exception:
        operations.finish(lease)
        raise
    def body():
        last=time.monotonic()
        try:
            for chunk in stream:
                if time.monotonic()-last>=5:
                    operations.heartbeat(lease)
                    last=time.monotonic()
                yield chunk
        finally:
            operations.finish(lease)
    headers={"Content-Disposition":f'attachment; filename="photosorter-{run_id}.zip"',
             "Cache-Control":"no-store"}
    return StreamingResponse(body(),media_type="application/zip",headers=headers)
