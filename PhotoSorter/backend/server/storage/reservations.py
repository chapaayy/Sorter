"""Atomic admission leases with crash recovery and registry handoff."""
from contextlib import contextmanager
from pathlib import Path
import uuid
from ..database import connect
from app import config
from . import admission
from .registry import key_for,observe,note

def sync_paths(db,keys,tree_key=None):
    # Only the private operation tree, never a global scan. Include vanished
    # rows so atomic rename/delete is accounted for before releasing the lease.
    keys=set(keys)
    if tree_key:
        from .reconciliation import walk
        keys.update(walk(config.APP_STORAGE_ROOT,tree_key))
        keys.update(r["path"] for r in db.execute("SELECT path FROM storage_files WHERE starts_with(path,%s)",(tree_key+"/",)))
    if keys:observe(db,config.APP_STORAGE_ROOT,sorted(keys))

class Lease:
    def __init__(self,token=None):self.token=token
    def track(self,path,*,tree=False):
        if self.token is None:return
        key=key_for(path)
        if not key:raise ValueError("Reservation path outside app storage")
        with connect() as db:
            admission.lock(db)
            db.execute("UPDATE storage_reservations SET work_key=%s,work_tree=%s WHERE id=%s",(key,tree,self.token))
    def publish(self,*paths):
        if self.token is None:return
        keys=[k for p in paths if (k:=key_for(p))]
        if not keys:return
        with connect() as db:
            admission.lock(db)
            db.execute("UPDATE storage_reservations SET publish_keys=publish_keys||%s::text[] WHERE id=%s",(keys,self.token))
    def sync(self,db=None):
        if self.token is None:return
        if db is None:
            with connect() as conn:return self.sync(conn)
        admission.lock(db)
        row=db.execute("SELECT * FROM storage_reservations WHERE id=%s",(self.token,)).fetchone()
        if row:_sync(db,row)

def _sync(db,row):
    key=row["work_key"]
    keys=list(row["publish_keys"])
    if key and not row["work_tree"]:keys.append(key)
    sync_paths(db,keys,key if row["work_tree"] else None)

@contextmanager
def reservation(kind,requested,*,owner=None,personal=0,temporary=None,path=None,work=None,tree=False):
    from .. import database
    if not database.DB_URL:
        from ..services import disk_guard
        if path is not None:disk_guard.check_admission(requested,path=path)
        yield Lease();return
    requested=admission.rounded(requested)
    temporary=requested if temporary is None else admission.rounded(temporary)
    personal=admission.rounded(personal)
    token=uuid.uuid4();key=token.int & ((1<<63)-1)
    # Session lock lives until exit or process death. The short transaction
    # lock serializes competing admissions, not their long-running writes.
    with connect() as db:
        db.execute("SELECT pg_advisory_lock(%s)",(key,))
        admission.lock(db)
        admission.admit(db,requested,temporary=temporary,owner=owner,personal=personal,path=path)
        db.execute("""INSERT INTO storage_reservations(id,kind,lease_key,requested_bytes,
            owner_id,personal_bytes,temporary_bytes,work_key,work_tree)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (token,kind,key,requested,owner,personal,temporary,key_for(work) if work is not None else None,tree))
        db.commit()
        try:yield Lease(token)
        finally:
            admission.lock(db)
            row=db.execute("SELECT * FROM storage_reservations WHERE id=%s",(token,)).fetchone()
            if row:_sync(db,row)
            db.execute("DELETE FROM storage_reservations WHERE id=%s",(token,))
            db.commit()

def recover(db,limit=100,after=None):
    """Advance through all leases, including those behind long-lived holders.

    A crash may reset the cursor safely: a deleted row never resurrects, and
    a complete pass wraps around to catch inserts before the cursor.
    """
    admission.lock(db)
    if after is None:
        rows=db.execute("SELECT * FROM storage_reservations ORDER BY id LIMIT %s",(limit,)).fetchall()
    else:
        rows=db.execute("SELECT * FROM storage_reservations WHERE id>%s ORDER BY id LIMIT %s",(after,limit)).fetchall()
    for row in rows:
        if db.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok",(row["lease_key"],)).fetchone()["ok"]:
            _sync(db,row)
            db.execute("DELETE FROM storage_reservations WHERE id=%s",(row["id"],))
    return rows[-1]["id"] if len(rows)==limit else None
