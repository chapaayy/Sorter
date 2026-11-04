"""Dedicated CPU process: durable one-job-at-a-time PostgreSQL queue consumer."""
from __future__ import annotations
import logging
import signal
import time
from psycopg.types.json import Jsonb
from .database import connect,wait_and_initialize
from .jobs import ServerJob

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
RUN=True

def stop(*_):
    global RUN
    RUN=False


def claim_job():
    with connect() as db:
        # Multiple worker containers also cannot claim the same queued job.
        row=db.execute("SELECT id,snapshot FROM jobs WHERE status='queued' "
                       'ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1').fetchone()
        if row:
            info=row['snapshot'];info['status']='running'
            db.execute('UPDATE jobs SET status=%s,snapshot=%s,updated_at=now() WHERE id=%s',
                       ('running',Jsonb(info),row['id']))
            return info
    return None


def main():
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    wait_and_initialize()
    with connect() as db:
        db.execute("UPDATE jobs SET status='interrupted',snapshot=jsonb_set(snapshot,'{status}', to_jsonb('interrupted'::text)),updated_at=now() WHERE status IN ('running','stopping')")
    logging.info('MegaLoc worker started (CPU, PostgreSQL-backed queue)')
    while RUN:
        info=claim_job()
        if info:
            logging.info('Processing %s',info['id'])
            try:ServerJob(info).run()
            except Exception:logging.exception('Unhandled job exception: %s',info['id'])
        else:time.sleep(1)

if __name__=='__main__':main()
