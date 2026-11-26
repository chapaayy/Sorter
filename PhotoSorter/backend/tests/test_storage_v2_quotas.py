"""Stage 9: real PostgreSQL receipts, inode accounting and concurrent admission."""
import asyncio
import concurrent.futures
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
import pytest
from fastapi import HTTPException
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_path
from server import database,uploads
from server.storage import admission
from server.storage.reservations import reservation
from server.services import cleanup,archives
from .test_unified_queue_stage3 import system
from .test_stage1_lifecycle import _batch,_job
from .test_stage2_platform import _jpg
from .test_batch_media import clips
from .test_storage_v2_admin import clients
from .accounting_checks import settle,exact

def policy(enabled=True,temp=None,disk=None):
    return {"personal_enabled":enabled,"temporary_limit_bytes":temp,"disk_reserve_bytes":disk}

def owner_of(batch):
    with database.connect() as db:
        return db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch,)).fetchone()["owner_id"]

def budget(owner):
    with database.connect() as db:return admission.account_budget(db,owner)

def begin(batch,raw,name="photo.jpg"):
    uid=uuid.uuid4()
    uploads._create_upload(uploads.BeginUpload(kind="fo",filename=name,batch_id=str(batch),size=len(raw)),uid)
    return uid

def chunk(batch,uid,raw,offset,end):
    actual=uploads._append_chunk(uploads.part_path(batch,uid),offset,raw[offset:end],len(raw))
    uploads._record_chunk(uid,actual)
    assert actual==end

def finish(batch,uid,raw,offset=0):
    chunk(batch,uid,raw,offset,len(raw))
    return Path(uploads._finalize_sync(str(uid))["path"])

def test_concurrent_personal_admission_resume_dedup_and_disable(system):
    first=_batch(system,with_photo=False)
    owner=owner_of(first)
    second=uuid.uuid4()
    with database.connect() as db:
        other=db.execute("INSERT INTO users(username,access_role) VALUES (%s,'viewer') RETURNING id",("other-"+uuid.uuid4().hex,)).fetchone()["id"]
        db.execute("INSERT INTO batches(id,display_name,owner_id) VALUES(%s,'Other',%s)",(second,other))
    raw=_jpg()+b"\0"*8192
    unit=admission.rounded(len(raw))
    settle()
    admission.set_account(owner,2*unit)
    admission.set_account(other,unit)
    admission.configure(policy())
    barrier=threading.Barrier(4)
    def attempt(i):
        barrier.wait(timeout=10)
        try:return begin(first,raw,f"{i}.jpg")
        except HTTPException as exc:
            assert exc.status_code==507 and "личной квоте" in exc.detail
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        accepted=[uid for uid in pool.map(attempt,range(4)) if uid]
    assert len(accepted)==2
    assert budget(owner)["reserved_bytes"]==2*unit
    other_uid=begin(second,raw)
    assert budget(other)["reserved_bytes"]==unit
    offset=4096
    chunk(first,accepted[0],raw,0,offset)
    assert budget(owner)["reserved_bytes"]==2*unit
    admission.set_account(owner,0)
    assert budget(owner)["state"]=="exceeded"
    paths=[finish(first,accepted[0],raw,offset),finish(first,accepted[1],raw)]
    independent=finish(second,other_uid,raw)
    settle()
    assert paths[0].stat().st_ino==paths[1].stat().st_ino!=independent.stat().st_ino
    assert budget(owner)["used_bytes"]==max(len(raw),paths[0].stat().st_blocks*512)
    assert budget(owner)["reserved_bytes"]==0
    assert budget(other)["used_bytes"]==max(len(raw),independent.stat().st_blocks*512)
    with pytest.raises(HTTPException,match="личной квоте"):begin(first,raw)
    admission.configure(policy(False))
    uid=begin(first,raw)
    asyncio.run(uploads.cancel_upload(str(uid)))
    assert budget(owner)["reserved_bytes"]==0
    admission.configure(policy())
    cleanup.request(first)
    assert cleanup.cleanup_one(first)=="completed"
    settle()
    assert budget(owner)["used_bytes"]==0 and independent.exists()
    admission.set_account(owner,None)
    assert budget(owner)["state"]=="unlimited"

