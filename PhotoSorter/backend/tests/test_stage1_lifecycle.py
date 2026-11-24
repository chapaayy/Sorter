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
from .asgi_response import response_bytes

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
    from app import config
    monkeypatch.setattr(config,"APP_STORAGE_ROOT",tmp_path/"storage/app")
    config.APP_STORAGE_ROOT.mkdir(parents=True)
    for folder in ("uploads","outputs","incoming","references","runs"):
        (data/folder).mkdir(parents=True)
    monkeypatch.setattr(cleanup,"DATA_DIR",data)
    monkeypatch.setattr(cleanup,"RUNS_DIR",data/"runs")
    monkeypatch.setattr(batches,"DATA_DIR",data)
    monkeypatch.setattr(retention,"DATA_DIR",data)
    monkeypatch.setattr(images,"DATA_DIR",data)
    monkeypatch.setattr(repository,"RUNS_DIR",data/"runs")
    return data

def owner_for_test(db):
    return db.execute("""INSERT INTO users(username,access_role) VALUES ('admin','owner')
        ON CONFLICT(username) DO UPDATE SET access_role='owner' RETURNING id""").fetchone()["id"]

def _batch(data,with_photo=True):
    from server.services import batches
    from server.database import connect
    with connect() as db:
        owner_id=owner_for_test(db)
    ident=uuid.UUID(batches.create("Тестовая партия",owner_id=owner_id)["batch_id"])
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

def test_historical_additive_migrations_and_v2_rejects_unowned_rows(db,tmp_path,monkeypatch):
    import psycopg
    from server.database import DB_URL,SCHEMA
    from server.db.migration_runner import migrate,MIGRATIONS
    import shutil
    from server.db import migration_runner
    for file in MIGRATIONS.glob('*.sql'):
        if file.name != '0037_batch_ownership.sql':
            shutil.copy2(file,tmp_path/file.name)
    monkeypatch.setattr(migration_runner,'MIGRATIONS',tmp_path)
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
                file.name for file in tmp_path.glob("*.sql")}
            assert conn.execute("SELECT id FROM batches WHERE id=%s",(old,)).fetchone()[0]==old
            monkeypatch.setattr(migration_runner,"MIGRATIONS",MIGRATIONS)
            with pytest.raises(psycopg.errors.NotNullViolation):
                with conn.transaction():
                    migrate(conn)
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
        target=paths.result_media_dir(run)/"SAM-0001"/"photo.jpg"
        target.parent.mkdir(parents=True)
        os.link(source,target)
        run_folder=sandbox/"runs"/run
        run_folder.mkdir()
        (run_folder/"run.json").write_text("{}",encoding="utf8")
        zip_dir=paths.run_dir(run)/".archives"
        zip_dir.mkdir()
        (zip_dir/"ready.zip").write_bytes(b"completed ZIP")
    assert cleanup.request(own)["state"]=="deleting"
    assert cleanup.cleanup_one(own)=="completed"
    assert not paths.batch_dir(own).exists()
    assert not (paths.batch_root(own)/"results").exists()
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
    assert cleanup.get_status(own)["task"]["progress"]["phase"]=="queued"
    with connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=%s",(queued,)).fetchone()["status"]=="stopped"
        assert db.execute("SELECT status FROM jobs WHERE id=%s",(running,)).fetchone()["status"]=="stopping"
    assert cleanup.cleanup_one(own)=="waiting"
    assert cleanup.get_status(own)["task"]["progress"]["phase"]=="stopping_jobs"
    with connect() as db:
        db.execute("UPDATE jobs SET status='stopped' WHERE id=%s",(running,))
    assert cleanup.cleanup_one(own)=="waiting"
    assert cleanup.get_status(own)["task"]["progress"]["phase"]=="waiting_operations"
    operations.finish(lease)
    assert cleanup.cleanup_one(own)=="completed"

