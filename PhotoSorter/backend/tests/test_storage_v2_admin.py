"""Real PostgreSQL/files and real owner/viewer HTTP sessions for stage 8."""
import os,time,uuid
from pathlib import Path
from fastapi.testclient import TestClient
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_path
from server import auth,database
from server.main import app
from server.security.login_throttle import LoginThrottle
from server.services import admin_users,storage_admin,storage_maintenance,archive_cache
from server.storage.reconciliation import Reconciler
from .test_unified_queue_stage3 import system
from .test_stage1_lifecycle import _batch,_job
from .accounting_checks import settle

def clients(monkeypatch):
    origin="https://storage.example.test"
    password="disposable_storage_password"
    monkeypatch.setenv("DOMAIN","storage.example.test")
    monkeypatch.setenv("ADMIN_PASSWORD",password)
    monkeypatch.setattr(auth,"limiter",LoginThrottle())
    auth.bootstrap_admin()
    admin_users.create("viewer@example.test",password,password,[])
    owner=TestClient(app,base_url=origin,headers={"Origin":origin})
    viewer=TestClient(app,base_url=origin,headers={"Origin":origin})
    public=TestClient(app,base_url=origin,headers={"Origin":origin})
    for client,name in ((owner,"admin"),(viewer,"viewer@example.test")):
        assert client.post("/api/auth/login",json={"username":name,"password":password}).status_code==200
    return owner,viewer,public

def test_owner_reports_global_hardlink_attribution_and_paginated_batches(system,monkeypatch):
    owner,viewer,public=clients(monkeypatch)
    initial=owner.get("/api/storage/accounts").json()
    assert initial["sampled_at"] is None
    assert all(r["usage"] is None for r in initial["rows"])
    batch=_batch(system)
    run=_job(system,batch)
    with database.connect() as db:
        row=db.execute("SELECT id,target_path FROM uploads WHERE batch_id=%s",(batch,)).fetchone()
        user=db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch,)).fetchone()["owner_id"]
        for i in range(30):
            db.execute("INSERT INTO batches(id,display_name,owner_id) VALUES(%s,%s,%s)",(uuid.uuid4(),str(i),user))
    source=Path(row["target_path"])
    media=managed_path(Category.RESULT_MEDIA,user_id=user,batch_uuid=batch,run_id=run)/"one.jpg"
    media.parent.mkdir(parents=True)
    os.link(source,media)
    data=settle()
    def no_scan(*args,**kwargs):raise AssertionError("HTTP projections must not enumerate the filesystem")
    with monkeypatch.context() as patch:
        patch.setattr(os,"walk",no_scan)
        patch.setattr(os,"scandir",no_scan)
        rows=storage_admin.accounts()
        detail=storage_admin.account_detail(user,0,25)
        operational=storage_admin.operational()
        assert rows["total"]==2 and detail["total"]==31
        assert operational["archives"]==[]
    assert len(detail["batches"])==25
    assert detail["categories"]["fo_original"]["allocated_bytes"]==source.stat().st_blocks*512
    assert detail["categories"]["result_media"]["allocated_bytes"]==0
    assert detail["categories"]["result_media"]["logical_bytes"]==source.stat().st_size
    assert sum(r["usage"]["allocated_bytes"] for r in rows["rows"])==data["owners"][str(user)]["allocated_bytes"]
    next_page=owner.get(f"/api/storage/accounts/{user}?offset=25").json()
    assert len(next_page["batches"])==6 and next_page["total"]==31
    assert owner.get("/api/storage/accounts?limit=101").status_code==422
    assert owner.get("/api/storage/accounts/999999999").status_code==404
    assert owner.get("/api/storage/operations").status_code==200
    assert owner.get("/api/storage/usage").status_code==200
    paths=["usage","accounts",f"accounts/{user}","operations","accounting/issues","maintenance","maintenance/expired_archives/preview","host-maintenance/storage-cache/preview","host-maintenance/storage-logs/preview"]
    for path in paths:
        assert viewer.get("/api/storage/"+path).status_code==403,path
        assert public.get("/api/storage/"+path).status_code==401,path
    for path in ("reconcile","maintenance/expired_archives","host-maintenance/storage-cache","host-maintenance/storage-logs"):
        assert viewer.post("/api/storage/"+path,json={"confirmed":True}).status_code==403
        assert public.post("/api/storage/"+path,json={"confirmed":True}).status_code==401
    assert owner.post("/api/storage/reconcile",headers={"Origin":"https://evil.example"}).status_code==403
    assert owner.post("/api/storage/host-maintenance/storage-cache",json={"confirmed":False}).status_code==422
    assert owner.post("/api/storage/host-maintenance/arbitrary",json={"confirmed":True}).status_code==422
    assert owner.get("/api/storage/host-maintenance/storage-cache/preview").status_code==200
    assert owner.get("/api/storage/host-maintenance/storage-logs/preview").status_code==200

