"""Compact FO cards must display real model counts without leaking paths."""
from __future__ import annotations
from psycopg.types.json import Jsonb
from server.database import connect
from server.services import batches,cleanup
from .test_stage1_lifecycle import sandbox,db,_batch,_job

def test_latest_batch_projection_includes_safe_megaloc_counts(sandbox):
    own=_batch(sandbox)
    run=_job(sandbox,own,status="completed")
    try:
        with connect() as db:
            db.execute("UPDATE jobs SET snapshot=%s WHERE id=%s",(
                Jsonb({"id":run,"archive_state":"ready","models":{"megaloc":{
                    "status":"completed","processed":188,"assigned":185,
                    "uncertain":3,"groups":27,"private_path":"/secret"}}}),run))
        data=batches.get(own)["latest_run"]
        assert data["archive_state"]=="ready"
        assert data["models"]["megaloc"]=={"status":"completed",
            "processed":188,"assigned":185,"uncertain":3,"groups":27}
        assert "private_path" not in str(data)
    finally:
        cleanup.request(own)
        cleanup.cleanup_one(own)
