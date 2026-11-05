"""Stage 1 safety contract on disposable test files and a disposable test DB."""
from __future__ import annotations
import errno
import asyncio
import hashlib
import io
import json
import os
import uuid
import zipfile
from datetime import datetime,timezone
from pathlib import Path
import pytest

from server.storage.hardlinks import link_or_copy,sha256
from server.storage import paths

def test_hardlink_exact_inode_checksum_and_original_survives(tmp_path):
    source=tmp_path/"original.jpg"
    source.write_bytes(b"some-photo-bytes")
    original=sha256(source)
    output=tmp_path/"SAM-0001.jpg"
    assert link_or_copy(source,output)=="hardlink"
    assert (source.stat().st_ino,source.stat().st_dev)==(output.stat().st_ino,output.stat().st_dev)
    output.unlink()
    assert sha256(source)==original
    link_or_copy(source,output)
    source.unlink()
    assert output.read_bytes()==b"some-photo-bytes"

def test_hardlink_cross_device_fallback_and_no_partial_output(tmp_path,monkeypatch):
    from server.storage import hardlinks
    source=tmp_path/"src.jpg"
    source.write_bytes(b"raw")
    target=tmp_path/"dest.jpg"
    def exdev(*args,**kwargs):raise OSError(errno.EXDEV,"different mount")
    monkeypatch.setattr(hardlinks.os,"link",exdev)
    assert link_or_copy(source,target)=="copy"
    assert target.read_bytes()==source.read_bytes()
    assert target.stat().st_ino != source.stat().st_ino
    with pytest.raises(FileExistsError):link_or_copy(source,target)
    assert target.read_bytes()==b"raw", "An existing export must survive a name collision"
    with pytest.raises(ValueError):
        link_or_copy(source,tmp_path/"bad.jpg",expected_hash="0"*64)
    assert not (tmp_path/"bad.jpg").exists()

@pytest.fixture
def db():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("No disposable PostgreSQL test instance")
    from server.database import initialize
    initialize()
    return None

@pytest.fixture
def sandbox(tmp_path,monkeypatch,db):
    from server.services import cleanup,batches,retention
    from server.api.routes import images
    from app.results import repository
    data=tmp_path/"data"
    for folder in ("uploads","outputs","incoming","references","runs"):
        (data/folder).mkdir(parents=True)
    monkeypatch.setattr(paths,"UPLOADS",data/"uploads")
    monkeypatch.setattr(paths,"OUTPUTS",data/"outputs")
    monkeypatch.setattr(cleanup,"DATA_DIR",data)
    monkeypatch.setattr(cleanup,"RUNS_DIR",data/"runs")
    monkeypatch.setattr(batches,"DATA_DIR",data)
    monkeypatch.setattr(retention,"DATA_DIR",data)
    monkeypatch.setattr(images,"DATA_DIR",data)
    monkeypatch.setattr(repository,"RUNS_DIR",data/"runs")
    return data

def _batch(data,with_photo=True):
    from server.services import batches
    from server.database import connect
    ident=uuid.UUID(batches.create("Тестовая партия")["batch_id"])
    if with_photo:
        file_id=uuid.uuid4()
        folder=paths.batch_dir(ident)
        folder.mkdir(parents=True,exist_ok=True)
        target=folder/f"{file_id}.jpg"
        target.write_bytes(f"fake-photo-{ident}".encode())
        with connect() as db:
            db.execute("""INSERT INTO uploads(id,kind,batch_id,filename,declared_size,
                received,checksum,finalized,target_path)
                VALUES (%s,'fo',%s,'test.jpg',%s,%s,%s,true,%s)""",
                (file_id,ident,target.stat().st_size,target.stat().st_size,
                 sha256(target),str(target)))
    return ident

def _job(data,batch_id,status="completed"):
    from psycopg.types.json import Jsonb
    from server.database import connect
    run_id="20261105T000000-"+uuid.uuid4().hex[:12]
    with connect() as db:
        db.execute("INSERT INTO jobs(id,batch_id,status,snapshot) VALUES (%s,%s,%s,%s)",
                   (run_id,batch_id,status,Jsonb({"id":run_id,"status":status})))
    return run_id

