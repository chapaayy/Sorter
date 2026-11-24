"""Observation of existing admission/operation leases; NOT a new quota policy."""
from contextlib import contextmanager
import logging,uuid
from ..database import connect

@contextmanager
def reservation(kind,requested):
    from .. import database
    if not database.DB_URL:
        yield;return
    token=uuid.uuid4()
    key=token.int & ((1<<63)-1)
    # Session advisory lock survives commit and is released by PostgreSQL on
    # SIGKILL/disconnect. No reliance on PID or an indefinitely stale heartbeat.
    with connect() as db:
        db.execute("SELECT pg_advisory_lock(%s)",(key,))
        db.execute("INSERT INTO storage_reservations(id,kind,lease_key,requested_bytes) VALUES(%s,%s,%s,%s)",
                   (token,kind,key,max(0,int(requested))))
        db.commit()
        try:yield
        finally:
            db.execute("DELETE FROM storage_reservations WHERE id=%s",(token,))
            db.commit()

def recover(db,limit=100):
    rows=db.execute("SELECT id,lease_key FROM storage_reservations ORDER BY created_at LIMIT %s",(limit,)).fetchall()
    for row in rows:
        if db.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok",(row["lease_key"],)).fetchone()["ok"]:
            db.execute("DELETE FROM storage_reservations WHERE id=%s",(row["id"],))
