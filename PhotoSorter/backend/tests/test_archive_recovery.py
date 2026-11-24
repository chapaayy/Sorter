"""Missing completed ZIP can be recovered without running MegaLoc again."""
from __future__ import annotations
import json
import zipfile
from fastapi import HTTPException
import pytest
from psycopg.types.json import Jsonb

from server.database import connect
from server.services import archives,archive_retries,archive_pipeline,cleanup
from server.storage import paths
from .test_stage1_lifecycle import sandbox,db,_batch,_job


def test_zip_absence_is_normal_and_never_changes_job_status(sandbox):
    batch=_batch(sandbox)
    run=_job(sandbox,batch)
    try:
        with connect() as db:
            db.execute("UPDATE jobs SET snapshot=%s WHERE id=%s",(
                Jsonb({"id":run,"status":"completed","archive_state":"ready",
                       "models":{"megaloc":{"status":"completed"}}}),run))
        assert archive_retries.archive_status(run)=={
            "run_id":run,"state":"on_demand","can_retry":False}
        with pytest.raises(HTTPException) as rejected:
            archive_retries.request(run)
        assert rejected.value.status_code==409
        with connect() as db:
            assert db.execute("SELECT status FROM jobs WHERE id=%s",(run,)).fetchone()["status"]=="completed"
            assert db.execute("SELECT count(*) AS n FROM archive_retries WHERE run_id=%s",(run,)).fetchone()["n"]==0
        assert not list(paths.run_dir(run).rglob("*.zip"))
    finally:
        cleanup.request(batch)
        cleanup.cleanup_one(batch)

@pytest.mark.parametrize("legacy_format",[True,False])
def test_download_preserves_names_without_rerunning_megaloc(sandbox,legacy_format):
    from io import BytesIO
    from urllib.parse import unquote
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server.api.routes.downloads import router
    from server.services import batches

    batch=_batch(sandbox)
    title=batches.rename(batch,"Самара 15.11")["display_name"]
    run=_job(sandbox,batch)
    model=paths.run_dir(run)/"megaloc"
    index=sandbox/"runs"/run/"models"
    index.mkdir(parents=True)
    sam="SAM 9961"
    address="Гагарина 64"
    with connect() as db:
        db.execute("""INSERT INTO reference_constructions(sam,city_code,construction_number,address)
            VALUES (%s,'SAM','9961',%s)""",(sam,address))
        original=db.execute("SELECT target_path FROM uploads WHERE batch_id=%s",(batch,)).fetchone()["target_path"]
        archive_day=db.execute("""SELECT (COALESCE(started_at,created_at) AT TIME ZONE 'Europe/Samara')::date AS day
            FROM jobs WHERE id=%s""",(run,)).fetchone()['day'].isoformat()
        db.execute("UPDATE uploads SET filename='IMG_0115.JPG' WHERE batch_id=%s",(batch,))
        db.execute("UPDATE jobs SET snapshot=%s WHERE id=%s",(
            Jsonb({"id":run,"status":"completed","archive_state":"ready",
                   "models":{"megaloc":{"status":"completed"}}}),run))
    rows=[]
    try:
        for folder,name,query in [(sam,"hash1.jpg",original),(sam,"hash2.jpg",original),
                                  ("_Неопределено","hash3.jpg","/unused/IMG_0914.JPG")]:
            source=model/folder/name
            source.parent.mkdir(parents=True,exist_ok=True)
            source.write_bytes(name.encode())
            rows.append({"copy":str(source),"query":query,"assigned_sam":folder})
        manifest=model/"manifest.json"
        manifest.write_text(json.dumps(rows))
        (index/"megaloc.json").write_text(json.dumps({"path":str(manifest)}))
        if legacy_format:
            initial=archives.prepare(run,None,archive_pipeline.legacy_selections(run))
        else:
            from types import SimpleNamespace
            info={"id":run,"batch_id":str(batch),"status":"completed",
                  "models":{"megaloc":{"status":"completed"}}}
            noop=lambda *args:None
            job=SimpleNamespace(info=info,progress=noop,log=noop,stopped=lambda:False,save=noop)
            archive_pipeline.build_for_job(job)
            assert info["archive_state"]=="on_demand"
            assert not list(model.parent.rglob("*.zip"))
            with connect() as db:
                db.execute("UPDATE jobs SET snapshot=%s WHERE id=%s",(Jsonb(info),run))

        app=FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            reply=client.get("/api/download/"+run)
            assert reply.status_code==200, reply.text[:100]
            assert title+".zip" in unquote(reply.headers["content-disposition"])
            with zipfile.ZipFile(BytesIO(reply.content)) as result:
                expected={
                    f"{title}/{sam} — {address}/{archive_day}/Неназначена сторона/IMG_0115.JPG":b"hash1.jpg",
                    f"{title}/{sam} — {address}/{archive_day}/Неназначена сторона/IMG_0115 (2).JPG":b"hash2.jpg",
                    f"{title}/_Неопределено/{archive_day}/Неназначена сторона/IMG_0914.JPG":b"hash3.jpg",
                }
                assert {name:result.read(name) for name in result.namelist()}==expected
            group=client.get("/api/download/"+run,params={"sam":sam})
            with zipfile.ZipFile(BytesIO(group.content)) as result:
                assert result.namelist()==list(expected)[:2]
            with connect() as db:
                row=db.execute("SELECT status,snapshot FROM jobs WHERE id=%s",(run,)).fetchone()
                assert row["status"]=="completed"
                assert "archive_file" not in row["snapshot"]
            assert archive_retries.archive_status(run)["state"]=="on_demand"
            partial=client.get("/api/download/"+run,headers={"Range":"bytes=5-20"})
            assert partial.status_code==206
            assert partial.content==reply.content[5:21]
            from server.services import archive_cache
            import os,time
            for file in (model.parent/".archives").glob("*.zip"):
                os.utime(file,(time.time()-3700,)*2)
            assert archive_cache.sweep_folder(model.parent/".archives")>=2
            assert not list((model.parent/".archives").glob("*.zip"))
            rebuilt=client.get("/api/download/"+run)
            assert rebuilt.status_code==200
            assert rebuilt.content==reply.content
            assert manifest.is_file()
    finally:
        with connect() as db:
            db.execute("DELETE FROM reference_constructions WHERE sam=%s",(sam,))
        cleanup.request(batch)
        cleanup.cleanup_one(batch)


