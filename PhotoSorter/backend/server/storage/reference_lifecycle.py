"""Shared reference/preview read pins versus exclusive dependency collection.

The FIFO lock serializes publication/claim; this separate lock protects readers
that outlive SQL statements (including streamed responses and preview rendering).
Never acquire the FIFO lock while holding a shared pin.
"""
from ..database import connect

LOCK=723409144

class ReadPin:
    def __init__(self):
        self.context=connect()
        db=self.context.__enter__()
        try:
            db.execute("SELECT pg_advisory_lock_shared(%s)",(LOCK,))
            db.commit()
        except BaseException:
            self.context.__exit__(*__import__("sys").exc_info())
            raise
        self.closed=False

    def close(self):
        if not self.closed:
            self.closed=True
            self.context.__exit__(None,None,None)

    def __enter__(self):return self
    def __exit__(self,*_):self.close()

def try_collect(db):
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    return db.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok",(LOCK,)).fetchone()["ok"]
