"""Periodic retention scan and recoverable batch cleanup independent of browsers."""
from __future__ import annotations
import logging
import signal
import time
from ..database import wait_and_initialize
from ..services import cleanup,retention

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
RUN=True

def stop(*_):
    global RUN
    RUN=False

def run_cycle():
    for batch_id in retention.due_batch_ids():
        cleanup.request(batch_id)
    for batch_id,result in cleanup.process_pending():
        logging.info("Batch cleanup %s: %s",batch_id,result)

def main():
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    wait_and_initialize()
    while RUN:
        try:run_cycle()
        except Exception:logging.exception("Lifecycle maintenance failure")
        for _ in range(30):
            if not RUN:break
            time.sleep(1)

if __name__=="__main__":main()