def test_zip_failed_integrity_check_is_never_published(tmp_path,monkeypatch):
    monkeypatch.setattr(archives.storage_paths,"OUTPUTS",tmp_path)
    run="20261107T120000-abcdef123456"
    source=tmp_path/run/"megaloc"/"SAM 0001"/"one.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"photo")
    monkeypatch.setattr(zipfile.ZipFile,"testzip",lambda _self:"SAM 0001/one.jpg")
    with pytest.raises(OSError,match="проверки ZIP"):
        archives.prepare(run,None,[(source,"SAM 0001/one.jpg")])
    archive_dir=source.parents[2]/".archives"
    assert not list(archive_dir.glob("*.zip"))
    assert not list(archive_dir.glob("*.tmp"))


def test_manual_date_and_video_zip_layout(sandbox):
    from datetime import date
    batch=_batch(sandbox)
    run=_job(sandbox,batch)
    model=paths.run_dir(run)/"megaloc"
    index=sandbox/"runs"/run/"models"
    index.mkdir(parents=True,exist_ok=True)
    items=[]
    try:
        with connect() as db:
            db.execute("UPDATE batches SET report_date_mode='manual',report_date=%s WHERE id=%s",
                (date(2026,11,20),batch))
        for sam,kind,name,side in [
            ("SAM 0001","image","IMG_1.jpg","А"),
            ("SAM 0001","video","CLIP_1.mp4","Б"),
            ("_Неопределено","video","UNKNOWN.mp4",None),
        ]:
            source=model/sam/name
            source.parent.mkdir(parents=True,exist_ok=True)
            source.write_bytes(name.encode())
            items.append({"query":str(source),"copy":str(source),"assigned_sam":sam,
                          "media_kind":kind,"export_name":name,"side":side})
        manifest=model/"manifest.json"
        manifest.write_text(json.dumps(items))
        (index/"megaloc.json").write_text(json.dumps({"path":str(manifest)}))
        plan=archive_pipeline.named_plan(run,batch,"Отчёт по выезду")
        members={name for _,name in plan.files}
        assert members=={
            "Отчёт по выезду/SAM 0001/2026-11-20/Сторона А/IMG_1.jpg",
            "Отчёт по выезду/Видео/SAM 0001/2026-11-20/Сторона Б/CLIP_1.mp4",
            "Отчёт по выезду/Видео/_Неопределено/2026-11-20/Неназначена сторона/UNKNOWN.mp4",
        }
        only_sam=archive_pipeline.named_plan(run,batch,"Отчёт по выезду",sam="SAM 0001")
        assert len(only_sam.files)==2
        with zipfile.ZipFile(archives.prepare(run,None,plan.files)) as zipped:
            assert set(zipped.namelist())==members
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_processing_date_uses_job_start_not_upload_date(sandbox):
    batch=_batch(sandbox)
    run=_job(sandbox,batch)
    model=paths.run_dir(run)/"megaloc"
    source=model/"SAM 0001"/"one.jpg"
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_bytes(b"photo")
    index=sandbox/"runs"/run/"models"
    index.mkdir(parents=True,exist_ok=True)
    manifest=model/"manifest.json"
    manifest.write_text(json.dumps([{"copy":str(source),"assigned_sam":"SAM 0001"}]))
    (index/"megaloc.json").write_text(json.dumps({"path":str(manifest)}))
    try:
        with connect() as db:
            db.execute("UPDATE jobs SET started_at=%s WHERE id=%s",
                ("2026-11-21T21:30:00+00:00",run))
        plan=archive_pipeline.named_plan(run,batch,"Ночной выезд")
        assert plan.files[0][1]=="Ночной выезд/SAM 0001/2026-11-22/Неназначена сторона/one.jpg"
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)
