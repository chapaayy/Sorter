"""Actual filesystem and PostgreSQL integration; no fake accounting rows."""
import concurrent.futures
import hashlib
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from app import config
from app.storage.categories import Category
from app.storage.paths import managed_path,managed_prefix
from server import database,uploads
from server.storage import registry,reporting
from server.storage.reconciliation import Reconciler
from server.services import cleanup,upload_manifest
from .test_unified_queue_stage3 import system
from .test_stage1_lifecycle import _batch
from .test_stage2_platform import _jpg
from .test_upload_manifest import File
from .accounting_checks import settle,observed,exact

def test_parallel_resumable_uploads_hardlinks_owners_and_missing(system):
    raw=_jpg()
    first=_batch(system,with_photo=False)
    second=uuid.uuid4()
    with database.connect() as db:
        owner=db.execute("SELECT owner_id FROM batches WHERE id=%s",(first,)).fetchone()["owner_id"]
        other=db.execute("INSERT INTO users(username,access_role) VALUES (%s,'viewer') RETURNING id",("accounting-"+uuid.uuid4().hex,)).fetchone()["id"]
        db.execute("INSERT INTO batches(id,display_name,owner_id) VALUES (%s,'Second owner',%s)",(second,other))
    items=[(first,File(uuid.uuid4(),f"one/{i}.jpg",len(raw))) for i in range(2)]+[(second,File(uuid.uuid4(),"two/3.jpg",len(raw)))]
    for batch in (first,second):
        upload_manifest.register(batch,[f for bid,f in items if bid==batch])
    def begin(pair):
        batch,f=pair
        uploads._create_upload(uploads.BeginUpload(kind="fo",filename=f.filename,batch_id=str(batch),size=len(raw)),f.upload_id)
        p=uploads.part_path(batch,f.upload_id)
        end=uploads._append_chunk(p,0,raw[:len(raw)//2],len(raw))
        uploads._record_chunk(f.upload_id,end)
        return p,end
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        parts=list(pool.map(begin,items))
    r=Reconciler()
    try:
        data=settle(r)
        for p,end in parts:
            row=exact(p)
            assert row["category"]=="fo_upload_part" and row["logical_bytes"]==end
            assert row["charged_bytes"]==0
        assert data["unfinished_fo"]["files"]==3
        def finish(pair):
            (batch,f),(p,end)=pair
            confirmed=uploads._append_chunk(p,end,raw[end:],len(raw))
            uploads._record_chunk(f.upload_id,confirmed)
            return Path(uploads._finalize_sync(str(f.upload_id))["path"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            paths=list(pool.map(finish,zip(items,parts)))
        data=settle(r)
        assert paths[0].stat().st_ino==paths[1].stat().st_ino
        assert paths[0].stat().st_ino!=paths[2].stat().st_ino
        block=paths[0].stat().st_blocks*512
        assert data["owners"][str(owner)]["allocated_bytes"]==block
        assert data["owners"][str(owner)]["logical_bytes"]==2*len(raw)
        assert data["owners"][str(owner)]["charged_bytes"]==max(block,len(raw))
        assert data["owners"][str(other)]["allocated_bytes"]==paths[2].stat().st_blocks*512
        assert data["unfinished_fo"]["files"]==0
        assert all(observed(p) is None for p,_ in parts)
        assert sum(exact(p)["physical_bytes"] for p in paths[:2])==block
        # Out-of-band unlink: no notification; a new generation must find it.
        paths[0].unlink()
        unknown=config.APP_STORAGE_ROOT/"unmanaged.bin"
        unknown.write_bytes(b"do not delete")
        data=settle()
        assert observed(paths[0]) is None
        assert exact(unknown)["category"]=="unknown"
        assert data["missing_expected"]>=1
        assert any(x["path"]==registry.key_for(paths[0]) for x in reporting.issues()["missing"])
        assert unknown.read_bytes()==b"do not delete"
        cleanup.request(first)
        assert cleanup.cleanup_one(first)=="completed"
        data=settle()
        assert str(owner) not in data["owners"]
        assert exact(paths[2])["owner_id"]==other
        assert unknown.exists()
    finally:r.close()

def test_crashed_writer_reservation_and_abandoned_scratch(system):
    from app.storage.temporary import collect_abandoned
    from app.storage.changes import changed
    script="""import sys
from app import config
from app.storage.temporary import temporary_operation
from server.storage.reservations import reservation
with reservation('archive',1048576),temporary_operation(config.APP_STORAGE_ROOT,'worker') as directory:
    p=directory/'fragment'
    with p.open('wb') as stream:
        stream.write(b'x'*131072)
        stream.flush()
        print(p,flush=True)
        sys.stdin.readline()
"""
    env=dict(os.environ,DATABASE_URL=database.DB_URL,MAP_APP_STORAGE_ROOT=str(config.APP_STORAGE_ROOT))
    p=subprocess.Popen([sys.executable,"-c",script],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        path=Path(p.stdout.readline().strip())
        assert path.is_file() and path.is_relative_to(config.APP_STORAGE_ROOT)
        data=settle()
        assert data["reserved_bytes"]==1048576
        assert any(row["operation_key"]==registry.key_for(path.parent) and row["logical_bytes"]>=131072
                   for row in data["temporary_operations"]["rows"])
        assert exact(path)["logical_bytes"]==131072
        assert data["temporary"]["allocated_bytes"]>=path.stat().st_blocks*512
        assert collect_abandoned(config.APP_STORAGE_ROOT,grace_seconds=0)==0
        p.kill();p.wait(timeout=10)
        for _ in range(20):
            data=settle()
            if not data["reserved_bytes"]:break
            time.sleep(.1)
        assert data["reserved_bytes"]==0
        assert path.exists()
        assert collect_abandoned(config.APP_STORAGE_ROOT,grace_seconds=0)==1
        data=settle()
        assert observed(path) is None and not path.exists()
        assert data["temporary_peak_bytes"]>=131072
    finally:
        if p.poll() is None:p.kill();p.wait(timeout=10)

def test_bounded_reconciliation_sparse_and_links_no_polling_walk(system,monkeypatch):
    root=config.APP_STORAGE_ROOT
    folder=managed_prefix(Category.TECHNICAL_CACHE,provider="torch")/"accounting-fixture"
    folder.mkdir(parents=True)
    base=folder/"sparse"
    with base.open("wb") as stream:
        stream.seek(64*1024*1024-1);stream.write(b"x")
    for i in range(2300):os.link(base,folder/str(i))
    started=time.perf_counter()
    r=Reconciler()
    try:
        assert r.tick(limit=128)
        assert r.busy
        data=settle(r)
        row=data["categories"]["technical_cache"]
        assert row["files"]==2301
        assert row["logical_bytes"]==2301*base.stat().st_size
        assert row["allocated_bytes"]==base.stat().st_blocks*512
        assert row["hardlink_paths"]==2300
        print("STAGE7_ACCOUNTING_FIXTURE",{"paths":row["files"],"logical_bytes":row["logical_bytes"],
              "allocated_bytes":row["allocated_bytes"],"elapsed_seconds":round(time.perf_counter()-started,3)})
        from server.services import storage_usage,storage_breakdown,storage_inventory
        def forbidden(*args,**kwargs):raise AssertionError("HTTP must not scan disk")
        with monkeypatch.context() as patch:
            patch.setattr(os,"walk",forbidden)
            patch.setattr(os,"scandir",forbidden)
            assert storage_usage.usage()
            assert storage_breakdown.breakdown()
            assert storage_inventory.scan()
    finally:r.close()

def test_reservation_recovery_advances_past_active_leases(system):
    from server.storage.reservations import recover
    ids=[uuid.UUID(int=i) for i in (1,2,3)]
    keys=[900001,900002,900003]
    with database.connect() as holder:
        for key in keys[:2]:
            holder.execute("SELECT pg_advisory_lock(%s)",(key,))
        with database.connect() as db:
            for ident,key in zip(ids,keys):
                db.execute("INSERT INTO storage_reservations(id,kind,lease_key,requested_bytes) VALUES(%s,'fixture',%s,100)",(ident,key))
        with database.connect() as db:
            after=recover(db,limit=2)
            assert after==ids[1]
        with database.connect() as db:
            assert recover(db,limit=2,after=after) is None
            assert [r["id"] for r in db.execute("SELECT id FROM storage_reservations ORDER BY id")]==ids[:2]
    with database.connect() as db:
        recover(db,limit=10)
        assert db.execute("SELECT count(*) AS n FROM storage_reservations").fetchone()["n"]==0

def test_missing_published_manifest_and_stale_snapshot(system):
    from app.results.exporter import MANIFEST_NAME
    from psycopg.types.json import Jsonb
    from .test_stage1_lifecycle import _job
    from server.storage.accounting import snapshot
    batch=_batch(system)
    run=_job(system,batch)
    with database.connect() as db:
        owner=db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch,)).fetchone()["owner_id"]
        db.execute("UPDATE jobs SET snapshot=%s WHERE id=%s",(Jsonb({"models":{"megaloc":{"status":"completed"}}}),run))
    manifest=managed_path(Category.RESULT_METADATA,user_id=owner,batch_uuid=batch,run_id=run)/MANIFEST_NAME
    manifest.parent.mkdir(parents=True)
    import json
    media=managed_path(Category.RESULT_MEDIA,user_id=owner,batch_uuid=batch,run_id=run)/"SAM 0001"/"фото.jpg"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"media")
    manifest.write_text(json.dumps({"index":0,"copy":"SAM 0001/фото.jpg"})+"\n",encoding="utf8")
    data=settle()
    key=registry.key_for(manifest)
    media_key=registry.key_for(media)
    assert not any(row["path"] in (key,media_key) for row in reporting.issues()["missing"])
    media.unlink()
    data=settle()
    assert data["issues"]["missing_result_media"]==1
    assert any(row["path"]==media_key for row in reporting.issues()["missing"])
    media.write_bytes(b"media")
    data=settle()
    assert not any(row["path"]==media_key for row in reporting.issues()["missing"])
    assert "missing_result_media" not in data["issues"]
    manifest.write_text(json.dumps({"index":0,"copy":"../escape.jpg"})+"\n",encoding="utf8")
    data=settle()
    assert data["issues"]["invalid_result_manifest"]==1
    manifest.unlink()
    data=settle()
    assert data["missing_expected"]>=1
    assert any(row["path"]==key for row in reporting.issues()["missing"])
    with database.connect() as db:
        db.execute("UPDATE storage_accounting_state SET sampled_at=now()-interval '2 minutes'")
    assert snapshot()["stale"] and snapshot()["partial"]
