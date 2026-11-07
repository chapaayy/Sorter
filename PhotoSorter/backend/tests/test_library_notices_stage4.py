"""Stage 4: notice cursor, real manifest completion, aggregation and FIFO API."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from server import database
from server.services import library_notices,upload_manifest
from server.api.routes import library_notices as api_notices,work_queue as api_queue
from .test_unified_queue_stage3 import system,add_fo
from .test_stage2_platform import _jpg

def batch():
    ident=uuid.uuid4()
    with database.connect() as db:
        db.execute("INSERT INTO batches(id,display_name) VALUES (%s,'FO notice')",(ident,))
    return ident

def publish(kind='reference_prepared'):
    with database.connect() as db:
        number=db.execute("""SELECT COALESCE(MAX(version_number),0)+1 AS n
            FROM reference_library_versions""").fetchone()["n"]
        version=db.execute("""INSERT INTO reference_library_versions(
            version_number,manifest_digest) VALUES (%s,%s) RETURNING id""",
            (number,f"{number:064x}")).fetchone()["id"]
        db.execute("""UPDATE reference_library_state
            SET current_version_id=%s,baseline_state='ready' WHERE id=1""",(version,))
        db.execute("""INSERT INTO reference_library_events(version_id,event_kind)
            VALUES (%s,%s)""",(version,kind))
    return version

def complete_batch():
    own=batch()
    with database.connect() as db:
        library_notices.record_completed_fo(db,own)
    return own

def test_notice_is_created_only_after_first_complete_fo_and_new_version(system):
    assert not library_notices.status()["notice"]
    v2=publish()
    assert not library_notices.status()["notice"],"no earlier FO, no warning"
    complete_batch()
    baseline=library_notices.status()
    assert baseline["acknowledged_version_id"]==v2
    assert not baseline["notice"]
    v3=publish()
    visible=library_notices.status()
    assert visible["notice"]
    assert visible["pending_changes"]==1
    assert visible["notice_version_id"]==v3
    assert "могут отличаться" in visible["message"]
    # A new completed FO never erases an unacknowledged notice.
    complete_batch()
    assert library_notices.status()["notice"]
    assert library_notices.acknowledge(v3)["notice"] is False
    assert library_notices.status()["notice"] is False, "ack lives in PG, not browser"
    v4=publish()
    assert library_notices.status()["notice"]
    assert library_notices.status()["notice_version_id"]==v4

def test_multiple_publications_are_one_banner_and_older_ack_does_not_hide_new(system):
    complete_batch()
    v2=publish()
    v3=publish()
    v4=publish()
    state=library_notices.status()
    assert state["pending_changes"]==3
    assert state["notice_version_id"]==v4
    assert library_notices.acknowledge(v2)["pending_changes"]==2
    assert library_notices.acknowledge(v3)["pending_changes"]==1
    assert library_notices.acknowledge(v4)["pending_changes"]==0
    assert not library_notices.acknowledge(v3)["notice"],"stale ack cannot roll cursor back"

def test_technical_snapshot_and_address_changes_do_not_show_false_notice(system):
    complete_batch()
    publish("baseline_immutable")
    current=library_notices.status()
    assert not current["notice"]
    publish("address_changed")
    assert not library_notices.status()["notice"]
    publish("reference_prepared")
    assert library_notices.status()["notice"]

def test_receipt_idempotency_and_first_upload_sql_manifest_hook(system):
    from hashlib import sha256
    own=batch()
    raw=_jpg()
    entry=SimpleNamespace(upload_id=uuid.uuid4(),relative_path="folder/photo.jpg",
                          filename="photo.jpg",size=len(raw))
    upload_manifest.register(own,[entry])
    with database.connect() as db:
        db.execute("""SELECT id FROM batches WHERE id=%s FOR UPDATE""",(own,))
        assert upload_manifest.reconcile_locked(db,own) is False
        assert db.execute("SELECT count(*) AS n FROM fo_library_upload_receipts").fetchone()["n"]==0
    from pathlib import Path
    root=system/"uploads"/str(own)
    root.mkdir(parents=True)
    picture=root/"photo.jpg"
    picture.write_bytes(raw)
    with database.connect() as db:
        db.execute("""INSERT INTO uploads(id,kind,batch_id,filename,declared_size,
            received,checksum,finalized,target_path)
            VALUES (%s,'fo',%s,'photo.jpg',%s,%s,%s,true,%s)""",
            (entry.upload_id,own,len(raw),len(raw),sha256(raw).hexdigest(),str(picture)))
        db.execute("SELECT id FROM batches WHERE id=%s FOR UPDATE",(own,))
        assert upload_manifest.reconcile_locked(db,own) is True
        assert upload_manifest.reconcile_locked(db,own) is True
        assert db.execute("SELECT count(*) AS n FROM fo_library_upload_receipts").fetchone()["n"]==1
    state=library_notices.status()
    assert state["last_fo_uploaded_at"] is not None
    assert not state["notice"]
    v2=publish()
    assert library_notices.status()["notice"]
    # Rechecking an older finished manifest must not advance the cursor.
    with database.connect() as db:
        db.execute("SELECT id FROM batches WHERE id=%s FOR UPDATE",(own,))
        assert upload_manifest.reconcile_locked(db,own) is True
    assert library_notices.status()["notice"]
    assert library_notices.status()["notice_version_id"]==v2

def test_invalid_ack_and_history_filter(system):
    with pytest.raises(HTTPException):
        api_notices.acknowledge(api_notices.Acknowledgement(version_id=999))
    complete_batch()
    v2=publish("reference_prepared")
    v3=publish("baseline_immutable")
    changed=api_notices.events(limit=20,after_version=v2-1)["events"]
    assert {e["version_id"] for e in changed}=={v2,v3}
    with pytest.raises(HTTPException):
        library_notices.acknowledge(v3+100)
    assert library_notices.status()["notice"]

def test_active_and_history_queue_views_are_disjoint(system):
    # New FO jobs populate the ledger and still support old /api/runs.
    from server.db.repositories import work_queue
    from server import jobs
    from .test_unified_queue_stage3 import add_published_reference
    add_published_reference(system)
    one=add_fo()
    two=add_fo()
    active=api_queue.list_work_queue(scope="active")
    assert len(active["tasks"])==2
    assert active["tasks"][0]["seq"]<active["tasks"][1]["seq"]
    assert active["tasks"][0]["batch_name"] is not None
    with database.connect() as db:
        db.execute("UPDATE jobs SET status='completed' WHERE id=%s",(one,))
        work_queue.finish_fo(db,one,"completed")
    active=api_queue.list_work_queue(scope="active")
    history=api_queue.list_work_queue(scope="history")
    assert [task["fo_run_id"] for task in active["tasks"]]==[two]
    assert [task["fo_run_id"] for task in history["tasks"]]==[one]
    with pytest.raises(HTTPException):
        api_queue.list_work_queue(scope="invalid")