def test_manual_reconciliation_and_safe_archive_action(system,monkeypatch):
    owner,_,_=clients(monkeypatch)
    batch=_batch(system)
    run=_job(system,batch)
    folder=managed_path(Category.ZIP_RESULTS,run_id=run)
    folder.mkdir(parents=True)
    expired=folder/("a"*12+"-"+"b"*20+".zip")
    fresh=folder/("c"*12+"-"+"d"*20+".zip")
    unknown=folder/"unknown.zip"
    for p in (expired,fresh,unknown):p.write_bytes(b"archive")
    old=time.time()-4000
    for p in (expired,unknown):os.utime(p,(old,old))
    reconciler=Reconciler()
    try:
        first=settle(reconciler)
        # A manual request must trigger a new generation without waiting 900s.
        unknown.write_bytes(b"changed")
        assert owner.post("/api/storage/reconcile").status_code==202
        assert owner.get("/api/storage/usage").json()["registry"]["reconciliation_requested"]
        after=settle(reconciler)
        assert not after["reconciliation_requested"]
        assert after["reconciled_at"]>=first["reconciled_at"]
        from server.services import operations as io_operations
        lease=io_operations.start(batch,"download")
        try:
            operations=owner.get("/api/storage/operations").json()
            assert any(row["kind"]=="download" and row["operations"]==1 for row in operations["io_leases"])
        finally:io_operations.finish(lease)
        assert sum(row["files"] for row in operations["archives"])==2
        assert sum(row["expired"] for row in operations["archives"])==1
        preview=owner.get("/api/storage/maintenance/expired_archives/preview")
        assert preview.status_code==200 and preview.json()["files"]==1
        assert expired.exists() and unknown.exists()
        assert owner.post("/api/storage/maintenance/expired_archives",json={"confirmed":False}).status_code==422
        assert owner.post("/api/storage/maintenance/expired_archives",json={"confirmed":"true"}).status_code==422
        assert owner.post("/api/storage/maintenance/unknown",json={"confirmed":True}).status_code==422
        assert owner.post("/api/storage/maintenance/expired_archives",json={"confirmed":True}).status_code==202
        with archive_cache.pin(folder):
            storage_maintenance.run_pending()
            assert expired.exists()
        status=owner.get("/api/storage/maintenance").json()
        assert status[0]["state"]=="completed" and status[0]["removed"]==0
        assert owner.post("/api/storage/maintenance/expired_archives",json={"confirmed":True}).status_code==202
        storage_maintenance.run_pending()
        assert not expired.exists() and fresh.exists() and unknown.exists()
        assert owner.get("/api/storage/maintenance").json()[0]["removed"]==1
        data=settle()
        assert data["categories"]["unknown"]["files"]==1
        with database.connect() as db:
            db.execute("UPDATE storage_maintenance SET state='running'")
        storage_maintenance.run_pending()
        assert owner.get("/api/storage/maintenance").json()[0]["state"]=="interrupted"
    finally:reconciler.close()
