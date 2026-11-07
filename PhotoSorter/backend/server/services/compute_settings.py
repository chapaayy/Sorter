"""CPU-only MegaLoc thread preference, persisted for the next FIFO task.

Only the running worker sets PyTorch thread count. Docker cpuset/quota limits
remain fixed by the Compose installation; this API never controls Docker.
"""
from __future__ import annotations
import os
from ..database import connect

def read():
    with connect() as db:
        row=db.execute("SELECT cpu_threads FROM processing_settings WHERE id=1").fetchone()
    return {
        "threads":row["cpu_threads"],
        "max_threads":min(32,os.cpu_count() or 4),
        "applies":"next_task",
        "docker_quota_changes":False,
    }

def update(threads:int):
    with connect() as db:
        db.execute("UPDATE processing_settings SET cpu_threads=%s,updated_at=now() WHERE id=1",(threads,))
    return read()

def for_worker(db):
    row=db.execute("SELECT cpu_threads FROM processing_settings WHERE id=1").fetchone()
    return row["cpu_threads"] if row else 7
