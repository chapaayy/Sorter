"""Assert production registry against real files, not a second production counter."""
from app import config
from server import database
from server.storage.reconciliation import Reconciler
from server.storage.accounting import refresh,snapshot
from server.storage.registry import key_for

def settle(reconciler=None):
    owned=reconciler is None
    r=reconciler or Reconciler()
    try:
        for _ in range(120):
            assert r.tick()
            with database.connect() as db:
                pending=db.execute("SELECT count(*) AS n FROM storage_dirty").fetchone()["n"]
            if not pending and not r.busy and r.temp is None:break
        else:raise AssertionError("Registry did not converge")
        with database.connect() as db:refresh(db,force=True)
        return snapshot()
    finally:
        if owned:r.close()

def observed(path):
    with database.connect() as db:
        return db.execute("SELECT * FROM storage_accounted_files WHERE path=%s",(key_for(path),)).fetchone()

def exact(path):
    row=observed(path)
    assert row is not None,path
    info=path.lstat()
    assert row["logical_bytes"]==info.st_size
    assert row["allocated_bytes"]==info.st_blocks*512
    assert row["inode"]==info.st_ino and row["device"]==info.st_dev
    return row
