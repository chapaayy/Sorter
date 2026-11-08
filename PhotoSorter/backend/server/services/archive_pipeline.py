"""Automatic final ZIP stage, shared by the worker and explicit archive repair."""
from __future__ import annotations
from pathlib import Path
from app.config import DATA_DIR
from app.results.repository import load_model,load_run
from ..storage.paths import owned_file
from . import archives

def selections(run_id):
    rows=load_model(run_id,"megaloc")
    root=DATA_DIR/"outputs"
    selected=[]
    for item in rows:
        source=owned_file(Path(item["copy"]),root)
        if not source.is_file():
            raise FileNotFoundError("Отсутствует готовая фотография: "+source.name)
        selected.append((source,archives.archive_member(item["assigned_sam"],source.name)))
    if not selected:
        raise RuntimeError("Готовых фотографий для архива нет")
    info=load_run(run_id)
    if info.get("ad_pipeline",{}).get("enabled"):
        from .ad_pipeline import best_archive_entries
        selected.extend(best_archive_entries(run_id,info["ad_pipeline"]))
    return selected

def build_for_job(job):
    selected=selections(job.info["id"])
    job.info["archive_state"]="preparing"
    total=sum(path.stat().st_size for path,_ in selected)
    job.progress("megaloc","archive",0,total,"Подготовка полного ZIP")
    job.log("INFO","Создание полного ZIP-архива","megaloc")
    try:
        archive=archives.prepare(job.info["id"],None,selected,
            progress=lambda done,size: job.progress("megaloc","archive",done,size,"Подготовка ZIP"),
            should_stop=job.stopped)
        job.info["archive_state"]="ready"
        job.info["archive_bytes"]=archive.stat().st_size
        job.progress("megaloc","archive",total,total,"Архив готов")
        job.log("INFO","ZIP готов к скачиванию","megaloc")
    except BaseException:
        job.info["archive_state"]="failed"
        job.save()
        raise