def test_cleanup_exposes_committed_file_counts_and_database_phase(sandbox,monkeypatch):
    from server.services import batches,cleanup
    own=_batch(sandbox)
    original=paths.batch_dir(own)
    (original/"second.jpg").write_bytes(b"photo")
    external=sandbox/"outside.jpg"
    external.write_bytes(b"keep")
    (original/"link.jpg").symlink_to(external)
    observed=[]
    real_reporter=cleanup._reporter

    def track(db,batch_id):
        real_report=real_reporter(db,batch_id)
        def report(phase,done,total):
            real_report(phase,done,total)
            if phase=="files":
                observed.append((done,total,len(list(original.iterdir())) if original.exists() else None))
                if done in (0,1,total-1):
                    assert cleanup.get_status(own)["task"]["progress"]=={
                        "phase":"files","done":done,"total":total}
            if phase=="database":
                state=batches.get(own)
                assert state["delete_state"]=="deleting"
                assert state["deletion_progress"]=={"phase":"database","done":total-1,"total":total}
                assert next(b for b in batches.list_all()["batches"] if b["batch_id"]==str(own))["deletion_progress"]==state["deletion_progress"]
                assert cleanup.request(own)["state"]=="deleting"
                assert cleanup.get_status(own)["task"]["progress"]==state["deletion_progress"]
        return report
    monkeypatch.setattr(cleanup,"_reporter",track)
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="completed"
    assert observed==[(0,5,3),(1,5,2),(2,5,1),(3,5,0),(4,5,None)]
    assert cleanup.get_status(own)["task"]["progress"]=={"phase":"completed","done":5,"total":5}
    assert external.read_bytes()==b"keep"

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
        return original(*args)
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
    directory=paths.result_metadata_dir(run)
    directory.mkdir(parents=True)
    (directory/"manifest.rows.jsonl").write_text("",encoding="utf8")
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
    target=paths.result_media_dir(run)/"SAM-0045"/"photo.jpg"
    target.parent.mkdir(parents=True)
    os.link(source,target)
    from app.results.exporter import export
    export(paths.result_metadata_dir(run),[{
        "query":str(source),"copy":str(target),"assigned_sam":"SAM-0045","top":[]
    }])
    with connect() as db:
        archive_day=db.execute("""SELECT (COALESCE(started_at,created_at) AT TIME ZONE 'Europe/Samara')::date AS day
            FROM jobs WHERE id=%s""",(run,)).fetchone()['day'].isoformat()
    response=download_results(run)
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="waiting"
    body=asyncio.run(response_bytes(response))
    assert response.stat_result is None or response.stat_result.st_size==len(body)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        member=f"Тестовая партия/SAM-0045/{archive_day}/Неназначена сторона/test.jpg"
        assert archive.namelist()==[member]
        assert archive.read(member)==source.read_bytes()
    assert cleanup.cleanup_one(own)=="completed"

def test_retention_due_guard_cannot_delete_after_new_run(sandbox):
    from server.services import cleanup,retention
    from server.database import connect
    own=_batch(sandbox)
    run=_job(sandbox,own)
    directory=paths.result_metadata_dir(run)
    directory.mkdir(parents=True)
    (directory/"manifest.rows.jsonl").write_text("",encoding="utf8")
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


def test_short_retention_can_be_assigned_only_after_completed_zip(sandbox):
    from server.services import retention,cleanup
    from server.database import connect
    own=_batch(sandbox)
    original=retention.settings()
    try:
        assert retention.update_settings(True,3,"minutes")["unit"]=="minutes"
        with connect() as db:
            retention.schedule(db,own,"20261107T120000-abcdef123456")
        row=retention.status(own)
        assert row["delete_after_at"] is not None
        assert row["download_confirmed_at"] is None
        with connect() as db:
            diff=db.execute("""SELECT extract(epoch from (delete_after_at-now())) AS seconds
                FROM batches WHERE id=%s""",(own,)).fetchone()["seconds"]
        assert 170<float(diff)<=180
    finally:
        retention.update_settings(original["enabled"],original["value"],original["unit"])
        cleanup.request(own)
        cleanup.cleanup_one(own)


