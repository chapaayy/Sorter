"""Missing completed ZIP can be recovered without running MegaLoc again."""
from __future__ import annotations
import json
import zipfile
from fastapi import HTTPException
import pytest
from psycopg.types.json import Jsonb

from server.database import connect
from server.services import archives,archive_retries,archive_pipeline,cleanup
from server.storage import paths
from .test_stage1_lifecycle import sandbox,db,_batch,_job


def test_completed_zip_missing_can_be_queued_for_zip_only_repair(sandbox,monkeypatch):
    monkeypatch.setattr(archive_pipeline,"DATA_DIR",sandbox)
    batch=_batch(sandbox)
    run=_job(sandbox,batch)
    folder=paths.run_dir(run)/"megaloc"
    source=folder/"SAM 0001"/"one.jpg"
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_bytes(b"photo bytes")
    manifest=folder/"manifest.json"
    manifest.write_text(json.dumps([{"copy":str(source),"assigned_sam":"SAM 0001"}]))
    index=sandbox/"runs"/run/"models"
    index.mkdir(parents=True)
    (index/"megaloc.json").write_text(json.dumps({"path":str(manifest)}))
    try:
        with connect() as db:
            db.execute("UPDATE jobs SET snapshot=%s WHERE id=%s",(
                Jsonb({"id":run,"status":"completed","archive_state":"ready",
                       "models":{"megaloc":{"status":"completed"}}}),run))
        selected=[(source,"SAM 0001/one.jpg")]
        full=archives.prepare(run,None,selected)
        assert archive_retries.archive_status(run)["state"]=="ready"
        with pytest.raises(HTTPException) as ready:
            archive_retries.request(run)
        assert ready.value.status_code==409

        full.unlink()
        assert archive_retries.archive_status(run)["state"]=="missing"
        assert archive_retries.archive_status(run)["can_retry"] is True
        assert archive_retries.request(run)["state"]=="pending"
        assert archive_retries.request(run)["state"]=="pending"
        with connect() as db:
            row=db.execute("SELECT status,snapshot FROM jobs WHERE id=%s",(run,)).fetchone()
            retry=db.execute("SELECT state FROM archive_retries WHERE run_id=%s",(run,)).fetchone()
        assert row["status"]=="failed"
        assert row["snapshot"]["archive_state"]=="failed"
        assert row["snapshot"]["models"]["megaloc"]["status"]=="completed"
        assert retry["state"]=="pending"
    finally:
        cleanup.request(batch)
        cleanup.cleanup_one(batch)


def test_zip_failed_integrity_check_is_never_published(tmp_path,monkeypatch):
    monkeypatch.setattr(archives.storage_paths,"OUTPUTS",tmp_path)
    run="20261107T120000-abcdef123456"
    source=tmp_path/run/"megaloc"/"SAM 0001"/"one.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"photo")
    monkeypatch.setattr(zipfile.ZipFile,"testzip",lambda _self:"SAM 0001/one.jpg")
    with pytest.raises(OSError,match="проверки ZIP"):
        archives.prepare(run,None,[(source,"SAM 0001/one.jpg")])
    archive_dir=source.parents[2]/".archives"
    assert not list(archive_dir.glob("*.zip"))
    assert not list(archive_dir.glob("*.tmp"))
