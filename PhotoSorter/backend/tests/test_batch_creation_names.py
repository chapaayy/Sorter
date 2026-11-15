"""New folder imports are isolated by ID, including concurrent requests and retries."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from server.api.routes.batches import NewBatch, create
from server.database import connect
from server.services import batches, cleanup, upload_manifest
from .test_stage1_lifecycle import db, sandbox
from .test_stage2_platform import thumbs, _jpg
from .test_upload_manifest import File, _send


def test_same_name_folders_get_separate_manifests_and_photos(thumbs):
    base = "Выезд " + uuid4().hex
    created = [create(NewBatch(display_name=base, creation_request_id=uuid4()))
               for _ in range(3)]
    try:
        assert [row["display_name"] for row in created] == [base, base + " 2", base + " 3"]
        assert len({row["batch_id"] for row in created}) == 3
        raw = _jpg()
        files = [File(uuid4(), "Камера/IMG_0001.jpg", len(raw)) for _ in created]
        for row, file in zip(created, files):
            upload_manifest.register(row["batch_id"], [file])
            _send(thumbs, row["batch_id"], file, raw)
        with connect() as db:
            stored = db.execute("""SELECT id,batch_id,target_path FROM uploads
                WHERE id=ANY(%s)""", ([file.upload_id for file in files],)).fetchall()
        assert {str(row["batch_id"]): row["id"] for row in stored} == {
            batch["batch_id"]: file.upload_id for batch, file in zip(created, files)
        }
        assert len({row["target_path"] for row in stored}) == 3
    finally:
        for row in created:
            cleanup.request(row["batch_id"])
            cleanup.cleanup_one(row["batch_id"])


def test_concurrent_creates_allocate_suffixes_and_retry_is_idempotent(sandbox):
    base = "Same%" + uuid4().hex
    retry = NewBatch(display_name=base, creation_request_id=uuid4())
    fresh = [NewBatch(display_name=base, creation_request_id=uuid4()) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(create, [retry] * 4 + fresh))
    ids = {row["batch_id"] for row in rows}
    try:
        assert rows[:4] == [rows[0]] * 4
        assert len(ids) == 5
        assert {row["display_name"] for row in rows} == {base, *(base + f" {i}" for i in range(2, 6))}
    finally:
        for identifier in ids:
            cleanup.request(identifier)
            cleanup.cleanup_one(identifier)


def test_names_stay_at_most_120_chars_and_rename_respects_existing_names(sandbox):
    base = uuid4().hex + "а" * 88
    first, second = [batches.create(base) for _ in range(2)]
    try:
        assert first["display_name"] == base
        assert second["display_name"] == base[:118] + " 2"
        assert batches.rename(second["batch_id"], base)["display_name"] == second["display_name"]
        cleanup.request(first["batch_id"])
        cleanup.cleanup_one(first["batch_id"])
        assert batches.rename(second["batch_id"], base)["display_name"] == base
    finally:
        cleanup.request(second["batch_id"])
        cleanup.cleanup_one(second["batch_id"])
