"""Retention OFF must pause due scans; re-enabling must not mass-delete."""
from __future__ import annotations
from server.database import connect
from server.services import cleanup,retention
from .test_stage1_lifecycle import sandbox,db,_batch

def test_retention_disabled_blocks_existing_deadline_and_safe_reenable(sandbox):
    own=_batch(sandbox)
    original=retention.settings()
    try:
        retention.update_settings(True,1,"minutes")
        with connect() as db:
            db.execute("""UPDATE batches SET delete_after_at=now()-interval '1 minute'
                WHERE id=%s""",(own,))
        assert own in retention.due_batch_ids()
        retention.update_settings(False,5,"minutes")
        assert own not in retention.due_batch_ids()
        assert cleanup.request(own,only_if_due=True)["state"]=="skipped"
        assert cleanup.get_status(own)["delete_state"]=="active"
        retention.update_settings(True,5,"minutes")
        with connect() as db:
            seconds=db.execute("""SELECT extract(epoch from
                (delete_after_at-now())) AS seconds FROM batches WHERE id=%s""",
                (own,)).fetchone()["seconds"]
        assert 290<float(seconds)<=300
        assert own not in retention.due_batch_ids()
    finally:
        retention.update_settings(original["enabled"],original["value"],original["unit"])
        cleanup.request(own)
        cleanup.cleanup_one(own)