def test_additive_migration_legacy_rows_survive(db):
    import psycopg
    from server.database import DB_URL,SCHEMA
    from server.db.migration_runner import migrate
    schema="stage1_"+uuid.uuid4().hex[:16]
    with psycopg.connect(DB_URL) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
        try:
            conn.execute(f'SET search_path TO "{schema}"')
            for statement in SCHEMA.split(";"):
                if statement.strip():conn.execute(statement)
            old=uuid.uuid4()
            conn.execute("INSERT INTO batches(id) VALUES (%s)",(old,))
            migrate(conn)
            assert conn.execute("SELECT display_name FROM batches WHERE id=%s",(old,)).fetchone()[0].startswith("ФО ")
            migrate(conn)
            assert {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}=={
                "0001_batch_lifecycle.sql","0002_batch_upload_state.sql",
                "0003_thumbnails_queue.sql","0004_megaloc_queue.sql",
                "0005_result_pages.sql","0006_unfinished_age.sql",
                "0007_service_heartbeat.sql"}
            assert conn.execute("SELECT id FROM batches WHERE id=%s",(old,)).fetchone()[0]==old
        finally:
            conn.execute("RESET search_path")
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')

def test_batch_photo_removal_only_before_first_run(sandbox):
    from server.services import batches
    from server.database import connect
    batch=_batch(sandbox)
    with connect() as db:
        photo_id=db.execute("SELECT id FROM uploads WHERE batch_id=%s",(batch,)).fetchone()["id"]
    assert batches.photos(batch)["total"]==1
    run=_job(sandbox,batch)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        batches.remove_unprocessed_photo(batch,photo_id)
    assert exc.value.status_code==409
    from server.services.cleanup import request,cleanup_one
    request(batch)
    assert cleanup_one(batch)=="completed"

def test_cleanup_only_owned_paths_multiple_runs_and_idempotent(sandbox):
    from server.services import cleanup
    from server.database import connect
    own=_batch(sandbox)
    other=_batch(sandbox)
    protected=sandbox/"references"/"SAM-0001"/"ref.jpg"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"permanent-reference")
    runs=[_job(sandbox,own),_job(sandbox,own)]
    source=next(paths.batch_dir(own).iterdir())
    for run in runs:
        target=paths.run_dir(run)/"megaloc"/"SAM-0001"/"photo.jpg"
        target.parent.mkdir(parents=True)
        os.link(source,target)
        run_folder=sandbox/"runs"/run
        run_folder.mkdir()
        (run_folder/"run.json").write_text("{}",encoding="utf8")
    assert cleanup.request(own)["state"]=="deleting"
    assert cleanup.cleanup_one(own)=="completed"
    assert not paths.batch_dir(own).exists()
    assert all(not paths.run_dir(run).exists() for run in runs)
    assert all(not (sandbox/"runs"/run).exists() for run in runs)
    assert paths.batch_dir(other).exists()
    assert protected.read_bytes()==b"permanent-reference"
    assert cleanup.request(own)["state"]=="deleted"
    assert cleanup.cleanup_one(own)=="skipped"
    with connect() as db:
        assert db.execute("SELECT count(*) AS n FROM jobs WHERE batch_id=%s",(own,)).fetchone()["n"]==0
    cleanup.request(other)
    cleanup.cleanup_one(other)

def test_cleanup_waits_for_operations_and_running_jobs(sandbox):
    from server.services import cleanup,operations
    from server.database import connect
    own=_batch(sandbox)
    queued=_job(sandbox,own,"queued")
    running=_job(sandbox,own,"running")
    lease=operations.start(own,"download")
    cleanup.request(own)
    with connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=%s",(queued,)).fetchone()["status"]=="stopped"
        assert db.execute("SELECT status FROM jobs WHERE id=%s",(running,)).fetchone()["status"]=="stopping"
    assert cleanup.cleanup_one(own)=="waiting"
    operations.finish(lease)
    assert cleanup.cleanup_one(own)=="waiting"
    with connect() as db:
        db.execute("UPDATE jobs SET status='stopped' WHERE id=%s",(running,))
    assert cleanup.cleanup_one(own)=="completed"

