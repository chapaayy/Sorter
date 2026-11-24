"""Build download plans from the saved MegaLoc results."""
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
    """Finalize the run without creating or opening a ZIP."""
    for key in ("archive_file","archive_bytes","archive_title","archive_retry"):
        job.info.pop(key,None)
    job.info["archive_state"]="on_demand"
