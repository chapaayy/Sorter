"""FO run status presentation; scheduling is owned exclusively by work_queue."""
from __future__ import annotations

TERMINAL=("completed","completed_with_errors","failed","stopped","interrupted")

def decorated(db,row):
    from . import work_queue
    info=dict(row["snapshot"])
    info["status"]=row["status"]
    info["queue_position"]=work_queue.position(db,row["id"]) if row["status"]=="queued" else None
    if row.get("started_at"):info["actual_started_at"]=row["started_at"].isoformat()
    if row.get("finished_at"):info["actual_finished_at"]=row["finished_at"].isoformat()
    return info
