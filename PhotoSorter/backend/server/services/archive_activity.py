"""Best-effort personal ZIP preparation notifications; never own the ZIP or lease."""
from contextlib import contextmanager
import logging
import uuid

from ..database import connect

@contextmanager
def track(user,kind):
    token=None
    if user:
        try:
            with connect() as db:
                token=uuid.uuid4()
                db.execute("INSERT INTO favicon_archive_activity(id,actor_id,kind,state) VALUES(%s,%s,%s,'running')",
                           (token,user["id"],kind))
        except Exception:
            token=None
            logging.exception("Could not record ZIP preparation")
    state="failed"
    try:
        yield
        state="completed"
    finally:
        if token is not None:
            try:
                with connect() as db:
                    db.execute("UPDATE favicon_archive_activity SET state=%s,updated_at=now() WHERE id=%s",
                               (state,token))
            except Exception:
                logging.exception("Could not record ZIP outcome")

def collect_expired():
    # A crashed API may leave an unfinished notification. Expire it rather than
    # inventing a successful completion. Never delete archive data here.
    with connect() as db:
        db.execute("DELETE FROM favicon_archive_activity WHERE updated_at<now()-interval '24 hours'")
