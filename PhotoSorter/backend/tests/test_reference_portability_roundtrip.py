"""Small cross-runtime portability acceptance: real ZIP, TS reader, clean PG/CAS.

Only model inference is replaced by small valid cached vectors. All publication,
chunk transfer, object verification, export and accounting paths are production.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import uuid
import zipfile

from PIL import Image
import psycopg
from psycopg.conninfo import make_conninfo
import pytest

from app import config
from server import database
from server.api.routes import reference_imports as api
from server.db.repositories import reference_versions, work_queue
from server.services import archive_cache, reference_archives, reference_imports, reference_uploads
from server.services import reference_portable_catalog
from server.storage import reference_objects
from server.storage.reference_lifecycle import ReadPin
from server.workers import reference_prepare
from .accounting_checks import settle, exact
from .test_unified_queue_stage3 import system, cache_vector


def image(color):
    data=io.BytesIO()
    Image.new("RGB",(80,40),color).save(data,"JPEG")
    return data.getvalue()


def import_photos(photos):
    sid=uuid.uuid4()
    items=[api.ImportFile(upload_id=uuid.uuid4(),**{k:v for k,v in p.items() if k!="bytes"})
           for p in photos]
    reference_imports.create(sid)
    assert reference_imports.register_manifest(sid,items)["pending"]==len(items)
    for i,(item,photo) in enumerate(zip(items,photos)):
        data=base64.b64decode(photo["bytes"],validate=True)
        assert hashlib.sha256(data).hexdigest()==item.sha256
        # A split transfer exercises the persisted offset and immutable manifest.
        if i==0:
            split=len(data)//2
            reference_uploads.append(sid,item.upload_id,0,data[:split])
            assert reference_imports.file_status(sid,item.upload_id)["offset"]==split
            assert reference_imports.register_manifest(sid,items)["pending"]==len(items)
            reference_uploads.append(sid,item.upload_id,split,data[split:])
        else:
            reference_uploads.append(sid,item.upload_id,0,data)
        assert not reference_uploads.finish(sid,item.upload_id)["already_present"]
        assert not reference_objects.partial(sid,item.upload_id).exists()
    state=reference_imports.status(sid)
    assert state["state"]=="complete" and state["pending"]==0
    assert {row["upload_id"]:row["side"] for row in state["files"]}=={
        str(item.upload_id):item.side for item in items}
    for digest in {item.sha256 for item in items}:
        cache_vector(config.APP_STORAGE_ROOT,digest)
    with database.connect() as db:
        task=work_queue.claim_next(db)
    assert task["kind"]=="reference_preparation"
    assert reference_prepare.run(task["id"])["changed"]
    assert reference_imports.status(sid)["preparation_state"]=="completed"
    return items


def snapshot(manifest):
    return (
        sorted((r["sam"],r["kind"],r["city_code"],r["number"],r["address"])
               for r in manifest["constructions"]),
        sorted((r["sam"],r["sha256"],r["filename"],r["size"],r["side"])
               for r in manifest["photos"])
    )


def export():
    with ReadPin():
        plan=reference_archives.current_plan()
        path=reference_archives.prepare(plan)
    with zipfile.ZipFile(path) as archive:
        manifest=json.loads(archive.read("manifest.json"))
        assert archive.testzip() is None
        assert set(archive.namelist())=={"manifest.json",*(r["path"] for r in manifest["photos"])}
        for row in manifest["photos"]:
            assert hashlib.sha256(archive.read(row["path"])).hexdigest()==row["sha256"]
    return plan,path,manifest


def test_portable_reference_roundtrip(system,tmp_path,monkeypatch):
    # This gate is mandatory in CI; local backend-only installs may run
    # without Node. No extra long model or VM acceptance is necessary.
    if os.environ.get("MAP_PORTABLE_ROUNDTRIP")!="1":
        pytest.skip("Set MAP_PORTABLE_ROUNDTRIP=1 with Node 24 for the cross-runtime gate")
    catalog=[
        dict(sam="SAM 0004",kind="standard",city_code="SAM",number="0004",address="Гагарина 64"),
        dict(sam="TLT 0007",kind="standard",city_code="TLT",number="0007",address="Ленина 10"),
        dict(sam="Индивидуальная",kind="custom",city_code=None,number=None,address=None),
        dict(sam="Пустая",kind="custom",city_code=None,number=None,address=None),
    ]
    assert reference_portable_catalog.inspect([api.PortableConstruction(**c) for c in catalog],create=True)=={"created":4}
    red,blue,green=image("red"),image("blue"),image("green")
    photos=[]
    for i,(sam,address,name,side,data) in enumerate([
        ("SAM 0004","Гагарина 64","one.jpg","A1",red),
        ("SAM 0004","Гагарина 64","ONE.jpg","A1",blue),
        ("TLT 0007","Ленина 10","same.jpg","B2",red),
        ("Индивидуальная",None,"legacy.jpg","Старая/сторона",green),
        ("Индивидуальная",None,"unassigned.jpg",None,blue),
    ]):
        photos.append(dict(sam=sam,address=address,filename=name,side=side,portable=True,
            relative_path=f"source/{i}/{name}",sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),bytes=base64.b64encode(data).decode()))
    original_items=import_photos(photos)
    original_plan,original_zip,original_manifest=export()
    archive_copy=tmp_path/"portable.zip"
    archive_copy.write_bytes(original_zip.read_bytes())
    original_hash=hashlib.sha256(archive_copy.read_bytes()).hexdigest()
    result_file=tmp_path/"frontend-decoded.json"
    bridge=Path(__file__).resolve().parents[2]/"frontend/tests/referenceRoundtripBridge.mjs"
    subprocess.run(["node","--experimental-transform-types",str(bridge),str(archive_copy),str(result_file)],
                   check=True,timeout=60)
    decoded=json.loads(result_file.read_text(encoding="utf-8"))
    assert len(decoded["photos"])==5
    assert len(decoded["constructions"])==4
    # Different physical root and independent PostgreSQL schema.
    original_url=database.DB_URL
    schema="portable_"+uuid.uuid4().hex[:12]
    with psycopg.connect(original_url) as admin:
        admin.execute('CREATE SCHEMA "'+schema+'"')
    try:
        with monkeypatch.context() as m:
            m.setattr(database,"DB_URL",make_conninfo(original_url,options="-c search_path="+schema))
            m.setattr(config,"APP_STORAGE_ROOT",tmp_path/"restored-storage/app")
            config.APP_STORAGE_ROOT.mkdir(parents=True)
            database.initialize()
            from .test_stage1_lifecycle import owner_for_test
            from server.services import regions, thumbnails
            with database.connect() as db:
                owner_for_test(db)
                assert not reference_versions.members(db,reference_versions.current(db)["id"])
            for code in ("SAM","TLT"):
                regions.register(code)
            constructions=[api.PortableConstruction(**c) for c in decoded["constructions"]]
            assert reference_portable_catalog.inspect(constructions)["errors"]==[]
            assert reference_portable_catalog.inspect(constructions,create=True)=={"created":4}
            comparison=[api.ComparisonFile(**p) for p in decoded["photos"]]
            assert reference_imports.compare(comparison)["duplicates"]==[False]*5
            new_items=import_photos(decoded["photos"])
            assert not ({p.upload_id for p in original_items}&{p.upload_id for p in new_items})
            with database.connect() as db:
                version=reference_versions.current(db)["id"]
                assert db.execute("SELECT count(*) AS n FROM reference_physical_objects").fetchone()["n"]==3
                assert db.execute("SELECT count(*) AS n FROM reference_cache").fetchone()["n"]==3
                jobs_before=db.execute("SELECT count(*) AS n FROM work_queue").fetchone()["n"]
            comparison_result=reference_imports.compare(comparison)
            assert comparison_result["duplicates"]==[True]*5
            assert comparison_result["side_conflicts"]==[]
            assert reference_portable_catalog.inspect(constructions,create=True)=={"created":0}
            # Confirm all duplicates directly too: no bytes or new queue task.
            sid=uuid.uuid4()
            repeats=[p.model_copy(update={"upload_id":uuid.uuid4()}) for p in new_items]
            reference_imports.create(sid)
            reference_imports.register_manifest(sid,repeats)
            for item in repeats:
                assert reference_uploads.confirm_duplicate(sid,item.upload_id,item.sha256)["already_present"]
                assert not reference_objects.partial(sid,item.upload_id).exists()
            assert reference_imports.complete(sid)["state"]=="unchanged"
            with database.connect() as db:
                assert reference_versions.current(db)["id"]==version
                assert db.execute("SELECT count(*) AS n FROM work_queue").fetchone()["n"]==jobs_before
            while (task:=thumbnails.claim()) is not None:
                assert thumbnails.complete(task)=="ready"
            plan,restored_zip,restored_manifest=export()
            assert snapshot(restored_manifest)==snapshot(original_manifest)
            assert restored_zip==reference_archives.prepare(plan)
            for digest in {p.sha256 for p in new_items}:
                assert reference_objects.object_path(digest).is_file()
            settle()
            assert exact(restored_zip)["category"]=="zip_references"
            # Simulated time only: check production TTL without a one-hour wait.
            assert archive_cache.TTL_SECONDS==3600
            now=restored_zip.stat().st_mtime
            assert not archive_cache.sweep_folder(restored_zip.parent,reference=True,now=now+3599)
            assert restored_zip.exists()
            assert archive_cache.sweep_folder(restored_zip.parent,reference=True,now=now+3601)>=1
            assert not restored_zip.exists()
            settle()
            with database.connect() as db:
                assert db.execute("SELECT count(*) AS n FROM storage_reservations").fetchone()["n"]==0
            assert all(reference_objects.object_path(d).is_file() for d in {p.sha256 for p in new_items})
    finally:
        with psycopg.connect(original_url) as admin:
            admin.execute('DROP SCHEMA "'+schema+'" CASCADE')
    assert original_zip.is_file()
    assert hashlib.sha256(original_zip.read_bytes()).hexdigest()==original_hash
    assert reference_archives.current_plan().key==original_plan.key
    print("REFERENCE_PORTABLE_CLEAN_LIBRARY_ROUNDTRIP_OK")
