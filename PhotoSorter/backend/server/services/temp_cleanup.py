"""Conservative TTL for only unfinished upload parts; never remove originals."""
from __future__ import annotations
import time
from app import config
from app.storage.filesystem import safe_unlink
from ..storage.paths import part_path
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
            row=db.execute("""SELECT id,batch_id FROM uploads WHERE id=%s AND kind='fo' AND NOT finalized
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
            safe_unlink(config.APP_STORAGE_ROOT,target.relative_to(config.APP_STORAGE_ROOT),missing_ok=True)
            db.execute("DELETE FROM uploads WHERE id=%s",(row["id"],))
            if row["batch_id"]:refresh_upload_state(db,row["batch_id"])
            removed+=1
    return removed
