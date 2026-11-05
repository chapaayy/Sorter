"""Low-priority independent thumbnail consumer; no heavy image work in API."""
from __future__ import annotations
import logging,os,signal,time
from ..database import wait_and_initialize
from ..services import heartbeat
from ..services import thumbnails
RUN=True
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")

def stop(*_):
    global RUN
    RUN=False

def main():
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:os.nice(10)
    except OSError:pass
    wait_and_initialize()
    pulse,thread=heartbeat.start("thumbnail")
    while RUN:
        try:
            task=thumbnails.claim()
            if task:
                result=thumbnails.complete(task)
                if result=="error":logging.warning("Preview failed for upload %s",task["upload_id"])
            else:
                time.sleep(2)
        except Exception:
            logging.exception("Thumbnail worker failure")
            time.sleep(3)

if __name__=="__main__":main()
