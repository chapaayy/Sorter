"""The FO list is a list of *visible* batches, not DB deletion tombstones.

Regression for an empty selector on a newly uploaded batch and "Партий: 1"
after deletion. The disposable PostgreSQL fixture is not a real VPS.
"""
from __future__ import annotations

from .test_stage1_lifecycle import sandbox,db,_batch,_job
from server.services import batches,cleanup


def test_visible_batches_have_zero_run_counts_and_deleted_tombstones_do_not_count(sandbox):
    before=batches.list_all(200)
    fresh=_batch(sandbox)
    other=_batch(sandbox,with_photo=False)
    try:
        listing=batches.list_all(200)
        assert listing["total"]==before["total"]+2
        by_id={b["batch_id"]:b for b in listing["batches"]}
        new=by_id[str(fresh)]
        assert new["photos"]==1
        assert new["pending"]==0
        assert new["runs"]==0
        assert new["delete_state"]=="active"
        assert batches.get(fresh)["runs"]==0

        empty=by_id[str(other)]
        assert empty["photos"]==0
        assert empty["runs"]==0
        _job(sandbox,fresh,status="completed")
        after_run={b["batch_id"]:b for b in batches.list_all(200)["batches"]}
        assert after_run[str(fresh)]["runs"]==1

        cleanup.request(fresh)
        deleting={b["batch_id"]:b for b in batches.list_all(200)["batches"]}
        assert deleting[str(fresh)]["delete_state"]=="deleting"
        assert cleanup.cleanup_one(fresh)=="completed"

        final=batches.list_all(200)
        assert final["total"]==before["total"]+1
        assert str(fresh) not in {b["batch_id"] for b in final["batches"]}
        assert str(other) in {b["batch_id"] for b in final["batches"]}
        assert all(b["delete_state"]!="deleted" for b in final["batches"])
    finally:
        cleanup.request(fresh)
        cleanup.cleanup_one(fresh)
        cleanup.request(other)
        cleanup.cleanup_one(other)