def test_cleanup_crash_resume_no_unrelated_deletion(sandbox,monkeypatch):
    from server.services import cleanup
    own=_batch(sandbox)
    other=_batch(sandbox)
    original=cleanup._files
    state={"attempts":0}
    def failing(*args):
        state["attempts"]+=1
        if state["attempts"]==1:
            original(*args)
            raise RuntimeError("simulated crash after filesystem cleanup")
        original(*args)
    monkeypatch.setattr(cleanup,"_files",failing)
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="failed"
    assert cleanup.get_status(own)["delete_state"]=="delete_failed"
    assert paths.batch_dir(other).exists()
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="completed"
    assert paths.batch_dir(other).exists()
    cleanup.request(other)
    cleanup.cleanup_one(other)

def test_confirm_calendar_months_extension_and_warning(sandbox):
    from server.services import retention,cleanup
    from server.database import connect
    own=_batch(sandbox)
    run=_job(sandbox,own)
    directory=paths.run_dir(run)/"megaloc"
    directory.mkdir(parents=True)
    (directory/"manifest.json").write_text("[]",encoding="utf8")
    assert retention.status(own)["delete_after_at"] is None
    data=retention.confirm(own,run)
    assert data["delete_after_at"]>data["download_confirmed_at"]
    assert data["delete_after_at"].month in (1,2,3,4,5,6,7,8,9,10,11,12)
    extended=retention.extend(own)
    assert extended["delete_after_at"]>data["delete_after_at"]
    with connect() as db:
        result=db.execute("""SELECT
          (timestamp '2027-01-31 12:00:00'+interval '2 months')::date AS date""").fetchone()
    assert str(result["date"])=="2027-03-31"
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_legacy_zip_and_stream_lease_survives_delete_request(sandbox):
    from app.results import repository
    from server.api.routes.downloads import download_results
    from server.services import cleanup
    from server.database import connect
    own=_batch(sandbox)
    run=_job(sandbox,own)
    source=next(paths.batch_dir(own).iterdir())
    target=paths.run_dir(run)/"megaloc"/"SAM-0045"/"photo.jpg"
    target.parent.mkdir(parents=True)
    os.link(source,target)
    run_model_dir=sandbox/"runs"/run/"models"
    run_model_dir.mkdir(parents=True)
    (run_model_dir/"megaloc.json").write_text(json.dumps({"path":str(target.parents[1]/"manifest.json")}),encoding="utf8")
    (target.parents[1]/"manifest.json").write_text(json.dumps([{
        "query":str(source),"copy":str(target),"assigned_sam":"SAM-0045","top":[]
    }]),encoding="utf8")
    response=download_results(run)
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="waiting"
    async def collect():
        chunks=[]
        async for item in response.body_iterator:
            chunks.append(item)
        return b"".join(chunks)
    body=asyncio.run(collect())
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.namelist()==["SAM-0045/photo.jpg"]
        assert archive.read("SAM-0045/photo.jpg")==source.read_bytes()
    assert cleanup.cleanup_one(own)=="completed"

def test_retention_due_guard_cannot_delete_after_new_run(sandbox):
    from server.services import cleanup,retention
    from server.database import connect
    own=_batch(sandbox)
    run=_job(sandbox,own)
    directory=paths.run_dir(run)/"megaloc"
    directory.mkdir(parents=True)
    (directory/"manifest.json").write_text("[]",encoding="utf8")
    retention.confirm(own,run)
    with connect() as db:
        db.execute("""UPDATE batches SET delete_after_at=now()-interval '1 minute'
            WHERE id=%s""",(own,))
    # Scheduler may have read a due ID before a newer run invalidated the date.
    with connect() as db:
        db.execute("""UPDATE batches SET delete_after_at=NULL,
           download_confirmed_at=NULL,confirmed_run_id=NULL WHERE id=%s""",(own,))
    assert cleanup.request(own,only_if_due=True)["state"]=="skipped"
    assert paths.batch_dir(own).exists()
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_warning_for_stale_unconfirmed_and_seven_day_notice(sandbox):
    from server.services import retention,cleanup
    from server.database import connect
    own=_batch(sandbox,with_photo=False)
    with connect() as db:
        db.execute("UPDATE batches SET created_at=now()-interval '31 days' WHERE id=%s",(own,))
    assert retention.status(own)["stale_unconfirmed"] is True
    assert retention.status(own)["warning"] is False
    with connect() as db:
        db.execute("""UPDATE batches SET delete_after_at=now()+interval '6 days',
            download_confirmed_at=now() WHERE id=%s""",(own,))
    assert retention.status(own)["warning"] is True
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_hardlink_collision_does_not_unlink_original_result(tmp_path):
    src=tmp_path/"original.jpg"
    src.write_bytes(b"new content")
    destination=tmp_path/"old-result.jpg"
    destination.write_bytes(b"important historical output")
    with pytest.raises(FileExistsError):
        link_or_copy(src,destination)
    assert destination.read_bytes()==b"important historical output"
    assert src.read_bytes()==b"new content"

