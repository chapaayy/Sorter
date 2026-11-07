"""Stage 2: real PostgreSQL 17, real JPEG bytes, isolated staging and FIFO entries."""
from __future__ import annotations

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from fastapi import HTTPException
from psycopg.conninfo import make_conninfo

from server import database
from server.db.repositories import reference_imports as repository
from server.services import reference_imports,reference_uploads
from server.storage import reference_objects as storage
from server.api.routes import reference_imports as routes
from .test_stage2_platform import _jpg

@pytest.fixture
def isolated_import(tmp_path,monkeypatch):
    if not database.DB_URL:
        pytest.skip("Requires disposable PostgreSQL 17 DATABASE_URL")
    original=database.DB_URL
    schema="refimport_"+uuid.uuid4().hex[:12]
    with psycopg.connect(original) as admin:
        admin.execute('CREATE SCHEMA "'+schema+'"')
    monkeypatch.setattr(database,"DB_URL",
                        make_conninfo(original,options="-c search_path="+schema))
    monkeypatch.setattr(storage,"ROOT",tmp_path/"reference_staging")
    monkeypatch.setattr(storage,"LEGACY_ROOT",tmp_path/"references")
    try:
        database.initialize()
        yield tmp_path
    finally:
        with psycopg.connect(original) as admin:
            admin.execute('DROP SCHEMA "'+schema+'" CASCADE')

def entry(name="one.jpg",*,sha256=None,upload_id=None,sam="SAM 0004",address="Гагарина 64"):
    return routes.ImportFile(
        upload_id=upload_id or uuid.uuid4(),sam=sam,address=address,
        filename=name,relative_path="SAM 0004 — Гагарина 64/"+name,
        size=len(_jpg()),sha256=sha256)

def open_session(items):
    session_id=uuid.uuid4()
    reference_imports.create(session_id)
    response=reference_imports.register_manifest(session_id,items)
    assert response["registered"]
    assert response["expected"]==len(items)
    return session_id

def transfer(sid,item,raw):
    reference_uploads.append(sid,item.upload_id,0,raw)
    return reference_uploads.finish(sid,item.upload_id)

def count_jobs():
    with database.connect() as db:
        return db.execute("""
            SELECT count(*) AS n FROM reference_preparation_jobs
        """).fetchone()["n"]

def test_manifest_is_idempotent_immutable_and_no_job_before_files(isolated_import):
    item=entry()
    sid=open_session([item])
    assert reference_imports.register_manifest(sid,[item])["expected"]==1
    assert reference_imports.create(sid)["expected"]==1
    assert count_jobs()==0
    with pytest.raises(HTTPException) as failed:
        reference_imports.complete(sid)
    assert failed.value.status_code==409
    with pytest.raises(HTTPException) as changed:
        reference_imports.register_manifest(sid,[entry("changed.jpg")])
    assert changed.value.status_code==409
    with pytest.raises(HTTPException) as wrong:
        reference_imports.register_manifest(sid,[entry("../evil.jpg")])
    assert wrong.value.status_code==422

