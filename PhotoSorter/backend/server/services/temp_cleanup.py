"""Conservative TTL for only unfinished upload parts; never remove originals."""
from __future__ import annotations
import time
from app import config
from app.storage.filesystem import safe_unlink
from ..storage.paths import part_path,batch_dir,owned_file
from ..storage.batch_cleanup import discard_uncommitted_upload
from app.storage.paths import managed_prefix,uuid_key
from app.storage.categories import Category
import hashlib,os
from app.storage.filesystem import safe_read
from ..database import connect
from ..db.repositories.batches import refresh_upload_state

AGE_DAYS=30

def reclaim_abandoned(limit=50):
    removed=0
    with connect() as db:
        rows=db.execute("""SELECT id FROM uploads WHERE kind='fo' AND NOT finalized
          AND updated_at<now()-interval '30 days'
          ORDER BY updated_at,id LIMIT %s""",(limit,)).fetchall()
    for item in rows:
        with connect() as db:
            row=db.execute("""SELECT id,batch_id,filename FROM uploads WHERE id=%s AND kind='fo' AND NOT finalized
              AND updated_at<now()-interval '30 days' FOR UPDATE""",
              (item["id"],)).fetchone()
            if not row:continue
            if row["batch_id"]:
                if db.execute("SELECT 1 FROM batch_operations WHERE batch_id=%s LIMIT 1",
                              (row["batch_id"],)).fetchone():continue
                if db.execute("""SELECT 1 FROM jobs WHERE batch_id=%s
                      AND status IN ('queued','running','stopping') LIMIT 1""",
                      (row["batch_id"],)).fetchone():continue
            target=part_path(row["batch_id"],row["id"])
            if target.is_symlink():continue
            if target.exists() and target.resolve()!=target:continue
            if target.exists() and time.time()-target.stat().st_mtime<AGE_DAYS*86400:continue
            discard_uncommitted_upload(row["batch_id"],row["id"],row["filename"])
            db.execute("DELETE FROM uploads WHERE id=%s",(row["id"],))
            if row["batch_id"]:refresh_upload_state(db,row["batch_id"])
            removed+=1
    return removed


def reclaim_finalized_parts(limit=50):
    """Reconcile a crash after DB commit but before removing a known .part.

    Only inspect the typed FO part namespace; no deletion of unknown files.
    """
    root=managed_prefix(Category.FO_UPLOAD_PART)
    if not root.is_dir() or root.is_symlink():return 0
    removed=0
    for folder in root.iterdir():
        if folder.is_symlink() or not folder.is_dir():continue
        try:batch_id=uuid_key(folder.name)
        except ValueError:continue
        for target in folder.iterdir():
            if not target.name.endswith(".part") or target.is_symlink():continue
            try:upload_id=uuid_key(target.stem)
            except ValueError:continue
            if target!=part_path(batch_id,upload_id):continue
            with connect() as db:
                row=db.execute("""SELECT target_path,checksum FROM uploads
                    WHERE id=%s AND batch_id=%s AND kind='fo' AND finalized
                    FOR UPDATE""",(upload_id,batch_id)).fetchone()
                if not row or not row["target_path"]:continue
                if db.execute("SELECT 1 FROM batch_operations WHERE batch_id=%s LIMIT 1",(batch_id,)).fetchone():continue
                try:
                    original=owned_file(row["target_path"],batch_dir(batch_id))
                    with safe_read(config.APP_STORAGE_ROOT,original.relative_to(config.APP_STORAGE_ROOT)) as stream:
                        orig=os.fstat(stream.fileno())
                        with safe_read(config.APP_STORAGE_ROOT,target.relative_to(config.APP_STORAGE_ROOT)) as part:
                            stat=os.fstat(part.fileno())
                            if (orig.st_dev,orig.st_ino)!=(stat.st_dev,stat.st_ino):
                                if hashlib.file_digest(stream,"sha256").hexdigest()!=row["checksum"]:continue
                        safe_unlink(config.APP_STORAGE_ROOT,target.relative_to(config.APP_STORAGE_ROOT),missing_ok=True)
                    removed+=1
                except (OSError,ValueError):
                    continue
            if removed>=limit:return removed
    return removed
