"""Stage 4: filtered queue/history without changing legacy /runs semantics.

All tests use the disposable PostgreSQL and synthetic batch fixtures.
"""
from __future__ import annotations
import uuid

import pytest
from fastapi import HTTPException
from psycopg.types.json import Jsonb

from server.database import connect
from server import jobs
from server.services import cleanup
from .test_stage1_lifecycle import sandbox,db,_batch,_job


def test_dashboard_scope_isolated_from_history_and_old_clients(sandbox):
    batch_a=_batch(sandbox)
    batch_b=_batch(sandbox)
    batch_c=_batch(sandbox)
    try:
        run_a=_job(sandbox,batch_a,status="queued")
        run_b=_job(sandbox,batch_b,status="running")
        run_c=_job(sandbox,batch_c,status="failed")
        with connect() as db:
            # The snapshot's status may be stale; only the DB status is authoritative.
            db.execute("UPDATE jobs SET snapshot=%s WHERE id=%s",
                (Jsonb({"id":run_b,"status":"queued","progress":{
                    "stage_label":"Сопоставление","current":3,"total":10,
                    "stage_percent":30.0}}),run_b))
        with connect() as db:
            from server.db.repositories import work_queue
            work_queue.insert_fo(db,run_a)
        active=jobs.list_jobs(scope="active",limit=200)
        history=jobs.list_jobs(scope="history",limit=200)
        all_runs=jobs.list_jobs(limit=200)
        assert {run_a,run_b}.issubset({r["id"] for r in active["runs"]})
        assert run_c not in {r["id"] for r in active["runs"]}
        assert run_c in {r["id"] for r in history["runs"]}
        assert run_a not in {r["id"] for r in history["runs"]}
        assert {run_a,run_b,run_c}.issubset({r["id"] for r in all_runs["runs"]})
        live=next(r for r in active["runs"] if r["id"]==run_b)
        assert live["status"]=="running"
        assert live["progress"]["current"]==3
        assert next(r for r in active["runs"] if r["id"]==run_a)["queue_position"]>=1
        assert active["total"]>=2
        assert history["total"]>=1
    finally:
        # Synthetic 'running' rows must be marked terminal before deleting.
        with connect() as db:
            db.execute("""UPDATE jobs SET status='stopped',stop_requested=true
                WHERE batch_id=ANY(%s) AND status IN ('queued','running','stopping')""",
                ([batch_a,batch_b,batch_c],))
        for batch in (batch_a,batch_b,batch_c):
            cleanup.request(batch)
            cleanup.cleanup_one(batch)


def test_dashboard_history_pagination_and_validation(sandbox):
    batch=_batch(sandbox)
    try:
        ids=[_job(sandbox,batch,status="completed") for _ in range(3)]
        rows=jobs.list_jobs(scope="history",limit=2,offset=0)["runs"]
        assert len(rows)==2
        subsequent=jobs.list_jobs(scope="history",limit=2,offset=2)["runs"]
        assert ids[0] in {r["id"] for r in rows+subsequent}
        assert len({r["id"] for r in rows+subsequent})==len(rows+subsequent)
        for invalid in ("anything","queued","", "ACTIVE"):
            with pytest.raises(HTTPException) as exc:
                jobs.list_jobs(scope=invalid)
            assert exc.value.status_code==422
        with pytest.raises(HTTPException):
            jobs.list_jobs(scope="active",limit=0)
        with pytest.raises(HTTPException):
            jobs.list_jobs(scope="history",offset=-1)
    finally:
        cleanup.request(batch)
        cleanup.cleanup_one(batch)
