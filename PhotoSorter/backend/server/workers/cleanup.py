"""Periodic retention scan and recoverable batch cleanup independent of browsers."""
from __future__ import annotations
import logging
import signal
import time
from ..database import wait_and_initialize
from ..services import heartbeat
from ..services import cleanup,retention,thumbnail_gc,temp_cleanup,auto_processing,archive_retries,ad_layouts,ad_recognition

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
RUN=True
NEXT_GC=0.0

def stop(*_):
    global RUN
    RUN=False

def run_cycle():
    global NEXT_GC
    for run_id,state in archive_retries.process_pending(limit=1):
        logging.info('ZIP-only retry %s: %s',run_id,state)
    for batch_id,run_id in auto_processing.schedule_ready():
        logging.info('Auto processing queued for %s: %s',batch_id,run_id)
    for batch_id in retention.due_batch_ids():
        cleanup.request(batch_id,only_if_due=True)
    for batch_id,result in cleanup.process_pending():
        logging.info("Batch cleanup %s: %s",batch_id,result)
    removed=cleanup.reconcile_incomplete_exports()
    if removed:logging.info("Removed %s orphaned unpublished exports",len(removed))
    if time.monotonic()>=NEXT_GC:
        NEXT_GC=time.monotonic()+600
        abandoned=temp_cleanup.reclaim_abandoned(limit=50)
        if abandoned:logging.info("Reclaimed %s abandoned upload parts",abandoned)
        stale=thumbnail_gc.collect(limit=100)
        if stale:logging.info("Cleared %s unreferenced thumbnails",stale)
        scheduled=ad_layouts.requeue_stale_models()
        if scheduled:logging.info("Queued %s stale advertising layouts",scheduled)
        retired=ad_layouts.gc_retired(limit=25)
        if retired:logging.info("Cleared %s retired advertising layouts",retired)
        ad_recognition.prune_old_layout_cache()

def main():
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    wait_and_initialize()
    pulse,thread=heartbeat.start("cleanup")
    while RUN:
        try:run_cycle()
        except Exception:logging.exception("Lifecycle maintenance failure")
        for _ in range(30):
            if not RUN:break
            time.sleep(1)

if __name__=="__main__":main()
