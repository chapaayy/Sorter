"""Independent, bounded worker presence writer; never pretend queue length is health."""
from __future__ import annotations
import logging
import threading
import uuid
from ..database import connect

SERVICES=frozenset(("megaloc","thumbnail","cleanup"))
MAX_AGE_SECONDS=35

def touch(service,instance):
    if service not in SERVICES:raise ValueError("Invalid worker role")
    with connect() as db:
        db.execute("""INSERT INTO service_heartbeats(service,instance_id,seen_at)
          VALUES (%s,%s,now()) ON CONFLICT(service)
          DO UPDATE SET instance_id=excluded.instance_id,seen_at=now()""",
          (service,instance))

def status(db):
    rows=db.execute("""SELECT service,instance_id,seen_at,
              seen_at>now()-interval '35 seconds' AS alive
              FROM service_heartbeats""").fetchall()
    active={r["service"]:r for r in rows}
    return {
      name:{"alive":bool(active.get(name,{}).get("alive",False)),
            "last_seen":active[name]["seen_at"].isoformat() if name in active else None}
      for name in ("megaloc","thumbnail","cleanup")
    }

def start(service,interval=10):
    if service not in SERVICES:raise ValueError("Invalid worker role")
    instance=uuid.uuid4()
    stopped=threading.Event()
    def loop():
        while not stopped.is_set():
            try:touch(service,instance)
            except Exception:logging.exception("Heartbeat failure for %s",service)
            stopped.wait(interval)
    thread=threading.Thread(name="heartbeat-"+service,target=loop,daemon=True)
    thread.start()
    return stopped,thread