def test_temporary_concurrency_and_disk_reserve(system,monkeypatch):
    from server.services import disk_guard
    settle()
    unit=1024*1024
    admission.configure(policy(temp=2*unit))
    barrier=threading.Barrier(4)
    release=threading.Event()
    entered=[]
    mutex=threading.Lock()
    def contender():
        barrier.wait(timeout=10)
        try:
            with reservation("test",unit):
                with mutex:entered.append(True)
                assert release.wait(timeout=15)
        except HTTPException as exc:
            assert exc.status_code==507 and "временном" in exc.detail
            with mutex:entered.append(False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(contender) for _ in range(4)]
        try:
            import time
            deadline=time.monotonic()+10
            while len(entered)<4 and time.monotonic()<deadline:time.sleep(.02)
            assert entered.count(True)==2 and entered.count(False)==2
            assert admission.status()["temporary"]["reserved_bytes"]==2*unit
            admission.configure(policy(temp=0))
            with pytest.raises(HTTPException,match="временном"):
                with reservation("test",unit):pass
        finally:release.set()
        for f in futures:f.result(timeout=15)
    assert admission.status()["temporary"]["reserved_bytes"]==0
    admission.configure(policy(False))
    monkeypatch.setattr(disk_guard,"stat",lambda *a:(200*1024**3,21*1024**3))
    admission.configure(policy(False,disk=20*1024**3))
    with reservation("test",1024**3):
        with pytest.raises(HTTPException,match="диске"):
            with reservation("test",unit):pass
    admission.configure(policy(False,disk=0))
    assert admission.status()["disk"]["minimum_bytes"]==disk_guard.reserve(200*1024**3)

def test_tracked_crash_handoff_and_active_cleanup_protection(system):
    from app.storage.temporary import collect_abandoned
    settle()
    cap=1024*1024
    admission.configure(policy(temp=cap))
    script="""import sys
from app import config
from app.storage.temporary import temporary_operation
from server.storage.reservations import reservation
with temporary_operation(config.APP_STORAGE_ROOT,'worker') as directory:
    with reservation('archive',1048576,work=directory,tree=True):
        p=directory/'fragment'
        p.write_bytes(b'x'*131072)
        print(p,flush=True)
        sys.stdin.readline()
"""
    env=dict(os.environ,DATABASE_URL=database.DB_URL,MAP_APP_STORAGE_ROOT=str(config.APP_STORAGE_ROOT))
    proc=subprocess.Popen([sys.executable,"-c",script],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        path=Path(proc.stdout.readline().strip())
        assert path.is_file()
        settle()
        tmp=admission.status()["temporary"]
        assert tmp["used_bytes"]==path.stat().st_blocks*512
        assert tmp["used_bytes"]+tmp["reserved_bytes"]==cap
        assert collect_abandoned(config.APP_STORAGE_ROOT,grace_seconds=0)==0
        with pytest.raises(HTTPException,match="временном"):
            with reservation("test",4096):pass
        proc.kill();proc.wait(timeout=10)
        settle()
        tmp=admission.status()["temporary"]
        assert tmp["reserved_bytes"]==0 and tmp["used_bytes"]>0
        assert collect_abandoned(config.APP_STORAGE_ROOT,grace_seconds=0)==1
        settle()
        assert admission.status()["temporary"]["used_bytes"]==0
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=10)

def test_zip_rejection_before_write_and_personal_exclusion(system):
    batch=_batch(system)
    run=_job(system,batch)
    owner=owner_of(batch)
    media=managed_path(Category.RESULT_MEDIA,user_id=owner,batch_uuid=batch,run_id=run)/"large.jpg"
    media.parent.mkdir(parents=True)
    with media.open("wb") as f:f.truncate(64*1024**2)
    settle()
    admission.set_account(owner,0)
    admission.configure(policy(temp=2*1024**2))
    with pytest.raises(HTTPException,match="временном"):
        archives.prepare(run,None,[(media,"large.jpg")])
    assert not list(archives.archive_folder(run).glob("*.zip"))
    assert not list(archives.archive_folder(run).glob("*.tmp"))
    media.write_bytes(_jpg())
    settle()
    before=budget(owner)["used_bytes"]
    result=archives.prepare(run,None,[(media,"large.jpg")])
    assert result.is_file() and budget(owner)["used_bytes"]==before
    assert admission.status()["temporary"]["reserved_bytes"]==0
    admission.configure(policy(temp=0))
    assert archives.prepare(run,None,[(media,"large.jpg")])==result
    assert result.exists()