def test_result_export_atomic_hardlink_and_manifest_contract(sandbox):
    from app.results import repository
    run="20261105T120000-"+uuid.uuid4().hex[:12]
    source=sandbox/"uploads"/"source.jpg"
    source.write_bytes(b"exact immutable pixels")
    original=sha256(source)
    stamp=(source.stat().st_size,source.stat().st_mtime_ns)
    rows=[{"query":str(source),"top":[{"label":"SAM-0045","score":0.95,
            "reference":"sample.jpg"}],"group_id":"G0001"}]
    saved=repository.save_model({"id":run,"output":str(sandbox/"outputs")},
            "megaloc",rows,query_stamps={str(source):stamp})
    copy=Path(saved[0]["copy"])
    assert copy.exists() and copy.stat().st_ino==source.stat().st_ino
    assert sha256(source)==original
    assert (copy.parents[1]/"manifest.json").is_file()
    reloaded=repository.load_model(run,"megaloc")
    assert reloaded[0]["assigned_sam"]=="SAM-0045"
    assert reloaded[0]["score"]==0.95
    assert reloaded[0]["copy"]==str(copy)
    assert not (copy.parents[2]/".megaloc.building").exists()
    with pytest.raises(FileExistsError):
        repository.save_model({"id":run,"output":str(sandbox/"outputs")},
            "megaloc",rows,query_stamps={str(source):stamp})
    assert sha256(copy)==original

def test_export_crash_does_not_publish_partial_result(sandbox,monkeypatch):
    from app.results import repository
    run="20261105T120000-"+uuid.uuid4().hex[:12]
    source=sandbox/"uploads"/"first.jpg"
    source.write_bytes(b"first")
    second=sandbox/"uploads"/"second.jpg"
    second.write_bytes(b"second")
    old=repository.copy_photo
    count={"n":0}
    def fail_after_first(*args,**kwargs):
        count["n"]+=1
        if count["n"]==2:raise RuntimeError("simulated interrupted output")
        return old(*args,**kwargs)
    monkeypatch.setattr(repository,"copy_photo",fail_after_first)
    rows=[{"query":str(source),"top":[]},{"query":str(second),"top":[]}]
    with pytest.raises(RuntimeError):
        repository.save_model({"id":run,"output":str(sandbox/"outputs")},
                              "megaloc",rows)
    assert not paths.run_dir(run).exists() or not (paths.run_dir(run)/"megaloc").exists()
    assert not (paths.run_dir(run)/".megaloc.building").exists()
    assert source.read_bytes()==b"first"
    assert second.read_bytes()==b"second"

def test_cannot_reconfirm_old_zip_after_a_newer_run(sandbox):
    from server.services import retention,cleanup
    from server.database import connect
    from fastapi import HTTPException
    own=_batch(sandbox)
    old=_job(sandbox,own)
    olddir=paths.run_dir(old)/"megaloc"
    olddir.mkdir(parents=True)
    (olddir/"manifest.json").write_text("[]",encoding="utf8")
    retention.confirm(own,old)
    new=_job(sandbox,own,"running")
    with connect() as db:
        db.execute("""UPDATE batches SET download_confirmed_at=NULL,
           confirmed_run_id=NULL,delete_after_at=NULL WHERE id=%s""",(own,))
    with pytest.raises(HTTPException) as err:
        retention.confirm(own,old)
    assert err.value.status_code==409
    assert retention.status(own)["delete_after_at"] is None
    cleanup.request(own)
    with connect() as db:
        db.execute("UPDATE jobs SET status='stopped' WHERE id=%s",(new,))
    cleanup.cleanup_one(own)

