"""Batch card run projections: exact queue state, history and older results."""
from __future__ import annotations

import uuid
from psycopg.types.json import Jsonb
from fastapi import HTTPException
import pytest

from server.database import connect
from server.services import batches,cleanup
from server.api.routes.batches import runs_for_batch
from .test_stage1_lifecycle import sandbox,db,_batch,_job


def test_latest_run_and_saved_prior_results_visible_from_batch(sandbox):
    batch=_batch(sandbox)
    other=_batch(sandbox,with_photo=False)
    try:
        original=_job(sandbox,batch,"completed")
        failed=_job(sandbox,batch,"failed")
        with connect() as conn:
            conn.execute("""UPDATE jobs SET created_at=now()-interval '2 hours',
                snapshot=%s WHERE id=%s""",
                (Jsonb({"id":original,"status":"completed","grouping_threshold":.61,
                        "progress":{"stage_label":"Готово","current":4,"total":4},
                        "new_photos":"/private/photos"}),original))
            conn.execute("""UPDATE jobs SET created_at=now()-interval '1 hour',
                snapshot=%s WHERE id=%s""",
                (Jsonb({"id":failed,"status":"queued","grouping_threshold":.79,
                        "error":"synthetic test failure",
                        "references":"/private/references"}),failed))
        summary=batches.get(batch)
        assert summary["latest_run"]["id"]==failed
        assert summary["latest_run"]["status"]=="failed"
        assert summary["latest_run"]["grouping_threshold"]==.79
        assert summary["last_result_run_id"]==original
        assert "references" not in summary["latest_run"]
        listing={row["batch_id"]:row for row in batches.list_all(200)["batches"]}
        assert listing[str(batch)]["latest_run"]["id"]==failed
        assert listing[str(batch)]["last_result_run_id"]==original
        assert listing[str(other)]["latest_run"] is None
        assert listing[str(other)]["last_result_run_id"] is None
        history=runs_for_batch(str(batch))
        assert history["total"]==2
        assert [item["id"] for item in history["runs"]]==[failed,original]
        assert "new_photos" not in history["runs"][1]
        assert runs_for_batch(str(batch),limit=1,offset=1)["runs"][0]["id"]==original
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)
        cleanup.request(other);cleanup.cleanup_one(other)


def test_running_progress_and_true_queue_position(sandbox):
    batch=_batch(sandbox)
    later=_batch(sandbox)
    try:
        a=_job(sandbox,batch,"queued")
        b=_job(sandbox,later,"queued")
        with connect() as conn:
            conn.execute("""UPDATE jobs SET created_at=now()-interval '5 minutes',
                snapshot=%s WHERE id=%s""",
                (Jsonb({"id":a,"status":"queued","progress":{},
                        "grouping_threshold":.5}),a))
            conn.execute("""UPDATE jobs SET created_at=now()-interval '4 minutes',
                snapshot=%s WHERE id=%s""",
                (Jsonb({"id":b,"status":"queued","progress":{}}),b))
        queued_a=batches.get(batch)["latest_run"]
        queued_b=batches.get(later)["latest_run"]
        assert queued_a["queue_position"] is not None
        assert queued_b["queue_position"]==queued_a["queue_position"]+1
        with connect() as conn:
            conn.execute("""UPDATE jobs SET status='running',snapshot=%s WHERE id=%s""",
                (Jsonb({"id":a,"status":"queued","progress":{
                    "stage_label":"Сопоставление SAM","stage_percent":42.1,
                    "current":12,"total":30,"overall_percent":18.3}}),a))
        running=batches.get(batch)["latest_run"]
        assert running["status"]=="running"
        assert running["queue_position"] is None
        assert running["progress"]["stage_percent"]==42.1
        assert running["progress"]["current"]==12
        assert running["progress"]["total"]==30
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)
        cleanup.request(later);cleanup.cleanup_one(later)


def test_history_rejects_invalid_input_and_missing_batch(sandbox):
    batch=_batch(sandbox,with_photo=False)
    try:
        assert runs_for_batch(str(batch))=={"runs":[],"total":0}
        with pytest.raises(HTTPException) as invalid:
            runs_for_batch(str(batch),limit=101)
        assert invalid.value.status_code==422
        with pytest.raises(HTTPException) as missing:
            runs_for_batch(str(uuid.uuid4()))
        assert missing.value.status_code==404
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)