def test_owner_only_limits_validation_and_stale_disable(system,monkeypatch):
    owner,viewer,public=clients(monkeypatch)
    url="/api/storage/limits"
    assert owner.get(url).json()["policy"]==policy(False)
    assert owner.patch(url,json=policy()).status_code==409
    settle()
    assert viewer.patch(url,json=policy()).status_code==403
    assert public.patch(url,json=policy()).status_code==401
    assert owner.patch(url,json=policy(),headers={"Origin":"https://evil.example"}).status_code==403
    assert owner.patch(url,json={**policy(),"personal_enabled":"true"}).status_code==422
    assert owner.patch(url,json=policy(temp=2**63-1)).status_code==422
    assert owner.patch(url,json=policy(temp=1024**2)).status_code==200
    account=owner_of(_batch(system,with_photo=False))
    path=f"/api/storage/accounts/{account}/limit"
    assert viewer.patch(path,json={"limit_bytes":0}).status_code==403
    assert owner.patch(path,json={"limit_bytes":0}).json()["limit_bytes"]==0
    with database.connect() as db:db.execute("UPDATE storage_accounting_state SET sampled_at=now()-interval '2 minutes'")
    assert owner.patch(url,json=policy(False)).status_code==200
    assert owner.patch(path,json={"limit_bytes":None}).json()["state"]=="unlimited"

def test_real_transcode_admission_and_preserve_original(system,clips):
    from server.db.repositories import work_queue
    from server.workers import media_prepare
    from .test_batch_media import _import
    from io import BytesIO
    from PIL import Image
    raw=clips[1].read_bytes()
    batch=_batch(system,with_photo=False)
    owner=owner_of(batch)
    saved=_import(system,batch,[("clip.mov",raw)])
    settle()
    original=Path(saved[0][1]["path"])
    before=budget(owner)["used_bytes"]
    admission.set_account(owner,before+32*1024**2)
    admission.configure(policy(temp=32*1024**2))
    with database.connect() as db:item=work_queue.claim_next(db)
    assert item["kind"]=="media_preparation"
    media_prepare.run(item,stopping=lambda:False)
    with database.connect() as db:
        row=db.execute("SELECT media_output_path,media_error FROM uploads WHERE batch_id=%s",(batch,)).fetchone()
    assert row["media_error"] is None and row["media_output_path"]
    out=Path(row["media_output_path"])
    assert out.exists() and original.read_bytes()==raw
    settle()
    assert budget(owner)["used_bytes"]==before+max(out.stat().st_size,out.stat().st_blocks*512)
    assert budget(owner)["reserved_bytes"]==0
    second=_batch(system,with_photo=False)
    photo=BytesIO()
    Image.new("RGB",(64,32),"red").save(photo,format="PNG")
    saved=_import(system,second,[("photo.png",photo.getvalue())])
    settle()
    admission.set_account(owner,budget(owner)["used_bytes"])
    with database.connect() as db:item=work_queue.claim_next(db)
    assert item["kind"]=="media_preparation"
    media_prepare.run(item,stopping=lambda:False)
    with database.connect() as db:
        row=db.execute("SELECT media_output_path,media_error FROM uploads WHERE batch_id=%s",(second,)).fetchone()
    assert row["media_output_path"] is None and "личной квоте" in row["media_error"]
    assert Path(saved[0][1]["path"]).read_bytes()==photo.getvalue()
    assert budget(owner)["reserved_bytes"]==0


def test_live_writer_survives_database_session_loss(system):
    from server.storage.reservations import recover
    settle()
    unit=1024**2
    admission.configure(policy(temp=unit))
    with reservation("live",unit) as lease:
        with database.connect() as db:
            row=db.execute("SELECT lease_key FROM storage_reservations WHERE id=%s",(lease.token,)).fetchone()
            key=row["lease_key"]
            pid=db.execute("""SELECT pid FROM pg_locks WHERE locktype='advisory' AND granted
                AND classid=%s::oid AND objid=%s::oid AND objsubid=1""",
                (key>>32,key&0xffffffff)).fetchone()["pid"]
            assert db.execute("SELECT pg_terminate_backend(%s,5000) AS ok",(pid,)).fetchone()["ok"]
        with database.connect() as db:
            recover(db)
            assert db.execute("SELECT 1 FROM storage_reservations WHERE id=%s",(lease.token,)).fetchone()
        with pytest.raises(HTTPException,match="временном"):
            with reservation("other",4096):pass
    assert admission.status()["temporary"]["reserved_bytes"]==0
