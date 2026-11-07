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

def workload_settings():
    with connect() as db:
        row=db.execute("""SELECT cpu_mode,fo_cpu_threads,reference_cpu_threads
            FROM processing_settings WHERE id=1""").fetchone()
    return {
        "mode":row["cpu_mode"],
        "fo_threads":row["fo_cpu_threads"],
        "reference_threads":row["reference_cpu_threads"],
        "max_threads":max_threads(),
        "thumbnail_cpu_quota":float(os.environ.get("PHOTOSORTER_THUMBNAIL_CPUS","0.35")),
        "cleanup_cpu_quota":float(os.environ.get("PHOTOSORTER_CLEANUP_CPUS","0.25")),
        "zip_mode":"single_thread_in_worker",
        "docker_limits_editable":False,
        "applies":"next_task",
    }

def update_workloads(mode:str,fo_threads:int,reference_threads:int):
    from fastapi import HTTPException
    if mode not in ("manual","auto") or not (1<=fo_threads<=max_threads()
                                         and 1<=reference_threads<=max_threads()):
        raise HTTPException(422,"Недопустимые параметры CPU")
    with connect() as db:
        db.execute("""UPDATE processing_settings SET cpu_mode=%s,fo_cpu_threads=%s,
               reference_cpu_threads=%s,cpu_threads=%s,updated_at=now()
               WHERE id=1""",(mode,fo_threads,reference_threads,fo_threads))
    return workload_settings()

def for_worker(db,kind=None):
    row=db.execute("""SELECT cpu_mode,fo_cpu_threads,reference_cpu_threads,cpu_threads
        FROM processing_settings WHERE id=1""").fetchone()
    if not row:return 7
    if row["cpu_mode"]=="auto":return max_threads()
    if kind=="fo_processing":return min(max_threads(),row["fo_cpu_threads"])
    if kind=="reference_preparation":return min(max_threads(),row["reference_cpu_threads"])
    return min(max_threads(),row["cpu_threads"])
