"""CPU-only MegaLoc thread preference, persisted for the next FIFO task.

Only the running worker sets PyTorch thread count. Docker cpuset/quota limits
remain fixed by the Compose installation; this API never controls Docker.
"""
from __future__ import annotations
import os
from ..database import connect

def max_threads():
    # This is the upper bound of the *worker* cgroup, not the API process.
    available=min(32,os.cpu_count() or 4)
    try:
        quota=float(os.environ.get("PHOTOSORTER_WORKER_CPUS","7"))
        available=min(available,max(1,int(quota)))
    except ValueError:
        pass
    cpuset=os.environ.get("PHOTOSORTER_WORKER_CPUSET","0-6")
    try:
        cpus=set()
        for chunk in cpuset.split(","):
            parts=chunk.strip().split("-")
            if len(parts)==1:cpus.add(int(parts[0]))
            else:cpus.update(range(int(parts[0]),int(parts[1])+1))
        if cpus:available=min(available,len(cpus))
    except ValueError:
        pass
    return max(1,available)

def read():
    with connect() as db:
        row=db.execute("SELECT cpu_threads FROM processing_settings WHERE id=1").fetchone()
    return {
        "threads":row["cpu_threads"],
        "max_threads":max_threads(),
        "applies":"next_task",
        "docker_quota_changes":False,
    }

def update(threads:int):
    from fastapi import HTTPException
    if threads<1 or threads>max_threads():
        raise HTTPException(422,f"Доступно от 1 до {max_threads()} потоков MegaLoc")
    with connect() as db:
        db.execute("UPDATE processing_settings SET cpu_threads=%s,updated_at=now() WHERE id=1",(threads,))
    return read()

def for_worker(db):
    row=db.execute("SELECT cpu_threads FROM processing_settings WHERE id=1").fetchone()
    return row["cpu_threads"] if row else 7
