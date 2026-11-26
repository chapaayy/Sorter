"""Bounded incremental dirty-path processing and periodic reconciliation.
Single DB advisory leader. Crash restarts a fresh generation; no stale sweep
until enumeration completes. Never deletes data files.
"""
from __future__ import annotations
import os,stat,time,uuid
from pathlib import Path
from app import config
from ..database import connect
from .registry import observe,stat_key
from .result_audit import ResultAudit
LEADER=723409190
BATCH=1024
FULL_INTERVAL=900
TEMP_INTERVAL=5

def walk(root,key="app",onerror=lambda:None):
    """Descriptor-relative streaming walk. A symlink leaf is reported, never traversed."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    root=Path(root)
    try:fd=os.open(root,flags)
    except OSError:onerror();return
    try:
        for part in key.split("/")[1:]:
            child=os.open(part,flags,dir_fd=fd);os.close(fd);fd=child
        yield from _walk_fd(fd,key,flags,onerror)
    except FileNotFoundError:return
    except OSError:onerror()
    finally:os.close(fd)

def _walk_fd(fd,key,flags,onerror,depth=0):
    if depth>64:onerror();return
    with os.scandir(fd) as entries:
        for entry in entries:
            child_key=key+"/"+entry.name
            # Yield directories too so a huge empty tree consumes the budget.
            yield child_key
            try:
                if entry.is_dir(follow_symlinks=False):
                    child=os.open(entry.name,flags,dir_fd=fd)
                    try:yield from _walk_fd(child,child_key,flags,onerror,depth+1)
                    finally:os.close(child)
            except FileNotFoundError:pass
            except OSError:onerror()

class Reconciler:
    def __init__(self,root=None):
        self.root=Path(root or config.APP_STORAGE_ROOT)
        self.full=None;self.temp=None;self.dirty=None;self.results=None
        self.generation=None;self.last_full=0;self.last_temp=0;self.errors=0
        self.sweep=False;self.cursor=0;self.temp_cursor=0;self.reservation_cursor=None
    def error(self):self.errors+=1
    def _consume(self,db,iterator,limit,generation=None):
        keys=[];done=False
        deadline=time.monotonic()+0.25
        while len(keys)<limit and time.monotonic()<deadline:
            try:keys.append(next(iterator))
            except StopIteration:done=True;break
        observe(db,self.root,keys,generation,onerror=self.error)
        return done
    def tick(self,limit=BATCH):
        with connect() as db:
            if not db.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok",(LEADER,)).fetchone()["ok"]:return False
            from .admission import LOCK
            if not db.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok",(LOCK,)).fetchone()["ok"]:return False
            # Coalesced exact file updates first; trees are streamed over ticks.
            rows=db.execute("SELECT path,revision,subtree FROM storage_dirty WHERE NOT subtree ORDER BY touched_at LIMIT %s",(limit,)).fetchall()
            observe(db,self.root,[r["path"] for r in rows],self.generation,onerror=self.error)
            for row in rows:
                db.execute("DELETE FROM storage_dirty WHERE path=%s AND revision=%s",(row["path"],row["revision"]))
            if self.dirty is None:
                # Most scratch scopes are short-lived; discard their dirty key
                # without spending two ticks on an empty directory. Preserve
                # scopes with recorded files for the bounded recheck below.
                candidates=db.execute("SELECT path,revision FROM storage_dirty WHERE subtree ORDER BY touched_at LIMIT %s",(limit,)).fetchall()
                for row in candidates:
                    try:stat_key(self.root,row["path"])
                    except (FileNotFoundError,NotADirectoryError):
                        if not db.execute("SELECT 1 FROM storage_files WHERE starts_with(path,%s) LIMIT 1",(row["path"]+"/",)).fetchone():
                            db.execute("DELETE FROM storage_dirty WHERE path=%s AND revision=%s",(row["path"],row["revision"]))
                            continue
                    except OSError:pass
                    self.dirty=(row,walk(self.root,row["path"],self.error),0)
                    break
            if self.dirty:
                row,iterator,cursor=self.dirty
                if iterator is not None:
                    if self._consume(db,iterator,limit,self.generation):self.dirty=(row,None,0)
                else:
                    # Recheck old paths rather than blindly deleting a tree:
                    # another writer may already have recreated a file.
                    old=db.execute("SELECT id,path FROM storage_files WHERE id>%s AND (path=%s OR starts_with(path,%s)) ORDER BY id LIMIT %s",
                                   (cursor,row["path"],row["path"]+"/",limit)).fetchall()
                    observe(db,self.root,[r["path"] for r in old],self.generation,onerror=self.error)
                    if old:self.dirty=(row,None,old[-1]["id"])
                    else:
                        db.execute("DELETE FROM storage_dirty WHERE path=%s AND revision=%s",(row["path"],row["revision"]))
                        self.dirty=None
            now=time.monotonic();finished=False
            requested=db.execute("""SELECT requested_at IS NOT NULL AND
                (started_at IS NULL OR requested_at>started_at) AS pending FROM storage_accounting_state""").fetchone()["pending"]
            if self.full is None and not self.sweep and self.results is None and (requested or not self.last_full or now-self.last_full>=FULL_INTERVAL):
                self.generation=uuid.uuid4();self.errors=0;self.cursor=0
                self.full=walk(self.root,onerror=self.error)
                db.execute("UPDATE storage_accounting_state SET generation=%s,started_at=now(),errors=0",(self.generation,))
            if self.full is not None and self._consume(db,self.full,limit,self.generation):
                self.full=None;self.sweep=True
            if self.sweep:
                old=db.execute("SELECT id,path FROM storage_files WHERE id>%s AND seen_generation IS DISTINCT FROM %s ORDER BY id LIMIT %s",
                               (self.cursor,self.generation,limit)).fetchall()
                observe(db,self.root,[r["path"] for r in old],self.generation,onerror=self.error)
                if old:self.cursor=old[-1]["id"]
                else:
                    self.sweep=False;self.results=ResultAudit()
            if self.results is not None and self.results.step(db,self.root,limit=min(limit,256)):
                db.execute("UPDATE storage_accounting_state SET reconciled_at=now(),errors=%s",(self.errors,))
                self.results=None;self.last_full=now;finished=True
            # Native writes are sampled in the temporary subtree, not traced.
            if self.temp is None and now-self.last_temp>=TEMP_INTERVAL:
                self.temp=walk(self.root,"app/temporary",self.error)
            if self.temp is not None and self._consume(db,self.temp,limit,self.generation):
                self.temp=None;self.last_temp=now
            # Recheck disappeared temporary paths in bounded ID windows even
            # between full passes (native unlink and crashed process recovery).
            old=db.execute("SELECT id,path FROM storage_files WHERE scope='temporary' AND id>%s ORDER BY id LIMIT %s",
                           (self.temp_cursor,limit)).fetchall()
            observe(db,self.root,[r["path"] for r in old],self.generation,onerror=self.error)
            self.temp_cursor=old[-1]["id"] if old else 0
            from .reservations import recover
            self.reservation_cursor=recover(db,after=self.reservation_cursor)
            db.execute("UPDATE storage_accounting_state SET errors=%s WHERE errors IS DISTINCT FROM %s",(self.errors,self.errors))
            from .accounting import refresh
            refresh(db,force=finished)
            return True
    def close(self):
        for iterator in (self.full,self.temp,self.dirty[1] if self.dirty else None):
            if iterator is not None:iterator.close()
    @property
    def busy(self):return self.full is not None or self.sweep or self.dirty is not None or self.results is not None
