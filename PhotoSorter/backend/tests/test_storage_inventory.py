"""Read-only registry inventory and CSV tests."""
import csv
import io
import os
import pytest
from fastapi import HTTPException
from server.services import storage_inventory as inventory
from server.storage.reporting import inventory as capture
from app import config
from .test_unified_queue_stage3 import system
from .test_stage1_lifecycle import _batch,_job
from .accounting_checks import settle

def test_inventory_lists_real_paths_and_owners_without_writing(system):
    from server.storage.paths import batch_dir
    from app.storage.categories import Category
    from app.storage.paths import managed_path
    from server import database
    from pathlib import Path
    batch=_batch(system)
    run=_job(system,batch)
    original=next(batch_dir(batch).iterdir())
    with database.connect() as db:
        owner=db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch,)).fetchone()["owner_id"]
    published=managed_path(Category.RESULT_MEDIA,user_id=owner,batch_uuid=batch,run_id=run)/"SAM 0004"/"one.jpg"
    published.parent.mkdir(parents=True)
    os.link(original,published)
    root=config.APP_STORAGE_ROOT
    before=sorted(p.relative_to(root) for p in root.rglob("*"))
    settle()
    summary=inventory.scan()
    rows=inventory.files(snapshot_id=summary["snapshot_id"])["files"]
    after=sorted(p.relative_to(root) for p in root.rglob("*"))
    assert before==after
    assert summary["files_scanned"]==2
    assert sum(int(r["hardlink"]) for r in rows)==1
    assert sum(r["allocated_bytes"] for r in rows)==original.stat().st_blocks*512
    assert all(r["owner_name"] for r in rows)

def test_inventory_reports_unknown_symlink_and_bounded_snapshot(system,tmp_path):
    root=config.APP_STORAGE_ROOT
    outside=tmp_path/"private"
    outside.mkdir()
    (outside/"secret.txt").write_text("SECRET")
    (root/"external").symlink_to(outside,target_is_directory=True)
    for n in range(5):(root/f"{n}.jpg").write_text("image")
    settle()
    summary,rows=capture()
    assert summary["files_scanned"]==6
    assert any(r["issue"]=="unexpected_symlink" for r in rows)
    assert all("secret.txt" not in r["path"] for r in rows)
    summary,rows=capture(limit=2)
    assert len(rows)==2 and summary["partial"] is True

def test_inventory_pagination_rejects_expired_snapshot(monkeypatch):
    summary = {"snapshot_id": "test", "files_scanned": 3}
    rows = [
        {"path": "storage/app/state/a", "category": "originals", "owner_name": "A"},
        {"path": "storage/app/state/b", "category": "logs", "owner_name": None},
        {"path": "storage/app/state/c", "category": "originals", "owner_name": "A"},
    ]
    monkeypatch.setattr(inventory, "_snapshot", (summary, rows))
    page = inventory.files(snapshot_id="test", offset=1, limit=1)
    assert page["total"] == 3
    assert page["files"][0]["path"].endswith("/b")
    filtered = inventory.files(snapshot_id="test", category="originals", search="state/c")
    assert filtered["total"] == 1
    with pytest.raises(HTTPException) as exc:
        inventory.files(snapshot_id="old")
    assert exc.value.status_code == 409


def test_complete_csv_export_has_every_row_and_blocks_excel_formulas(monkeypatch):
    """No 100-file pagination: export exactly the last scanned snapshot."""
    snapshot = {"snapshot_id": "full", "captured_at": "2026-11-23T14:00:00+00:00"}
    entries = [
        {
            "path": f"storage/app/state/uploads/photo-{index}.jpg",
            "category": "originals",
            "purpose": "permanent",
            "owner_name": "=HYPERLINK(\"https://unsafe.example\")" if index == 3 else "ФО 321",
            "owner_kind": "batch",
            "owner_id": "batch-id",
            "logical_bytes": 1200,
            "allocated_bytes": 1200,
            "hardlink": index == 204,
            "links": 2 if index == 204 else 1,
            "modified_at": "2026-11-23T14:00:00+00:00",
        }
        for index in range(205)
    ]
    monkeypatch.setattr(inventory, "_snapshot", (snapshot, entries))
    filename, stream = inventory.csv_report("full")
    # A concurrent scan must not change an in-progress export.
    monkeypatch.setattr(inventory, "_snapshot", ({"snapshot_id": "new"}, []))
    raw = b"".join(stream)
    assert raw.startswith(b"\xef\xbb\xbf")
    assert filename == "map-file-inventory-20261123_140000.csv"
    table = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
    assert len(table) == 206
    assert table[0][0] == "Путь"
    assert table[1][0] == entries[0]["path"]
    assert table[205][0] == entries[204]["path"]
    assert table[4][4].startswith("'=HYPERLINK")
    assert table[205][9] == "Да"
    with pytest.raises(HTTPException) as exc:
        inventory.csv_report("stale")
    assert exc.value.status_code == 409