def test_resumable_upload_reconnect_finalize_and_queue_once(isolated_import):
    raw=_jpg()
    item=entry("resumable.jpg",sha256=hashlib.sha256(raw).hexdigest())
    sid=open_session([item])
    first=len(raw)//2
    assert reference_uploads.append(sid,item.upload_id,0,raw[:first])["offset"]==first
    assert reference_imports.file_status(sid,item.upload_id)["offset"]==first
    with database.connect() as db:
        db.execute("UPDATE reference_import_files SET received=0 WHERE upload_id=%s",
                   (item.upload_id,))
    assert reference_imports.file_status(sid,item.upload_id)["offset"]==first
    with pytest.raises(HTTPException) as wrong_offset:
        reference_uploads.append(sid,item.upload_id,0,raw[first:])
    assert wrong_offset.value.status_code==409
    assert reference_uploads.append(sid,item.upload_id,first,raw[first:])["offset"]==len(raw)
    assert count_jobs()==0
    result=reference_uploads.finish(sid,item.upload_id)
    assert result["sha256"]==item.sha256
    state=reference_imports.status(sid)
    assert state["state"]=="complete"
    assert state["preparation_state"]=="queued"
    assert state["queue_seq"] is not None
    assert state["finalized"]==1
    assert state["pending"]==0
    assert count_jobs()==1
    first_job=reference_imports.complete(sid)
    second_job=reference_imports.complete(sid)
    assert first_job==second_job
    assert first_job["preparation_job_id"]==state["preparation_job_id"]
    assert reference_uploads.finish(sid,item.upload_id)["already_finalized"]
    assert count_jobs()==1
    assert not (isolated_import/"references").exists()
    with database.connect() as db:
        files=repository.files(db,sid)
        path=Path(files[0]["stored_path"])
        assert path.is_file()
        assert path.read_bytes()==raw
        assert not storage.partial(sid,item.upload_id).exists()
        assert db.execute("""
            SELECT count(*) AS n FROM work_queue WHERE reference_job_id=%s
        """,(uuid.UUID(first_job["preparation_job_id"]),)).fetchone()["n"]==1

def test_duplicate_receipts_skip_bytes_and_preserve_one_preparation(isolated_import):
    raw=_jpg()
    digest=hashlib.sha256(raw).hexdigest()
    first=entry("one.jpg",sha256=digest)
    second=entry("other.jpg",sha256=digest)
    sid=open_session([first,second])
    transfer(sid,first,raw)
    assert count_jobs()==0
    reference_uploads.append(sid,second.upload_id,0,raw[:12])
    assert storage.partial(sid,second.upload_id).exists()
    assert reference_uploads.confirm_duplicate(sid,second.upload_id,digest)["already_present"]
    assert not storage.partial(sid,second.upload_id).exists()
    state=reference_imports.status(sid)
    assert state["state"]=="complete"
    assert (state["finalized"],state["duplicates"],state["pending"])==(1,1,0)
    assert count_jobs()==1
    assert reference_uploads.confirm_duplicate(sid,second.upload_id,digest)["already_present"]
    assert count_jobs()==1
    assert len(list((isolated_import/"reference_staging"/str(sid)/"files").iterdir()))==1

def test_duplicate_can_be_confirmed_against_published_staged_source(isolated_import):
    from server.services import reference_publication
    raw=_jpg()
    digest=hashlib.sha256(raw).hexdigest()
    key=uuid.uuid4()
    source=storage.object_path(uuid.uuid4(),key,"old.jpg")
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_bytes(raw)
    with database.connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        reference_publication.publish(db,[{
            "reference_id":key,"sam":"SAM 0004","filename":"old.jpg",
            "source_hash":digest,"target_path":str(source),
            "declared_size":len(raw),"source_kind":"staged"}],"test-model")
    item=entry("new-name.jpg",sha256=digest)
    sid=open_session([item])
    assert reference_uploads.confirm_duplicate(sid,item.upload_id,digest)["already_present"]
    assert reference_imports.status(sid)["duplicates"]==1
    assert count_jobs()==1
    assert source.read_bytes()==raw

def test_uploaded_bytes_are_deduplicated_on_server(isolated_import):
    raw=_jpg()
    one=entry("original.jpg")
    other=entry("copy.jpg")
    sid=open_session([one,other])
    transfer(sid,one,raw)
    result=transfer(sid,other,raw)
    assert result["already_present"]
    assert count_jobs()==1
    state=reference_imports.status(sid)
    assert state["finalized"]==1
    assert state["duplicates"]==1
    assert len(list((isolated_import/"reference_staging"/str(sid)/"files").iterdir()))==1

def test_duplicate_without_verified_source_is_rejected(isolated_import):
    raw=_jpg()
    digest=hashlib.sha256(raw).hexdigest()
    item=entry(sha256=digest)
    sid=open_session([item])
    with pytest.raises(HTTPException) as err:
        reference_uploads.confirm_duplicate(sid,item.upload_id,digest)
    assert err.value.status_code==409
    assert reference_imports.status(sid)["state"]=="uploading"
    assert count_jobs()==0

