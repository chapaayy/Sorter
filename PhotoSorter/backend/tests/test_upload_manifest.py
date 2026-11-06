"""Manifest completion regressions on disposable PostgreSQL and photo directories."""
from __future__ import annotations

import concurrent.futures
import uuid

import pytest
from fastapi import HTTPException

from server.database import connect
from server.services import batches, cleanup, upload_manifest
from .test_stage1_lifecycle import _batch, sandbox, db
from .test_stage2_platform import thumbs, _jpg


class File:
    def __init__(self, upload_id, relative_path, size):
        self.upload_id = upload_id
        self.relative_path = relative_path
        self.filename = relative_path.rsplit("/", 1)[-1]
        self.size = size


def _files(count, raw):
    return [File(uuid.uuid4(), f"SD/Camera/IMG_{i:04d}.jpg", len(raw))
            for i in range(count)]


def _send(root, batch, item, raw):
    from server import uploads
    uploads._create_upload(uploads.BeginUpload(
        kind="fo", batch_id=str(batch), filename=item.filename,
        size=len(raw), client_upload_id=item.upload_id), item.upload_id)
    (root / "incoming" / f"{item.upload_id}.part").write_bytes(raw)
    return uploads._finalize_sync(str(item.upload_id))


def test_manifest_proves_all_expected_not_only_pending_zero(thumbs):
    from server import jobs
    batch = _batch(thumbs, with_photo=False)
    raw = _jpg()
    files = _files(3, raw)
    try:
        first = upload_manifest.register(batch, files)
        assert (first["expected"], first["finalized"], first["missing"], first["pending"]) == (3, 0, 3, 3)
        assert batches.get(batch)["upload_state"] == "open"
        assert batches.get(batch)["pending"] == 0
        with pytest.raises(HTTPException) as error:
            jobs.enqueue(jobs.NewRun(batch_id=batch))
        assert error.value.status_code == 422
        _send(thumbs, batch, files[0], raw)
        assert upload_manifest.status(batch)["state"] == "waiting"
        assert batches.get(batch)["upload_state"] == "open"
        # No browser request to "finish the batch" is necessary.
        for file in files[1:]:
            _send(thumbs, batch, file, raw)
        confirmed = upload_manifest.status(batch)
        assert confirmed["state"] == "complete"
        assert confirmed["finalized"] == 3 and confirmed["pending"] == 0
        assert batches.get(batch)["upload_state"] == "ready"
        with connect() as db:
            assert db.execute("SELECT count(*) AS n FROM uploads WHERE batch_id=%s", (batch,)).fetchone()["n"] == 3
        # Lost ACK: repeat finish, do not create duplicate original or upload row.
        from server import uploads
        assert uploads._finalize_sync(str(files[-1].upload_id))["already_finalized"] is True
    finally:
        cleanup.request(batch); cleanup.cleanup_one(batch)


def test_manifest_is_immutable_idempotent_and_blocks_unregistered_upload(thumbs):
    from server import uploads
    batch = _batch(thumbs, with_photo=False)
    raw = _jpg()
    items = _files(2, raw)
    try:
        first = upload_manifest.register(batch, items)
        again = upload_manifest.register(batch, list(reversed(items)))
        assert first["expected"] == again["expected"] == 2
        with connect() as db:
            assert db.execute("SELECT count(*) AS n FROM batch_upload_manifest_files WHERE batch_id=%s",
                              (batch,)).fetchone()["n"] == 2
        with pytest.raises(HTTPException) as conflict:
            upload_manifest.register(batch, items[:1])
        assert conflict.value.status_code == 409
        with pytest.raises(HTTPException) as unlisted:
            uploads._create_upload(uploads.BeginUpload(
                kind="fo", batch_id=str(batch), filename="not-listed.jpg",
                size=len(raw)), uuid.uuid4())
        assert unlisted.value.status_code == 409
        with pytest.raises(HTTPException) as changed:
            uploads._create_upload(uploads.BeginUpload(
                kind="fo", batch_id=str(batch), filename=items[0].filename,
                size=len(raw)+1), items[0].upload_id)
        assert changed.value.status_code == 409
        with pytest.raises(HTTPException) as traversal:
            upload_manifest.register(batch, [File(uuid.uuid4(), "SD/../evil.jpg", len(raw))])
        assert traversal.value.status_code == 422
    finally:
        cleanup.request(batch); cleanup.cleanup_one(batch)


def test_restart_reconciliation_after_all_saved_and_missing_source(thumbs):
    from server import uploads
    batch = _batch(thumbs, with_photo=False)
    raw = _jpg()
    files = _files(2, raw)
    try:
        upload_manifest.register(batch, files)
        _send(thumbs, batch, files[0], raw)
        # Remaining file never even creates a session. The server still reports it.
        state = upload_manifest.status(batch)
        assert state["missing"] == 1
        assert state["files"][-1]["state"] == "not_started"
        # A complete but not finalized .part remains visible to recovery tools.
        item = files[1]
        uploads._create_upload(uploads.BeginUpload(
            kind="fo", batch_id=str(batch), filename=item.filename,
            size=len(raw)), item.upload_id)
        (thumbs / "incoming" / f"{item.upload_id}.part").write_bytes(raw)
        assert batches.pending_uploads(batch)["uploads"][0]["can_finalize"]
        _send_finish = uploads._finalize_sync(str(item.upload_id))
        assert _send_finish["already_finalized"] is False
        assert upload_manifest.status(batch)["state"] == "complete"
    finally:
        cleanup.request(batch); cleanup.cleanup_one(batch)


def test_legacy_batches_still_use_original_upload_semantics(thumbs):
    batch = _batch(thumbs, with_photo=False)
    raw = _jpg()
    try:
        assert upload_manifest.status(batch)["state"] == "legacy"
        _send(thumbs, batch, File(uuid.uuid4(), "legacy.jpg", len(raw)), raw)
        assert batches.get(batch)["upload_state"] == "ready"
        assert batches.get(batch)["upload_manifest_state"] is None
        with pytest.raises(HTTPException) as error:
            upload_manifest.register(batch, _files(1, raw))
        assert error.value.status_code == 409
    finally:
        cleanup.request(batch); cleanup.cleanup_one(batch)


def test_concurrent_finalization_only_completes_after_both(thumbs):
    batch = _batch(thumbs, with_photo=False)
    raw = _jpg()
    files = _files(2, raw)
    from server import uploads
    try:
        upload_manifest.register(batch, files)
        for item in files:
            uploads._create_upload(uploads.BeginUpload(
                kind="fo", batch_id=str(batch), filename=item.filename,
                size=len(raw)), item.upload_id)
            (thumbs / "incoming" / f"{item.upload_id}.part").write_bytes(raw)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda i: uploads._finalize_sync(str(i.upload_id)), files))
        assert all(result["already_finalized"] is False for result in results)
        assert upload_manifest.status(batch)["state"] == "complete"
        assert batches.get(batch)["pending"] == 0
    finally:
        cleanup.request(batch); cleanup.cleanup_one(batch)
