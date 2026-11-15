"""Automatic final ZIP stage, shared by the worker and explicit archive repair."""
from __future__ import annotations
from pathlib import Path
from app.results.repository import load_model
from ..database import connect
from ..storage.paths import owned_directory,owned_file,run_dir
from . import archive_layout,archives

def legacy_selections(run_id):
    """Only used to check pre-upgrade cached archives, never to create them."""
    rows=load_model(run_id,"megaloc")
    run=owned_directory(run_dir(run_id,archives.output_root()),archives.output_root())
    root=owned_directory(run/"megaloc",run)
    selected=[]
    for item in rows:
        source=owned_file(Path(item["copy"]),root)
        if not source.is_file():
            raise FileNotFoundError("Отсутствует готовая фотография: "+source.name)
        selected.append((source,archives.archive_member(item["assigned_sam"],source.name)))
    if not selected:
        raise ValueError("Готовых фотографий для архива нет")
    return selected

def named_plan(run_id,batch_id,title=None,sam=None):
    rows=load_model(run_id,"megaloc")
    with connect() as db:
        if title is None:
            title=db.execute("SELECT display_name FROM batches WHERE id=%s",(batch_id,)).fetchone()["display_name"]
        return archive_layout.build(db,run_id,batch_id,title,rows,sam)

def build_for_job(job):
    try:
        plan=named_plan(job.info["id"],job.info["batch_id"])
        job.info["archive_state"]="preparing"
        total=sum(path.stat().st_size for path,_ in plan.files)
        job.progress("megaloc","archive",0,total,"Подготовка полного ZIP")
        job.log("INFO","Создание полного ZIP-архива","megaloc")
        archive=archives.prepare(job.info["id"],None,plan.files,
            progress=lambda done,size: job.progress("megaloc","archive",done,size,"Подготовка ZIP"),
            should_stop=job.stopped)
        job.info.update(archive_state="ready",archive_bytes=archive.stat().st_size,
                        archive_file=archive.name,archive_title=plan.title)
        job.progress("megaloc","archive",total,total,"Архив готов")
        job.log("INFO","ZIP готов к скачиванию","megaloc")
    except BaseException:
        job.info["archive_state"]="failed"
        job.save()
        raise