def test_corrupt_content_or_wrong_checksum_never_enqueues(isolated_import):
    raw=_jpg()
    item=entry(sha256="0"*64)
    sid=open_session([item])
    reference_uploads.append(sid,item.upload_id,0,raw)
    with pytest.raises(HTTPException) as mismatch:
        reference_uploads.finish(sid,item.upload_id)
    assert mismatch.value.status_code==422
    assert count_jobs()==0
    invalid=entry("other.jpg",sha256=hashlib.sha256(b"x"*len(raw)).hexdigest())
    second=open_session([invalid])
    reference_uploads.append(second,invalid.upload_id,0,b"x"*len(raw))
    with pytest.raises(HTTPException) as malformed:
        reference_uploads.finish(second,invalid.upload_id)
    assert malformed.value.status_code==422
    assert count_jobs()==0

def test_two_independent_sessions_have_two_fifo_jobs(isolated_import):
    data=_jpg()
    first=entry("first.jpg")
    second=entry("second.jpg")
    s1=open_session([first])
    s2=open_session([second])
    transfer(s1,first,data)
    transfer(s2,second,data)
    state1=reference_imports.status(s1)
    state2=reference_imports.status(s2)
    assert count_jobs()==2
    assert state1["preparation_job_id"]!=state2["preparation_job_id"]
    assert state1["queue_seq"]<state2["queue_seq"]

def test_parallel_last_two_finishes_queue_exactly_once(isolated_import):
    data=_jpg()
    a,b=entry("a.jpg"),entry("b.jpg")
    sid=open_session([a,b])
    reference_uploads.append(sid,a.upload_id,0,data)
    reference_uploads.append(sid,b.upload_id,0,data)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(reference_uploads.finish,sid,x.upload_id) for x in (a,b)]
        assert all(f.result(timeout=20)["sha256"] for f in futures)
    assert reference_imports.status(sid)["state"]=="complete"
    assert count_jobs()==1

def test_missing_staged_file_blocks_completion_without_false_success(isolated_import):
    raw=_jpg()
    item=entry()
    sid=open_session([item])
    reference_uploads.append(sid,item.upload_id,0,raw)
    storage.partial(sid,item.upload_id).unlink()
    with pytest.raises(HTTPException):
        reference_uploads.finish(sid,item.upload_id)
    assert reference_imports.status(sid)["pending"]==1
    assert count_jobs()==0

def test_staging_symlink_parent_is_rejected_before_writing(isolated_import):
    raw=_jpg()
    item=entry()
    sid=open_session([item])
    incoming=storage.session_root(sid)/"incoming"
    incoming.parent.mkdir(parents=True)
    outside=isolated_import/"outside"
    outside.mkdir()
    incoming.symlink_to(outside,target_is_directory=True)
    with pytest.raises(HTTPException) as forbidden:
        reference_uploads.append(sid,item.upload_id,0,raw)
    assert forbidden.value.status_code==409
    assert not list(outside.iterdir())
    assert count_jobs()==0

def test_reference_import_rejects_filename_path(isolated_import):
    item=entry("folder/photo.jpg")
    with pytest.raises(HTTPException) as forbidden:
        open_session([item])
    assert forbidden.value.status_code==422

def test_staged_api_is_always_available_without_flags(isolated_import,monkeypatch):
    monkeypatch.delenv("REFERENCE_IMPORT_STAGING_ENABLED",raising=False)
    monkeypatch.delenv("PHOTOSORTER_UNIFIED_QUEUE",raising=False)
    sid=uuid.uuid4()
    state=routes.create(routes.NewSession(client_session_id=sid))
    assert state["id"]==str(sid)
    assert not state["registered"]
    listing=routes.list_sessions()
    assert any(item["id"]==sid for item in listing["sessions"])
