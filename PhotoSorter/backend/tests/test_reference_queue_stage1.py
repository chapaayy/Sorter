"""Stage 1: actual PostgreSQL migrations, passive FIFO and validated legacy V1."""
from __future__ import annotations
import hashlib
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from server.database import DB_URL, SCHEMA
from server.db.migration_runner import migrate
from server.db.repositories import work_queue, reference_versions
from server.services.reference_versions import ensure_baseline

@pytest.fixture
def isolated_db():
    if not DB_URL:
        pytest.skip("PostgreSQL test DATABASE_URL not configured")
    schema = "refstage1_" + uuid.uuid4().hex[:12]
    with psycopg.connect(DB_URL,row_factory=dict_row) as db:
        db.execute('CREATE SCHEMA "'+schema+'"')
        db.commit()
        try:
            db.execute('SET search_path TO "'+schema+'"')
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    db.execute(statement)
            yield db
        finally:
            db.rollback()
            db.execute("RESET search_path")
            db.execute('DROP SCHEMA "'+schema+'" CASCADE')
            db.commit()

def add_reference(db,root,*,valid=True):
    upload_id = uuid.uuid4()
    target = root / "SAM 0004" / (str(upload_id) + ".jpg")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(b"reference sample pixels " + upload_id.bytes)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    db.execute("""
        INSERT INTO uploads(id,kind,sam,filename,declared_size,received,
                            checksum,finalized,target_path)
        VALUES (%s,'reference','SAM 0004','photo.jpg',%s,%s,%s,true,%s)
    """,(upload_id,target.stat().st_size,target.stat().st_size,
        digest if valid else "0"*64,str(target)))
    return upload_id,target,digest

def add_run(db,created_at,status="queued",*,migrated=False):
    batch = uuid.uuid4()
    run_id="20261107T180000-"+uuid.uuid4().hex[:12]
    if migrated:
        db.execute("INSERT INTO batches(id,display_name) VALUES (%s,%s)",(batch,"Test FO"))
    else:
        db.execute("INSERT INTO batches(id) VALUES (%s)",(batch,))
    db.execute("""INSERT INTO jobs(id,batch_id,status,snapshot,created_at)
                  VALUES (%s,%s,%s,%s,%s)""",
               (run_id,batch,status,Jsonb({"id":run_id,"status":status}),created_at))
    return run_id,batch

def test_migration_backfills_existing_fo_fifo_without_changing_jobs(isolated_db):
    db=isolated_db
    a,_=add_run(db,"2026-11-01 09:00:00+00")
    b,_=add_run(db,"2026-11-01 08:00:00+00")
    running,_=add_run(db,"2026-11-01 07:00:00+00","running")
    migrate(db)
    queued=[row["fo_run_id"] for row in work_queue.entries(db)]
    assert queued==[b,a]
    assert db.execute("SELECT status FROM jobs WHERE id=%s",(running,)).fetchone()["status"]=="running"
    assert db.execute("SELECT count(*) AS n FROM jobs").fetchone()["n"]==3
    assert not work_queue.backfill_legacy_queued(db)
    c,_=add_run(db,"2026-11-02 09:00:00+00",migrated=True)
    assert len(work_queue.backfill_legacy_queued(db))==1
    assert [row["fo_run_id"] for row in work_queue.entries(db)]==[b,a,c]
    assert not work_queue.backfill_legacy_queued(db)
    migrate(db)
    assert db.execute("SELECT count(*) AS n FROM work_queue").fetchone()["n"]==3

def test_reference_baseline_validates_files_and_is_idempotent(isolated_db,tmp_path):
    db=isolated_db
    root=tmp_path/"references"
    uid,path,digest=add_reference(db,root)
    migrate(db)
    first=ensure_baseline(db,reference_root=root,model_signature="test-model")
    assert first["baseline_state"]=="ready"
    assert first["version_number"]==1
    assert first["model_signature"]=="test-model"
    values=reference_versions.members(db,first["id"])
    assert len(values)==1
    assert values[0]["reference_id"]==uid
    assert values[0]["source_hash"]==digest
    assert values[0]["target_path"]==str(path)
    # A repeated startup never duplicates a publication or rewrites membership.
    second=ensure_baseline(db,reference_root=root,model_signature="other-model")
    assert second["id"]==first["id"]
    assert second["model_signature"]=="test-model"
    assert db.execute("SELECT count(*) AS n FROM reference_library_events").fetchone()["n"]==1
    assert db.execute("SELECT count(*) AS n FROM reference_library_versions").fetchone()["n"]==1

def test_corrupt_finalized_reference_fails_closed_without_partial_publication(isolated_db,tmp_path):
    db=isolated_db
    root=tmp_path/"references"
    _,_,_=add_reference(db,root)
    damaged,path,digest=add_reference(db,root,valid=False)
    migrate(db)
    result=ensure_baseline(db,reference_root=root,model_signature="test-model")
    assert result["baseline_state"]=="needs_attention"
    assert result["id"] is None
    assert db.execute("SELECT count(*) AS n FROM reference_library_versions").fetchone()["n"]==0
    db.execute("UPDATE uploads SET checksum=%s WHERE id=%s",(digest,damaged))
    recovered=ensure_baseline(db,reference_root=root,model_signature="test-model")
    assert recovered["baseline_state"]=="ready"
    assert len(reference_versions.members(db,recovered["id"]))==2
    assert db.execute("SELECT count(*) AS n FROM reference_library_versions").fetchone()["n"]==1

def test_escaped_reference_path_cannot_enter_published_version(isolated_db,tmp_path):
    db=isolated_db
    root=tmp_path/"references"
    _,target,_=add_reference(db,root)
    migrate(db)
    outside=tmp_path/"unowned.jpg"
    outside.write_bytes(target.read_bytes())
    db.execute("UPDATE uploads SET target_path=%s",(str(outside),))
    result=ensure_baseline(db,reference_root=root,model_signature="test-model")
    assert result["baseline_state"]=="needs_attention"
    assert result["id"] is None

def test_new_queue_cannot_masquerade_as_fo_or_reference_job(isolated_db):
    db=isolated_db
    migrate(db)
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute("INSERT INTO work_queue(kind,fo_run_id) VALUES ('reference_preparation','fake-fo')")
    assert db.execute("SELECT count(*) AS n FROM work_queue").fetchone()["n"]==0
    assert db.execute("SELECT count(*) AS n FROM jobs").fetchone()["n"]==0