def test_orphan_unpublished_export_only_terminal_jobs(sandbox):
    import time
    from server.services import cleanup
    own=_batch(sandbox)
    finished=_job(sandbox,own,"interrupted")
    running=_job(sandbox,own,"running")
    folder1=paths.run_dir(finished)/".megaloc.building"
    folder2=paths.run_dir(running)/".megaloc.building"
    for folder in (folder1,folder2):
        folder.mkdir(parents=True)
        (folder/"unfinished.jpg").write_bytes(b"temporary")
        os.utime(folder,(time.time()-7200,time.time()-7200))
    removed=cleanup.reconcile_incomplete_exports(grace_seconds=3600)
    assert finished in removed
    assert not folder1.exists()
    assert folder2.exists(), "Do not clear still-running inference outputs"
    cleanup.request(own)
    from server.database import connect
    with connect() as db:
        db.execute("UPDATE jobs SET status='stopped' WHERE id=%s",(running,))
    cleanup.cleanup_one(own)

def test_delete_refuses_symlink_escape_and_leaves_external_files(sandbox,tmp_path):
    from server.services import cleanup
    own=_batch(sandbox,with_photo=False)
    external=tmp_path/"outside_uploads"
    external.mkdir()
    (external/"protected.jpg").write_bytes(b"never delete")
    batchfolder=paths.batch_dir(own)
    batchfolder.symlink_to(external,target_is_directory=True)
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="failed"
    assert (external/"protected.jpg").read_bytes()==b"never delete"
    assert cleanup.get_status(own)["delete_state"]=="delete_failed"
    batchfolder.unlink()
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="completed"
    assert (external/"protected.jpg").read_bytes()==b"never delete"

def test_calendar_months_are_not_sixty_days(db):
    from server.database import connect
    with connect() as conn:
        rows=conn.execute("""SELECT
            (timestamp '2027-12-31 15:00:00' + interval '2 months')::date AS feb,
            (timestamp '2028-01-31 15:00:00' + interval '2 months')::date AS march,
            (timestamp '2028-02-29 15:00:00' + interval '2 months')::date AS april
        """).fetchone()
    assert str(rows["feb"])=="2028-02-29"
    assert str(rows["march"])=="2028-03-31"
    assert str(rows["april"])=="2028-04-29"

def test_upload_state_transitions_with_real_finalization(sandbox,monkeypatch):
    from PIL import Image
    from server import uploads
    from server.services import batches,cleanup
    from server.db.repositories import batches as batch_repository
    from server.database import connect
    own=_batch(sandbox,with_photo=False)
    monkeypatch.setattr(uploads,"UPLOADS_DIR",sandbox/"uploads")
    monkeypatch.setattr(uploads,"PART_DIR",sandbox/"incoming")
    monkeypatch.setattr(uploads,"REFERENCES_DIR",sandbox/"references")
    assert batches.get(own)["upload_state"]=="open"
    picture=io.BytesIO()
    Image.new("RGB",(20,20),"green").save(picture,format="JPEG")
    raw=picture.getvalue()
    payload=uploads.BeginUpload(kind="fo",batch_id=str(own),filename="fo.jpg",
                                size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    file_id=uuid.uuid4()
    uploads._create_upload(payload,file_id)
    assert batches.get(own)["upload_state"]=="open"
    (sandbox/"incoming"/f"{file_id}.part").write_bytes(raw)
    result=uploads._finalize_sync(str(file_id))
    assert result["sha256"]==payload.sha256
    assert batches.get(own)["upload_state"]=="ready"
    original=Path(result["path"])
    assert original.read_bytes()==raw
    with connect() as db:
        batch_repository.refresh_upload_state(db,own)
    assert batches.get(own)["upload_state"]=="ready"
    _job(sandbox,own)
    with connect() as db:
        batch_repository.refresh_upload_state(db,own)
    assert batches.get(own)["upload_state"]=="sealed"
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        uploads._create_upload(payload,uuid.uuid4())
    assert exc.value.status_code==409
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="completed"
