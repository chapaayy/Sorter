"""Periodic retention scan and recoverable batch cleanup independent of browsers."""
from __future__ import annotations
import logging
import signal
import threading
import time
from ..database import wait_and_initialize
from ..services import heartbeat
from ..services.update_gate import activity
from ..services import cleanup,retention,thumbnail_gc,temp_cleanup,auto_processing,archive_retries

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
STOPPED=threading.Event()
NEXT_GC=0.0
DELETION_POLL_SECONDS=1.0

def stop(*_):
    STOPPED.set()

def run_deletions(stopped):
    """Keep deletes responsive even while maintenance is rebuilding a ZIP."""
    while not stopped.is_set():
        with activity() as allowed:
            if allowed:
                try:
                    for batch_id,result in cleanup.process_pending():
                        if result not in ("busy","waiting","skipped"):
                            logging.info("Batch cleanup %s: %s",batch_id,result)
                except Exception:
                    logging.exception("Batch cleanup failure")
        stopped.wait(DELETION_POLL_SECONDS)

def run_cycle():
    global NEXT_GC
    for run_id,state in archive_retries.process_pending(limit=1):
        logging.info('ZIP-only retry %s: %s',run_id,state)
    for batch_id,run_id in auto_processing.schedule_ready():
        logging.info('Auto processing queued for %s: %s',batch_id,run_id)
    for batch_id in retention.due_batch_ids():
        cleanup.request(batch_id,only_if_due=True)
    removed=cleanup.reconcile_incomplete_exports()
    if removed:logging.info("Removed %s orphaned unpublished exports",len(removed))
    if time.monotonic()>=NEXT_GC:
        NEXT_GC=time.monotonic()+600
        abandoned=temp_cleanup.reclaim_abandoned(limit=50)
        if abandoned:logging.info("Reclaimed %s abandoned upload parts",abandoned)
        stale=thumbnail_gc.collect(limit=100)
        if stale:logging.info("Cleared %s unreferenced thumbnails",stale)

def main():
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    wait_and_initialize()
    pulse,thread=heartbeat.start("cleanup")
    deletions=threading.Thread(name="batch-deletions",target=run_deletions,args=(STOPPED,))
    deletions.start()
    try:
        while not STOPPED.is_set():
            with activity() as allowed:
                if allowed:
                    try:run_cycle()
                    except Exception:logging.exception("Lifecycle maintenance failure")
            STOPPED.wait(30)
    finally:
        STOPPED.set()
        deletions.join()
        pulse.set()
        thread.join()

if __name__=="__main__":main()