def test_disabled_retention_does_not_assign_deadline(sandbox):
    from server.services import retention,cleanup
    from server.database import connect
    own=_batch(sandbox)
    original=retention.settings()
    try:
        retention.update_settings(False,1,"minutes")
        with connect() as db:
            retention.schedule(db,own,"20261107T120000-abcdef123456")
        assert retention.status(own)["delete_after_at"] is None
    finally:
        retention.update_settings(original["enabled"],original["value"],original["unit"])
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
    own=_batch(sandbox,with_photo=False)
    run=_job(sandbox,own)
    source=paths.batch_dir(own)/"source.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"exact immutable pixels")
    original=sha256(source)
    stamp=(source.stat().st_size,source.stat().st_mtime_ns)
    rows=[{"query":str(source),"top":[{"label":"SAM-0045","score":0.95,
            "reference":"sample.jpg"}],"group_id":"G0001"}]
    saved=repository.save_model({"id":run,"batch_id":str(own)},
            "megaloc",rows,query_stamps={str(source):stamp})
    copy=Path(saved[0]["copy"])
    assert copy.exists() and copy.stat().st_ino==source.stat().st_ino
    assert sha256(source)==original
    assert (paths.result_metadata_dir(run)/"manifest.rows.jsonl").is_file()
    assert not (paths.result_metadata_dir(run)/"manifest.json").exists()
    assert not (paths.result_metadata_dir(run)/"manifest.csv").exists()
    assert not (sandbox/"runs"/run/"models").exists()
    reloaded=repository.load_model(run,"megaloc")
    assert reloaded[0]["assigned_sam"]=="SAM-0045"
    assert reloaded[0]["score"]==0.95
    assert reloaded[0]["copy"]==str(copy)
    from app.storage.paths import managed_path
    from app.storage.categories import Category
    assert not managed_path(Category.PROCESSING_STAGING,run_id=run).exists()
    with pytest.raises(FileExistsError):
        repository.save_model({"id":run,"batch_id":str(own)},
            "megaloc",rows,query_stamps={str(source):stamp})
    assert sha256(copy)==original

def test_export_crash_does_not_publish_partial_result(sandbox,monkeypatch):
    from app.results import repository
    own=_batch(sandbox,with_photo=False)
    run=_job(sandbox,own)
    source=paths.batch_dir(own)/"first.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"first")
    second=source.parent/"second.jpg"
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
        repository.save_model({"id":run,"batch_id":str(own)},
                              "megaloc",rows)
    assert not paths.run_dir(run).exists()
    from app.storage.paths import managed_path
    from app.storage.categories import Category
    assert not managed_path(Category.PROCESSING_STAGING,run_id=run).exists()
    assert source.read_bytes()==b"first"
    assert second.read_bytes()==b"second"

def test_cannot_reconfirm_old_zip_after_a_newer_run(sandbox):
    from server.services import retention,cleanup
    from server.database import connect
    from fastapi import HTTPException
    own=_batch(sandbox)
    old=_job(sandbox,own)
    olddir=paths.result_metadata_dir(old)
    olddir.mkdir(parents=True)
    (olddir/"manifest.rows.jsonl").write_text("",encoding="utf8")
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
    from app.storage.paths import managed_path
    from app.storage.categories import Category
    folder1=managed_path(Category.PROCESSING_STAGING,run_id=finished)
    folder2=managed_path(Category.PROCESSING_STAGING,run_id=running)
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
    batchfolder.parent.mkdir(parents=True)
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
    assert batches.get(own)["upload_state"]=="open"
    picture=io.BytesIO()
    Image.new("RGB",(20,20),"green").save(picture,format="JPEG")
    raw=picture.getvalue()
    payload=uploads.BeginUpload(kind="fo",batch_id=str(own),filename="fo.jpg",
                                size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    file_id=uuid.uuid4()
    uploads._create_upload(payload,file_id)
    assert batches.get(own)["upload_state"]=="open"
    paths.part_path(own,file_id).write_bytes(raw)
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


def test_result_export_refuses_other_owner_even_with_valid_file(sandbox):
    from app.results import repository
    from server.database import connect
    own=_batch(sandbox)
    other=_batch(sandbox)
    with connect() as db:
        second=db.execute("INSERT INTO users(username,access_role) VALUES (%s,'viewer') RETURNING id",
                          ("isolation-"+uuid.uuid4().hex,)).fetchone()["id"]
        db.execute("UPDATE batches SET owner_id=%s WHERE id=%s",(second,other))
    # Put a file in the second user's actual directory, not in the first owner's.
    alien=paths.batch_dir(other)/"private.jpg"
    alien.parent.mkdir(parents=True,exist_ok=True)
    alien.write_bytes(b"private")
    run=_job(sandbox,own)
    with pytest.raises(ValueError,match="outside owned storage"):
        repository.save_model({"id":run,"batch_id":str(own)},"megaloc",[{"query":str(alien),"top":[]}])
    assert not paths.run_dir(run).exists()
    assert alien.read_bytes()==b"private"
