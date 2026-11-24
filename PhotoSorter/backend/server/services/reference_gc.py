"""Reference dependency collection: never prune by last access or cache size.

Version headers and notices are retained. Only superseded, unpinned member sets
can retire after the rollback grace period. Physical collection is a separate
two-pass candidate process. Unknown or mismatched paths fail closed.
"""
from __future__ import annotations
from pathlib import Path
from psycopg.errors import LockNotAvailable
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_prefix,uuid_key
from app.storage.filesystem import safe_unlink,file_stat
from ..database import connect
from ..reference_cache import location
from ..storage import reference_objects as objects
from ..storage.reference_lifecycle import try_collect

HISTORY_GRACE_SECONDS=30*86400
OBJECT_GRACE_SECONDS=86400
IMPORT_IDLE_SECONDS=30*86400

def _inconsistent_pins(db):
    # The FK is authoritative. A mismatched/missing pin in an existing
    # snapshot indicates incomplete graph evidence. Do not collect anything.
    return db.execute("""SELECT 1 FROM jobs j
        LEFT JOIN reference_library_versions v ON v.id=j.reference_version_id
        WHERE (j.reference_version_id IS NOT NULL OR j.snapshot ? 'reference_version_id'
               OR j.snapshot ? 'reference_members')
          AND (j.reference_version_id IS NULL OR v.id IS NULL OR v.members_retired_at IS NOT NULL
               OR j.snapshot->>'reference_version_id' IS DISTINCT FROM j.reference_version_id::text)
        LIMIT 1""").fetchone()

def mark_candidates(db):
    """Call under the FIFO gate after changing dependency state, or in GC."""
    for table in ("reference_physical_objects","reference_cache"):
        db.execute(f"""UPDATE {table} o SET unowned_since=NULL
            WHERE unowned_since IS NOT NULL AND EXISTS(
                SELECT 1 FROM reference_live_hashes h WHERE h.source_hash=o.source_hash)""")
        db.execute(f"""UPDATE {table} o SET unowned_since=now()
            WHERE unowned_since IS NULL AND NOT EXISTS(
                SELECT 1 FROM reference_live_hashes h WHERE h.source_hash=o.source_hash)""")

def _retire(db,limit,history_grace):
    versions=db.execute("""SELECT v.id FROM reference_library_versions v
        WHERE v.superseded_at IS NOT NULL AND v.members_retired_at IS NULL
          AND v.superseded_at<=now()-(%s*interval '1 second')
          AND NOT EXISTS(SELECT 1 FROM reference_library_state s WHERE s.current_version_id=v.id)
          AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.reference_version_id=v.id)
        ORDER BY v.superseded_at,v.id LIMIT %s FOR UPDATE""",(history_grace,limit)).fetchall()
    for row in versions:
        db.execute("DELETE FROM reference_version_members WHERE version_id=%s",(row["id"],))
        db.execute("UPDATE reference_library_versions SET members_retired_at=now() WHERE id=%s",(row["id"],))
    return len(versions)

def _expire_uploads(db,limit,idle):
    # A per-file row lock is the transfer lease. Never cancel an active
    # append, even if it started before the age check.
    rows=db.execute("""SELECT s.id FROM reference_import_sessions s
        WHERE s.upload_state='uploading' AND
          GREATEST(s.created_at,COALESCE(s.manifest_registered_at,s.created_at),
            COALESCE((SELECT max(f.updated_at) FROM reference_import_files f WHERE f.session_id=s.id),s.created_at))
             <=now()-(%s*interval '1 second')
        ORDER BY s.created_at,s.id LIMIT %s""",(idle,limit)).fetchall()
    cancelled=0
    for row in rows:
        sid=row["id"]
        try:
            with db.transaction():
                db.execute("SELECT upload_id FROM reference_import_files WHERE session_id=%s FOR UPDATE NOWAIT",(sid,)).fetchall()
                result=db.execute("""UPDATE reference_import_sessions s
                    SET upload_state='cancelled',preparation_state='stopped',error='Abandoned upload'
                    WHERE s.id=%s AND s.upload_state='uploading' AND
                    GREATEST(s.created_at,COALESCE(s.manifest_registered_at,s.created_at),
                    COALESCE((SELECT max(f.updated_at) FROM reference_import_files f WHERE f.session_id=s.id),s.created_at))
                     <=now()-(%s*interval '1 second') RETURNING id""",(sid,idle)).fetchone()
                cancelled+=bool(result)
        except LockNotAvailable:
            continue
    return cancelled

def _parts(db,limit):
    root=managed_prefix(Category.REFERENCE_UPLOAD_PART)
    if not root.is_dir() or root.is_symlink():return 0
    removed=0
    for folder in root.iterdir():
        if folder.is_symlink() or not folder.is_dir():continue
        try:sid=uuid_key(folder.name)
        except ValueError:continue
        for path in folder.iterdir():
            if path.is_symlink() or path.suffix!=".part":continue
            try:uid=uuid_key(path.stem)
            except ValueError:continue
            if path!=objects.partial(sid,uid):continue
            try:
                with db.transaction():
                    row=db.execute("""SELECT f.state,s.upload_state FROM reference_import_files f
                        JOIN reference_import_sessions s ON s.id=f.session_id
                        WHERE f.session_id=%s AND f.upload_id=%s FOR UPDATE OF f NOWAIT""",(sid,uid)).fetchone()
                    if not row or (row["state"]=="pending" and row["upload_state"]!="cancelled"):continue
                    safe_unlink(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT),missing_ok=True)
                    removed+=1
            except (LockNotAvailable,OSError,ValueError):continue
            if removed>=limit:return removed
    return removed

