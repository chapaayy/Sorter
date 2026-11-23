"""Read-only file inventory with physical hardlink accounting and explicit scan gaps."""
import os

import pytest
from fastapi import HTTPException

from server.services import storage_inventory as inventory


def test_inventory_lists_real_paths_and_owners_without_writing(tmp_path):
    data = tmp_path / "data"
    models = tmp_path / "Models"
    batch_id = "11111111-1111-4111-8111-111111111111"
    run_id = "20261123T123000-abcdef123456"
    original = data / "uploads" / batch_id / "one.jpg"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"a" * 8192)
    published = data / "outputs" / run_id / "megaloc" / "SAM 0004" / "one.jpg"
    published.parent.mkdir(parents=True)
    os.link(original, published)
    part = data / "incoming" / "pending.part"
    part.parent.mkdir()
    part.write_bytes(b"x")
    cache = data / "cache" / "megaloc" / "references" / "one.npy"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"c" * 20)
    model = models / "models" / "megaloc" / "model.safetensors"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"m" * 10)

    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    summary, records = inventory._collect(
        data, models, {batch_id: "Фотоотчёт 321"}, {run_id: batch_id}
    )
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert before == after, "Inventory must not create, rewrite or remove files"
    assert summary["partial"] is False
    assert summary["files_scanned"] == 5
    by_path = {r["path"]: r for r in records}
    assert by_path["PhotoSorter/data/incoming/pending.part"]["purpose"] == "temporary"
    assert by_path["PhotoSorter/data/cache/megaloc/references/one.npy"]["purpose"] == "cache"
    assert by_path["Models/models/megaloc/model.safetensors"]["purpose"] == "system"
    assert by_path["PhotoSorter/data/uploads/" + batch_id + "/one.jpg"]["owner_name"] == "Фотоотчёт 321"
    # Only one of the two physical hardlinks receives disk-block allocation.
    shared = [r for r in records if r["path"].endswith("/one.jpg")]
    assert len(shared) == 2
    assert sum(int(r["hardlink"]) for r in shared) == 1
    assert sum(r["allocated_bytes"] for r in shared) == original.stat().st_blocks * 512
    assert summary["allocated_bytes"] == sum(r["allocated_bytes"] for r in records)


def test_inventory_does_not_follow_symlinks_and_reports_partial(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    models = tmp_path / "models"
    models.mkdir()
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "secret.txt").write_text("SECRET")
    (root / "external").symlink_to(outside, target_is_directory=True)
    summary, records = inventory._collect(root, models, {}, {})
    assert records == []
    assert summary["partial"] is True
    assert summary["skipped_paths"] == 1
    (root / "external").unlink()
    for n in range(5):
        (root / f"{n}.jpg").write_text("image")
    summary, records = inventory._collect(root, models, {}, {}, max_files=2)
    assert len(records) == 2
    assert summary["partial"] is True


def test_inventory_pagination_rejects_expired_snapshot(monkeypatch):
    summary = {"snapshot_id": "test", "files_scanned": 3}
    rows = [
        {"path": "PhotoSorter/data/a", "category": "originals", "owner_name": "A"},
        {"path": "PhotoSorter/data/b", "category": "logs", "owner_name": None},
        {"path": "PhotoSorter/data/c", "category": "originals", "owner_name": "A"},
    ]
    monkeypatch.setattr(inventory, "_snapshot", (summary, rows))
    page = inventory.files(snapshot_id="test", offset=1, limit=1)
    assert page["total"] == 3
    assert page["files"][0]["path"].endswith("/b")
    filtered = inventory.files(snapshot_id="test", category="originals", search="data/c")
    assert filtered["total"] == 1
    with pytest.raises(HTTPException) as exc:
        inventory.files(snapshot_id="old")
    assert exc.value.status_code == 409
