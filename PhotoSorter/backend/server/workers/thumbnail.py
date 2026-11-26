"""Low-priority independent thumbnail consumer; no heavy image work in API."""
from __future__ import annotations
import logging,os,signal,time
from ..database import wait_and_initialize
from ..services import heartbeat
from ..services.update_gate import activity
from ..services.account_activity import lease as account_activity
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
        with activity() as allowed:
            if not allowed:
                time.sleep(2)
                continue
            try:
                # A thumbnail may publish to the recipient's namespace.
                # Hold a shared account lease from claim through completion;
                # do not claim or consume retries during an exclusive move.
                task=None
                with account_activity() as safe:
                    if safe:
                        task=thumbnails.claim()
                        if task:
                            result=thumbnails.complete(task)
                            if result=="error":logging.warning("Preview failed for upload %s",task["upload_id"])
                if not task:time.sleep(2)
            except Exception:
                logging.exception("Thumbnail worker failure")
                time.sleep(3)

if __name__=="__main__":main()