def collect(limit=50,*,history_grace=HISTORY_GRACE_SECONDS,grace_seconds=OBJECT_GRACE_SECONDS,import_idle=IMPORT_IDLE_SECONDS):
    report={"retired_versions":0,"objects":0,"embeddings":0,"parts":0,"cancelled_imports":0,"blocked":False}
    with connect() as db:
        if not try_collect(db) or _inconsistent_pins(db):
            report["blocked"]=True
            return report
        report["cancelled_imports"]=_expire_uploads(db,limit,import_idle)
        report["parts"]=_parts(db,limit)
        report["retired_versions"]=_retire(db,limit,history_grace)
        mark_candidates(db)
        # Commit candidate state before unlink in a subsequent production pass.
        # Grace=0 is only used by controlled tests.
        candidates=db.execute("""SELECT source_hash,model_signature,cache_path FROM reference_cache c
            WHERE unowned_since<=now()-(%s*interval '1 second')
              AND NOT EXISTS(SELECT 1 FROM reference_live_hashes h WHERE h.source_hash=c.source_hash)
            ORDER BY unowned_since,source_hash,model_signature LIMIT %s""",(grace_seconds,limit)).fetchall()
        for row in candidates:
            try:
                target=location(row["source_hash"],row["model_signature"])
                if Path(row["cache_path"])!=target:continue
                safe_unlink(config.APP_STORAGE_ROOT,target.relative_to(config.APP_STORAGE_ROOT),missing_ok=True)
                db.execute("DELETE FROM reference_cache WHERE source_hash=%s AND model_signature=%s",
                           (row["source_hash"],row["model_signature"]))
                report["embeddings"]+=1
            except (OSError,ValueError,TypeError):continue
        candidates=db.execute("""SELECT source_hash,declared_size FROM reference_physical_objects o
            WHERE unowned_since<=now()-(%s*interval '1 second')
              AND NOT EXISTS(SELECT 1 FROM reference_live_hashes h WHERE h.source_hash=o.source_hash)
            ORDER BY unowned_since,source_hash LIMIT %s""",(grace_seconds,limit)).fetchall()
        for row in candidates:
            digest=row["source_hash"]
            try:
                target=objects.object_path(digest)
                try:objects.verify_object(target,row["declared_size"],digest=digest)
                except FileNotFoundError:pass
                safe_unlink(config.APP_STORAGE_ROOT,target.relative_to(config.APP_STORAGE_ROOT),missing_ok=True)
                db.execute("DELETE FROM reference_physical_objects WHERE source_hash=%s",(digest,))
                report["objects"]+=1
            except (OSError,ValueError):continue
    return report

def history_usage():
    """Bounded-by-registry, read-only physical sizes for retained historical data."""
    summary={"objects":0,"object_bytes":0,"embeddings":0,"embedding_bytes":0,"missing":0}
    with connect() as db:
        historical=db.execute("""SELECT DISTINCT m.source_hash FROM reference_version_members m
            WHERE NOT EXISTS(SELECT 1 FROM reference_library_state s JOIN reference_version_members c
                ON c.version_id=s.current_version_id WHERE c.source_hash=m.source_hash)
            AND NOT EXISTS(SELECT 1 FROM uploads u WHERE u.kind='reference' AND u.finalized AND u.checksum=m.source_hash)
            AND NOT EXISTS(SELECT 1 FROM reference_import_files f JOIN reference_import_sessions s ON s.id=f.session_id
                WHERE f.checksum=m.source_hash AND s.upload_state<>'cancelled'
                  AND s.preparation_state NOT IN ('completed','stopped'))""").fetchall()
        digests=[r["source_hash"] for r in historical]
        vectors=db.execute("SELECT source_hash,model_signature,cache_path FROM reference_cache WHERE source_hash=ANY(%s)",(digests,)).fetchall()
    seen=set()
    def measure(path,count_key,byte_key):
        try:
            info=file_stat(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT))
            inode=(info["device"],info["inode"])
            if inode in seen:return
            seen.add(inode)
            summary[count_key]+=1
            summary[byte_key]+=info["allocated"]
        except (ValueError,OSError):summary["missing"]+=1
    for digest in digests:
        measure(objects.object_path(digest),"objects","object_bytes")
    for row in vectors:
        try:
            path=location(row["source_hash"],row["model_signature"])
            if path!=Path(row["cache_path"]):raise ValueError("Bad cache path")
            measure(path,"embeddings","embedding_bytes")
        except (ValueError,TypeError):summary["missing"]+=1
    return summary
