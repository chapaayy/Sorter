"""Periodic retention scan and recoverable batch cleanup independent of browsers."""
from __future__ import annotations
import logging
import signal
import threading
import time
from ..database import wait_and_initialize
from app.config import APP_STORAGE_ROOT
from app.storage.temporary import collect_abandoned
from app.storage.categories import ARCHIVE_SWEEP_SECONDS
from ..services import heartbeat
from ..services.update_gate import activity
from ..services import cleanup,retention,thumbnail_gc,temp_cleanup,auto_processing,archive_cache,reference_gc

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
                    from ..services.account_lifecycle import run_pending as account_pending
                    account_pending()
                    for batch_id,result in cleanup.process_pending():
                        if result not in ("busy","waiting","skipped"):
                            logging.info("Batch cleanup %s: %s",batch_id,result)
                except Exception:
                    logging.exception("Batch cleanup failure")
        stopped.wait(DELETION_POLL_SECONDS)

def run_cycle():
    global NEXT_GC
    from ..services.storage_maintenance import run_pending
    run_pending()
    expired=archive_cache.collect()
    scratch=collect_abandoned(APP_STORAGE_ROOT)
    if scratch:logging.info("Removed %s abandoned scratch operations",scratch)
    if expired:logging.info("Removed %s expired ZIP cache files",expired)
    for batch_id,run_id in auto_processing.schedule_ready():
        logging.info('Auto processing queued for %s: %s',batch_id,run_id)
    for batch_id in retention.due_batch_ids():
        cleanup.request(batch_id,only_if_due=True)
    removed=cleanup.reconcile_incomplete_exports()
    if removed:logging.info("Removed %s orphaned FO staging directories",len(removed))
    if time.monotonic()>=NEXT_GC:
        NEXT_GC=time.monotonic()+600
        from ..services.archive_activity import collect_expired
        collect_expired()
        abandoned=temp_cleanup.reclaim_abandoned(limit=50)+temp_cleanup.reclaim_finalized_parts(limit=50)
        if abandoned:logging.info("Reclaimed %s abandoned upload parts",abandoned)
        refs=reference_gc.collect(limit=50)
        if any(refs[k] for k in ('retired_versions','objects','embeddings','parts','cancelled_imports')):
            logging.info('Reference lifecycle cleanup: %s',refs)
        from app.logging import events
        from ..database import connect
        with connect() as db:
            terminal=[r['id'] for r in db.execute("SELECT id FROM jobs WHERE status IN ('completed','completed_with_errors','failed','stopped','interrupted')").fetchall()]
        events.prune_terminal(terminal)
        stale=thumbnail_gc.collect(limit=100)
        if stale:logging.info("Cleared %s unreferenced thumbnails",stale)

def main():
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    wait_and_initialize()
    pulse,thread=heartbeat.start("cleanup")
    deletions=threading.Thread(name="batch-deletions",target=run_deletions,args=(STOPPED,))
    deletions.start()
    from ..storage.reconciliation import Reconciler
    def accounting_loop():
        reconciler=Reconciler()
        while not STOPPED.is_set():
            with activity() as allowed:
                if allowed:
                    try:reconciler.tick()
                    except Exception:
                        logging.exception('Storage reconciliation failure')
                        reconciler.close()
                        reconciler=Reconciler()
            STOPPED.wait(1 if reconciler.busy else 5)
        reconciler.close()
    accounting=threading.Thread(name='storage-accounting',target=accounting_loop)
    accounting.start()
    try:
        while not STOPPED.is_set():
            with activity() as allowed:
                if allowed:
                    try:run_cycle()
                    except Exception:logging.exception("Lifecycle maintenance failure")
            STOPPED.wait(ARCHIVE_SWEEP_SECONDS)
    finally:
        STOPPED.set()
        deletions.join()
        accounting.join()
        pulse.set()
        thread.join()

if __name__=="__main__":main()
