"""Build download plans from the saved MegaLoc results."""
from __future__ import annotations
from app.results.repository import load_model
from ..database import connect
from . import archive_layout

def named_plan(run_id,batch_id,title=None,sam=None):
    rows=load_model(run_id,"megaloc")
    with connect() as db:
        if title is None:
            title=db.execute("SELECT display_name FROM batches WHERE id=%s",(batch_id,)).fetchone()["display_name"]
        return archive_layout.build(db,run_id,batch_id,title,rows,sam)

def mark_on_demand(job):
    """Finalize the run without creating or opening a ZIP."""
    for key in ("archive_file","archive_bytes","archive_title","archive_retry"):
        job.info.pop(key,None)
    job.info["archive_state"]="on_demand"
