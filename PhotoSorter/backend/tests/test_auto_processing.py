"""FO automatic queueing with immediate FIFO registration and restart reconciliation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest
from fastapi import HTTPException
from server.database import connect
from server.services import auto_processing,upload_manifest,cleanup,batches
from server import jobs
from .test_stage1_lifecycle import _batch,sandbox,db
from .test_stage2_platform import thumbs,_jpg
from .test_upload_manifest import _files,_send


@pytest.fixture
def model_ready(monkeypatch):
    monkeypatch.setattr("app.system.model_store.files_present",lambda:True)


@pytest.fixture
def reference(thumbs):
    raw=_jpg()
    file=thumbs/"references"/"SAM-0001"/"reference.jpg"
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(raw)
    uid=uuid.uuid4()
    with connect() as db:
        db.execute("""INSERT INTO uploads(id,kind,sam,filename,declared_size,received,
            finalized,target_path) VALUES (%s,'reference','SAM-0001','reference.jpg',
            %s,%s,true,%s)""",(uid,len(raw),len(raw),str(file)))
    try:
        yield uid
    finally:
        with connect() as db:
            db.execute("DELETE FROM uploads WHERE id=%s",(uid,))


def test_default_setting_off_and_changes_do_not_retroactively_enable(thumbs):
    batch=_batch(thumbs,with_photo=False)
    raw=_jpg()
    try:
        current=auto_processing.settings()
        assert current["model"]=="megaloc"
        assert isinstance(current["auto_process_new_batches"],bool)
        old=auto_processing.settings()
        auto_processing.update_settings(enabled=True,threshold=.64)
        assert auto_processing.settings()["grouping_threshold"]==.64
        upload_manifest.register(batch,_files(1,raw))
        assert batches.get(batch)["auto_process_state"] is None
    finally:
        auto_processing.update_settings(enabled=old["auto_process_new_batches"],
                                        threshold=old["grouping_threshold"])
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_wait_for_complete_then_queue_once_with_persisted_threshold(thumbs,reference,model_ready):
    batch=_batch(thumbs,with_photo=False)
    raw=_jpg()
    files=_files(2,raw)
    try:
        upload_manifest.register(batch,files,auto_process=True,grouping_threshold=.73)
        assert auto_processing.schedule_ready()==[]
        _send(thumbs,batch,files[0],raw)
        assert auto_processing.schedule_ready()==[]
        _send(thumbs,batch,files[1],raw)
        # The browser could now be completely offline.
        # Last finalized FO file already enqueues in the same transaction.
        assert auto_processing.schedule_ready()==[]
        with connect() as db:
            job=db.execute("SELECT id,status,snapshot FROM jobs WHERE batch_id=%s",(batch,)).fetchone()
            assert job["status"]=="queued"
            assert job["snapshot"]["source"]=="automatic"
            assert job["snapshot"]["selected_models"]==["megaloc"]
            assert job["snapshot"]["grouping_threshold"]==.73
            # Worker errors are terminal, not an invitation to re-enqueue forever.
            db.execute("UPDATE jobs SET status='failed' WHERE id=%s",(job["id"],))
        assert batches.get(batch)["auto_process_run_id"]==job["id"]
        assert auto_processing.schedule_ready()==[]
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_cancel_before_enqueue_is_idempotent_and_does_not_stop_jobs(thumbs,reference,model_ready):
    batch=_batch(thumbs,with_photo=False)
    raw=_jpg()
    file=_files(1,raw)[0]
    try:
        upload_manifest.register(batch,[file],auto_process=True)
        assert auto_processing.cancel(batch)["auto_process_state"]=="cancelled"
        assert auto_processing.cancel(batch)["auto_process_state"]=="cancelled"
        _send(thumbs,batch,file,raw)
        assert auto_processing.schedule_ready()==[]
        with connect() as db:
            assert db.execute("SELECT 1 FROM jobs WHERE batch_id=%s",(batch,)).fetchone() is None
        # A distinct new batch can still enqueue.
        second=_batch(thumbs,with_photo=False)
        try:
            f=_files(1,raw)[0]
            upload_manifest.register(second,[f],auto_process=True)
            _send(thumbs,second,f,raw)
            assert auto_processing.schedule_ready()==[]
            with pytest.raises(HTTPException) as exc:auto_processing.cancel(second)
            assert exc.value.status_code==409
        finally:
            cleanup.request(second);cleanup.cleanup_one(second)
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_auto_enqueue_wins_without_manual_duplicate(thumbs,reference,model_ready):
    batch=_batch(thumbs,with_photo=False)
    raw=_jpg()
    file=_files(1,raw)[0]
    try:
        upload_manifest.register(batch,[file],auto_process=True,grouping_threshold=.63)
        _send(thumbs,batch,file,raw)
        with pytest.raises(HTTPException) as error:
            jobs.enqueue(jobs.NewRun(batch_id=batch,grouping_threshold=.81))
        assert error.value.status_code==409
        assert batches.get(batch)["auto_process_state"]=="queued"
        assert auto_processing.schedule_ready()==[]
        with connect() as db:
            assert db.execute("SELECT count(*) AS n FROM jobs WHERE batch_id=%s",
                              (batch,)).fetchone()["n"]==1
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_concurrent_dispatches_do_not_duplicate_runs(thumbs,reference,model_ready):
    batch=_batch(thumbs,with_photo=False)
    raw=_jpg()
    file=_files(1,raw)[0]
    try:
        upload_manifest.register(batch,[file],auto_process=True)
        _send(thumbs,batch,file,raw)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(auto_processing.schedule_ready) for _ in range(2)]
            outcomes=[future.result(timeout=25) for future in futures]
        assert sum(len(result) for result in outcomes)==0, "Already placed atomically on last file"
        with connect() as db:
            assert db.execute("SELECT count(*) AS n FROM jobs WHERE batch_id=%s",
                              (batch,)).fetchone()["n"]==1
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_legacy_batch_cannot_be_silently_enrolled(thumbs):
    batch=_batch(thumbs,with_photo=False)
    try:
        with pytest.raises(HTTPException) as error:
            auto_processing.cancel(batch)
        assert error.value.status_code==409
        assert batches.get(batch)["auto_process_state"] is None
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)
