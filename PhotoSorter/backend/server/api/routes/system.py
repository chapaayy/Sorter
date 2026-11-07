"""Latency ring, process metrics and live queue counters (no personal data)."""
from __future__ import annotations
import os,resource,statistics,threading,time
from collections import deque
from datetime import datetime,timezone
from fastapi import APIRouter
from ...database import connect
from ...services.disk_guard import stat,reserve
from ...services import heartbeat
from app.config import DATA_DIR

router=APIRouter(prefix="/api/system",tags=["system"])
START=time.monotonic()
LATENCIES=deque(maxlen=2048)
_LOCK=threading.Lock()

def record(seconds):
    with _LOCK:LATENCIES.append(max(0,float(seconds)))

def latency_snapshot():
    with _LOCK:data=sorted(LATENCIES)
    if not data:return {"samples":0,"p50_ms":None,"p95_ms":None,"max_ms":None}
    def at(frac):return round(data[max(0,min(len(data)-1,int(len(data)*frac+.9999)-1))]*1000,2)
    return {"samples":len(data),"p50_ms":at(.5),"p95_ms":at(.95),
            "max_ms":round(data[-1]*1000,2)}

@router.get("/status")
def system_status():
    with connect() as db:
        jobs=db.execute("""SELECT status,count(*) AS n FROM jobs
             WHERE status IN ('queued','running','stopping')
             GROUP BY status""").fetchall()
        thumbs=db.execute("""SELECT state,count(*) AS n FROM thumbnail_tasks
             GROUP BY state""").fetchall()
        services=heartbeat.status(db)
        from ...services.compute_settings import for_worker
        threads=for_worker(db)
    total,available=stat(DATA_DIR)
    return {"at":datetime.now(timezone.utc).isoformat(),
        "worker":{"queue":{x["status"]:x["n"] for x in jobs},
                  "expected_threads":threads},
        "thumbnails":{x["state"]:x["n"] for x in thumbs},
        "services":services,
        "disk":{"total_bytes":total,"available_bytes":available,
                "reserved_bytes":reserve(total)},
        "api":{"uptime_seconds":round(time.monotonic()-START,1),
               "latency":latency_snapshot(),
               "rss_peak_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               "allowed_cpus":sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else None}}

@router.post("/cache/cleanup")
def clean_unused_thumbnails():
    """Manual, owner-checked cleanup only of orphaned preview cache."""
    from ..services.thumbnails import gc_unowned,gc_incomplete
    return {"removed":gc_unowned(limit=200)+gc_incomplete(limit=200)}
