"""Stage 3 unified FIFO: real isolated PostgreSQL, immutable staged file and snapshots.

No model inference: precomputed cache vectors verify the publication contract.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import numpy as np
import psycopg
import pytest
from fastapi import HTTPException
from psycopg.conninfo import make_conninfo

from server import database,jobs
from server.db.repositories import work_queue,reference_versions
from server.services import reference_imports,reference_uploads,reference_publication
from server.storage import reference_objects,reference_versions as objects
from server.workers import reference_prepare
from server.api.routes import work_queue as actions
from .test_stage2_platform import _jpg

@pytest.fixture
def system(tmp_path,monkeypatch):
    if not database.DB_URL:
        pytest.skip("Requires disposable PostgreSQL")
    url=database.DB_URL
    schema="unified_"+uuid.uuid4().hex[:12]
    with psycopg.connect(url) as admin:
        admin.execute('CREATE SCHEMA "'+schema+'"')
    monkeypatch.setattr(database,"DB_URL",make_conninfo(url,options="-c search_path="+schema))
    root=tmp_path/"data"
    refs=root/"references"
    refs.mkdir(parents=True)
    monkeypatch.setattr(objects,"ROOT",root/"reference_objects")
    monkeypatch.setattr(objects,"LEGACY_ROOT",refs)
    monkeypatch.setattr(reference_objects,"ROOT",root/"reference_staging")
    monkeypatch.setattr(reference_objects,"LEGACY_ROOT",refs)
    monkeypatch.setattr(reference_prepare,"REFERENCE_GALLERY",refs)
    monkeypatch.setattr(reference_prepare,"signature",lambda:"stage3-model")
    monkeypatch.setattr(work_queue,"signature",lambda:"stage3-model")
    monkeypatch.setenv("PHOTOSORTER_UNIFIED_QUEUE","1")
    from server import reference_cache
    cache=root/"cache"/"megaloc"/"references"
    cache.mkdir(parents=True)
    monkeypatch.setattr(reference_cache,"CACHE_DIR",cache)
    database.initialize()
    try:
        yield root
    finally:
        with psycopg.connect(url) as admin:
            admin.execute('DROP SCHEMA "'+schema+'" CASCADE')

def add_legacy(root):
    ref=root/"references"/"SAM-0001"/"one.jpg"
    ref.parent.mkdir(parents=True,exist_ok=True)
    raw=_jpg()
    ref.write_bytes(raw)
    key=uuid.uuid4()
    with database.connect() as db:
        db.execute("""INSERT INTO uploads(id,kind,sam,filename,declared_size,
           received,checksum,finalized,target_path)
           VALUES (%s,'reference','SAM-0001','one.jpg',%s,%s,%s,true,%s)""",
           (key,len(raw),len(raw),hashlib.sha256(raw).hexdigest(),str(ref)))
    return key,ref

def add_fo():
    batch=uuid.uuid4()
    with database.connect() as db:
        db.execute("""INSERT INTO batches(id,display_name,upload_manifest_state)
             VALUES (%s,'Test FO','complete')""",(batch,))
        db.execute("""INSERT INTO uploads(id,kind,batch_id,filename,declared_size,
             received,finalized) VALUES (%s,'fo',%s,'report.jpg',100,100,true)""",
             (uuid.uuid4(),batch))
    return jobs.enqueue(jobs.NewRun(batch_id=batch))["id"]

def prepare_import(root):
    raw=_jpg(exif=True)
    fid=uuid.uuid4()
    sid=uuid.uuid4()
    reference_imports.create(sid)
    from server.api.routes.reference_imports import ImportFile
    entry=ImportFile(upload_id=fid,sam="SAM 0004",address="Гагарина 64",
         relative_path="SAM 0004 — Гагарина 64/new.jpg",
         filename="new.jpg",size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    reference_imports.register_manifest(sid,[entry])
    assert reference_imports.status(sid)["state"]=="uploading"
    reference_uploads.append(sid,fid,0,raw)
    assert reference_uploads.finish(sid,fid)["already_present"] is False
    state=reference_imports.status(sid)
    assert state["state"]=="complete"
    path=reference_objects.object_path(sid,fid,"new.jpg")
    return sid,fid,path,hashlib.sha256(raw).hexdigest(),state["preparation_job_id"]

def cache_vector(root,digest):
    target=root/"cache"/"megaloc"/"references"/(digest+".npy")
    np.save(target,np.asarray([0.9,0.1],dtype="float32"))
    with database.connect() as db:
        db.execute("""INSERT INTO reference_cache(source_hash,model_signature,cache_path)
        VALUES (%s,'stage3-model',%s)""",(digest,str(target)))

def finish_fo(run_id):
    with database.connect() as db:
        db.execute("UPDATE jobs SET status='completed',finished_at=now() WHERE id=%s",
                   (run_id,))
        work_queue.finish_fo(db,run_id,"completed")

def test_fifo_5_fo_prep_fo_has_frozen_v_before_and_after(system):
    add_legacy(system)
    first=[add_fo() for _ in range(5)]
    sid,uid,path,digest,pid=prepare_import(system)
    final=add_fo()
    with database.connect() as db:
        entries=work_queue.entries(db)
        assert [x["kind"] for x in entries]==(["fo_processing"]*5+
              ["reference_preparation","fo_processing"])
    initial_versions=[]
    for run_id in first:
        with database.connect() as db:
            task=work_queue.claim_next(db)
        assert task and task["kind"]=="fo_processing"
        assert task["id"]==run_id
        assert len(task["info"]["reference_members"])==1
        initial_versions.append(task["info"]["reference_version"])
        first_path=task["info"]["reference_members"][0]["path"]
        assert Path(first_path).is_file()
        assert "/reference_objects/" in first_path
        finish_fo(run_id)
    assert len(set(initial_versions))==1
    with database.connect() as db:
        item=work_queue.claim_next(db)
    assert item["kind"]=="reference_preparation"
    assert str(item["id"])==pid
    cache_vector(system,digest)
    result=reference_prepare.run(item["id"])
    assert result["changed"] is True
    assert result["version"]==initial_versions[0]+1
    with database.connect() as db:
        task=work_queue.claim_next(db)
    assert task["id"]==final
    assert task["info"]["reference_version"]==result["version"]
    assert len(task["info"]["reference_members"])==2
    assert {x["sam"] for x in task["info"]["reference_members"]}=={"SAM-0001","SAM 0004"}
    finish_fo(final)

def test_failure_blocks_later_fo_until_retry_or_explicit_skip(system):
    add_legacy(system)
    sid,uid,path,digest,pid=prepare_import(system)
    run=add_fo()
    with database.connect() as db:
        item=work_queue.claim_next(db)
        before=reference_versions.current(db)["id"]
    assert item["kind"]=="reference_preparation"
    path.unlink()
    with pytest.raises((ValueError,OSError)):
        reference_prepare.run(item["id"])
    with database.connect() as db:
        work_queue.finish_preparation(db,item["id"],"failed","missing source")
        assert reference_versions.current(db)["id"]==before
        assert work_queue.claim_next(db) is None
    action=actions.PreparationAction(idempotency_key=uuid.uuid4())
    a=actions.retry(uuid.UUID(pid),action)
    assert a["state"]=="queued"
    assert actions.retry(uuid.UUID(pid),action)["already_applied"]
    with database.connect() as db:
        task=work_queue.claim_next(db)
    assert task["kind"]=="reference_preparation"
    with database.connect() as db:
        work_queue.finish_preparation(db,task["id"],"failed","still missing")
    with database.connect() as db:
        assert work_queue.claim_next(db) is None
    skip=actions.skip(uuid.UUID(pid),actions.PreparationAction(idempotency_key=uuid.uuid4()))
    assert skip["state"]=="stopped"
    with database.connect() as db:
        next_item=work_queue.claim_next(db)
    assert next_item["id"]==run
    assert len(next_item["info"]["reference_members"])==1
    finish_fo(run)

def test_legacy_snapshots_use_immutable_paths_not_deleted_legacy(system):
    key,path=add_legacy(system)
    run=add_fo()
    with database.connect() as db:
        item=work_queue.claim_next(db)
    pinned=Path(item["info"]["reference_members"][0]["path"])
    original=pinned.read_bytes()
    path.unlink()
    assert pinned.read_bytes()==original
    assert pinned!=path
    finish_fo(run)

def test_readiness_never_queues_half_uploaded_session(system):
    add_legacy(system)
    fid=uuid.uuid4()
    sid=uuid.uuid4()
    reference_imports.create(sid)
    from server.api.routes.reference_imports import ImportFile
    entry=ImportFile(upload_id=fid,sam="SAM 0004",address="Гагарина 64",
      relative_path="SAM 0004 — Гагарина 64/partial.jpg",filename="partial.jpg",size=len(_jpg()))
    reference_imports.register_manifest(sid,[entry])
    reference_uploads.append(sid,fid,0,_jpg()[:100])
    with pytest.raises(HTTPException):
        reference_imports.complete(sid)
    with database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM reference_preparation_jobs").fetchone()["n"]==0
        assert db.execute("SELECT count(*) AS n FROM work_queue").fetchone()["n"]==0

def test_auto_fo_reserves_fifo_on_final_manifest_file(system,monkeypatch):
    from types import SimpleNamespace
    from server import uploads
    from server.services import upload_manifest,auto_processing
    add_legacy(system)
    raw=_jpg()
    batch=uuid.uuid4()
    file_id=uuid.uuid4()
    with database.connect() as db:
        db.execute("""INSERT INTO batches(id,display_name) VALUES (%s,'Auto FO')""",
                   (batch,))
    files=[SimpleNamespace(upload_id=file_id,relative_path="photo.jpg",
                           filename="photo.jpg",size=len(raw))]
    upload_manifest.register(batch,files,auto_process=True,grouping_threshold=.5)
    monkeypatch.setattr(uploads,"UPLOADS_DIR",system/"uploads")
    monkeypatch.setattr(uploads,"PART_DIR",system/"incoming")
    uploads._create_upload(uploads.BeginUpload(
         kind="fo",batch_id=str(batch),filename="photo.jpg",
         size=len(raw),sha256=hashlib.sha256(raw).hexdigest()),file_id)
    (system/"incoming"/(str(file_id)+".part")).write_bytes(raw)
    uploads._finalize_sync(str(file_id))
    with database.connect() as db:
        queued=db.execute("""
            SELECT b.auto_process_state,b.auto_process_run_id,j.id AS actual_id,
                   w.seq,w.kind FROM batches b JOIN jobs j ON j.batch_id=b.id
                   JOIN work_queue w ON w.fo_run_id=j.id WHERE b.id=%s
        """,(batch,)).fetchone()
        assert queued["auto_process_state"]=="queued"
        assert queued["auto_process_run_id"]==queued["actual_id"]
        assert queued["kind"]=="fo_processing"
        assert queued["seq"]==1
    # The cleanup poll must not queue another run.
    with database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM jobs WHERE batch_id=%s",
                          (batch,)).fetchone()["n"]==1

def test_duplicate_only_preparation_does_not_create_version(system):
    ref_id,path=add_legacy(system)
    raw=path.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    sid,fid=uuid.uuid4(),uuid.uuid4()
    reference_imports.create(sid)
    from server.api.routes.reference_imports import ImportFile
    entry=ImportFile(upload_id=fid,sam="SAM-0001",
        relative_path="SAM-0001/duplicate.jpg",filename="duplicate.jpg",
        size=len(raw),sha256=digest)
    reference_imports.register_manifest(sid,[entry])
    assert reference_uploads.confirm_duplicate(sid,fid,digest)["already_present"]
    with database.connect() as db:
        task=work_queue.claim_next(db)
        current=reference_versions.current(db)["version_number"]
    assert task["kind"]=="reference_preparation"
    result=reference_prepare.run(task["id"])
    assert result=={"version":current,"changed":False}
    with database.connect() as db:
        assert reference_versions.current(db)["version_number"]==current
        assert db.execute("SELECT count(*) AS n FROM reference_library_versions").fetchone()["n"]==current

def test_interrupted_preparation_is_barrier_until_retry(system):
    add_legacy(system)
    sid,uid,path,digest,pid=prepare_import(system)
    after=add_fo()
    with database.connect() as db:
        task=work_queue.claim_next(db)
        assert task["kind"]=="reference_preparation"
        work_queue.mark_interrupted(db)
        assert work_queue.claim_next(db) is None
    action=actions.PreparationAction(idempotency_key=uuid.uuid4())
    assert actions.retry(uuid.UUID(pid),action)["state"]=="queued"
    with database.connect() as db:
        again=work_queue.claim_next(db)
        assert again["id"]==task["id"]
        assert again["seq"]==task["seq"]

def test_stop_running_preparation_does_not_implicitly_skip_change(system):
    add_legacy(system)
    sid,uid,path,digest,pid=prepare_import(system)
    later=add_fo()
    with database.connect() as db:
        item=work_queue.claim_next(db)
        assert item["kind"]=="reference_preparation"
    request=actions.stop_running(uuid.UUID(pid))
    assert request["state"]=="stopping"
    assert actions.stop_running(uuid.UUID(pid))["stop_requested"]
    with pytest.raises(reference_prepare.PreparationCancelled):
        reference_prepare.run(item["id"])
    with database.connect() as db:
        work_queue.finish_preparation(db,item["id"],"interrupted","Остановлено пользователем")
        assert work_queue.claim_next(db) is None
    assert actions.stop_running(uuid.UUID(pid))["state"]=="interrupted"
    assert actions.skip(uuid.UUID(pid),
           actions.PreparationAction(idempotency_key=uuid.uuid4()))["state"]=="stopped"
    with database.connect() as db:
        resumed=work_queue.claim_next(db)
        assert resumed["id"]==later
    finish_fo(later)
