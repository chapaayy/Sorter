"""Stage 4: immutable FIFO snapshots, ROI quality, best picks and ZIP recovery."""
from __future__ import annotations
import io
import json
import uuid
import zipfile
import numpy as np
import cv2
import pytest
from fastapi import HTTPException
from PIL import Image
from app.ad_recognition import best,quality
from server.database import connect
from server.services import (ad_layouts,ad_pipeline,ad_pipeline_settings,
                             archive_pipeline,archives,screen_annotations as screens)
from server.db.repositories import work_queue
from .test_unified_queue_stage3 import (system,add_published_reference,add_fo,finish_fo)
from .test_screen_annotations import CORNERS
from .test_ad_recognition import pixels

def _entry(index,layout="layout1",*,score=55,review=False,sam="SAM 0001",screen="screen1",status="matched"):
    return {"index":index,"assigned_sam":sam,"screen_id":screen,
            "candidate_id":layout,"layout_name":layout,"status":status,
            "review_required":review,
            "quality":{"status":"measured","score":score}}

def test_quality_sharpness_and_exposure_measured_only_inside_screen():
    image=np.zeros((280,420,3),dtype=np.uint8)
    for y in range(0,280,16):
        for x in range(0,420,16):
            image[y:y+16,x:x+16]=((250,240,230) if (x//16+y//16)%2 else (15,20,30))
    source=Image.fromarray(image)
    screen={"crop_box":{"x":0,"y":0},
            "corners":[{"x":30,"y":30},{"x":390,"y":30},
                       {"x":390,"y":250},{"x":30,"y":250}]}
    crisp=quality.assess(source,screen,(1600,900))
    blurry=quality.assess(Image.fromarray(cv2.GaussianBlur(image,(31,31),9)),
                          screen,(1600,900))
    over=quality.assess(Image.new("RGB",(420,280),"white"),screen,(1600,900))
    assert crisp["status"]=="measured"
    assert 0<=crisp["score"]<=100
    assert crisp["score"]>blurry["score"]
    assert over["metrics"]["glare_fraction"]>.9
    assert over["score"]<crisp["score"]
    assert crisp["metrics"]["screen_coverage"]<1

def test_quality_rejects_tiny_distant_screen():
    screen={"crop_box":{"x":0,"y":0},"corners":[
        {"x":0,"y":0},{"x":3,"y":0},{"x":3,"y":3},{"x":0,"y":3}]}
    result=quality.assess(Image.new("RGB",(4,4),"red"),screen,(1920,1080))
    assert result["status"]=="insufficient"

def test_best_is_per_sam_screen_and_layout_and_uses_combined_scores():
    rows=[
       _entry(0,score=80,review=True),
       _entry(1,score=70,review=False),
       _entry(2,score=99,status="uncertain"),
       _entry(3,layout="layout2",score=65),
       _entry(4,score=67,sam="TLT 0001"),
       _entry(5,score=91,screen="screen2")
    ]
    picked=best.select(rows)
    assert len(picked)==4
    assert {(r["assigned_sam"],r["screen_id"],r["candidate_id"]) for r in picked}=={
        ("SAM 0001","screen1","layout1"),("SAM 0001","screen1","layout2"),
        ("SAM 0001","screen2","layout1"),("TLT 0001","screen1","layout1")}
    assert next(r for r in picked if r["assigned_sam"]=="SAM 0001"
                and r["screen_id"]=="screen1" and r["candidate_id"]=="layout1")["index"]==1
    tie=best.select([_entry(6,score=60),_entry(4,score=60)])
    assert tie[0]["index"]==4

def test_default_old_fifo_megaloc_only(system):
    assert ad_pipeline_settings.read()["enabled"] is False
    ref_id,_=add_published_reference(system)
    run=add_fo()
    with connect() as db:job=work_queue.claim_next(db)
    assert job["id"]==run
    frozen=job["info"]["ad_pipeline"]
    assert frozen["enabled"] is False
    assert frozen["grouping_threshold"]==.81
    assert frozen["matching_threshold"]==.81
    finish_fo(run)

def test_fifo_claim_freezes_reference_and_layout_revisions(system,monkeypatch):
    ref_id,_=add_published_reference(system)
    monkeypatch.setattr(screens,"DATA_DIR",system)
    monkeypatch.setattr(ad_layouts,"ROOT",system/"ad_layouts")
    created=screens.create("SAM 0001",ref_id,None,"Главный экран",CORNERS,2)
    layout_id=uuid.UUID(ad_layouts.create(pixels(),"ad.png","Исходная реклама","СКИДКИ 50")["id"])
    from app.screen_detection import xfeat_assets
    from app.ad_recognition import dino,ocr
    monkeypatch.setattr(xfeat_assets,"status",lambda:{"available":True})
    monkeypatch.setattr(dino,"status",lambda:{"available":True})
    monkeypatch.setattr(ocr,"status",lambda:{"available":True})
    monkeypatch.setattr(ocr,"signature",lambda:"test-paddle-sha")
    monkeypatch.setattr(dino,"verify",lambda:True)
    monkeypatch.setattr(dino,"load",lambda:object())
    monkeypatch.setattr(dino,"embed",lambda *_:np.r_[1.,np.zeros(383)].astype("float32"))
    monkeypatch.setattr(ocr,"load",lambda:object())
    monkeypatch.setattr(ocr,"read",lambda *_:[{"text":"СКИДКИ 50","score":.98}])
    from app.ad_recognition import embedding_cache
    from server.workers import ad_layout_prepare
    from .test_ad_layout_preparation_stage1 import _claim_layout
    monkeypatch.setattr(embedding_cache,"ROOT",system/"cache"/"dino"/"layouts")
    ad_layout_prepare.run(_claim_layout(layout_id))
    assert ad_pipeline_settings.update(True)["enabled"]
    run=add_fo()
    with connect() as db:
        task=work_queue.claim_next(db)
    frozen=task["info"]["ad_pipeline"]
    assert frozen["enabled"] is True and frozen["status"]=="queued"
    assert len(frozen["annotations"])==1 and len(frozen["layouts"])==1
    assert frozen["annotations"][0]["target_path"].startswith(str(system/"reference_staging"))
    assert frozen["layouts"][0]["name"]=="Исходная реклама"
    screens.update("SAM 0001",uuid.UUID(created["id"]),1,CORNERS,3)
    ad_layouts.update(layout_id,1,"Новое название","Другая акция",True)
    assert frozen["annotations"][0]["version"]==1
    assert frozen["annotations"][0]["band_width_px"]==2
    assert frozen["layouts"][0]["name"]=="Исходная реклама"
    assert frozen["layouts"][0]["expected_text"]=="СКИДКИ 50"
    with pytest.raises(HTTPException) as busy:
        ad_layouts.delete(layout_id)
    assert busy.value.status_code==409
    finish_fo(run)
    with pytest.raises(HTTPException) as still_enabled:
        ad_layouts.delete(layout_id)
    assert still_enabled.value.status_code==409
    with pytest.raises(HTTPException) as cannot_disable_last:
        ad_layouts.update(layout_id,2,"Название","",False)
    assert cannot_disable_last.value.status_code==409
    assert not ad_pipeline_settings.update(False)["enabled"]
    assert ad_layouts.delete(layout_id)=={"deleted":True}

def test_zip_selects_best_and_metadata_and_recovers_without_inference(tmp_path,monkeypatch):
    from app.results import repository
    from server.storage import paths
    run="20261108T120000-123abc123abc"
    root=tmp_path/"data"
    out=root/"outputs"/run
    source=out/"megaloc"/"SAM 0001"/"frame.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original fake photo preserved in ZIP")
    index=root/"runs"/run/"models"
    index.mkdir(parents=True)
    manifest=source.parents[1]/"manifest.json"
    manifest.write_text(json.dumps([{"copy":str(source),"assigned_sam":"SAM 0001"}]))
    (index/"megaloc.json").write_text(json.dumps({"path":str(manifest)}))
    snapshot={"enabled":True,"annotations":[],"layouts":[{"id":"layout-1"}],
              "xfeat_signature":"x","dino_signature":"d","ocr_version":"o",
              "status":"completed"}
    (root/"runs"/run/"run.json").write_text(json.dumps({"id":run,"ad_pipeline":snapshot}))
    item=_entry(0,review=True,score=87)
    item.update({"screen_id":str(uuid.uuid4()),"candidate_id":str(uuid.uuid4()),
                 "layout_name":"Скидки / Новый год","screen_name":"LED",
                 "copy":source.relative_to(out).as_posix()})
    artifact=out/"ad_pipeline"/"summary.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({"status":"completed","run_id":run,
                                    "snapshot_digest":ad_pipeline.digest(snapshot),
                                    "best":[item],"screens_found":1}))
    monkeypatch.setattr(repository,"RUNS_DIR",root/"runs")
    monkeypatch.setattr(archive_pipeline,"DATA_DIR",root)
    monkeypatch.setattr(ad_pipeline,"DATA_DIR",root)
    monkeypatch.setattr(archives.storage_paths,"OUTPUTS",root/"outputs")
    picked=archive_pipeline.selections(run)
    assert len(picked)==3
    assert any("Review_required/" in path for _,path in picked)
    assert any(path=="Ad_recognition/summary.json" for _,path in picked)
    archive=archives.prepare(run,None,picked)
    with zipfile.ZipFile(archive) as final:
        names=final.namelist()
        assert len(names)==3
        assert names[0]=="SAM 0001/frame.jpg"
        assert len([name for name in names if name.startswith("Review_required/")])==1
        assert final.read("Ad_recognition/summary.json")==artifact.read_bytes()
    assert archives.existing(run,None,archive_pipeline.selections(run))==archive
    # Simulate loss of run.json after ZIP publication. PostgreSQL snapshot
    # must keep the curated best entries during ZIP-only recovery.
    from contextlib import contextmanager
    from types import SimpleNamespace
    from server import database
    @contextmanager
    def from_database():
        yield SimpleNamespace(execute=lambda *_a,**_kw:
                              SimpleNamespace(fetchone=lambda:{"snapshot":{"ad_pipeline":snapshot}}))
    monkeypatch.setattr(database,"connect",from_database)
    (root/"runs"/run/"run.json").unlink()
    assert archive_pipeline.selections(run)==picked

def test_public_best_summary_redacts_internal_paths(tmp_path,monkeypatch):
    run="20261108T120000-123abc123abc"
    monkeypatch.setattr(ad_pipeline,"DATA_DIR",tmp_path)
    folder=tmp_path/"outputs"/run/"ad_pipeline"
    folder.mkdir(parents=True)
    (folder/"summary.json").write_text(json.dumps({"status":"completed","run_id":run,
         "best":[{"index":3,"copy":"megaloc/SAM 0001/secret.jpg","quality":{"score":75}}]}))
    public=ad_pipeline.summary(run)
    assert "copy" not in public["best"][0]
    assert "copy" in ad_pipeline.summary(run,internal=True)["best"][0]

def test_zip_ready_with_per_photo_errors_still_schedules_retention(system):
    from server import database
    add_published_reference(system)
    run=add_fo()
    with connect() as db:
        batch=db.execute("SELECT batch_id FROM jobs WHERE id=%s",(run,)).fetchone()["batch_id"]
    database.save_snapshot({"id":run,"batch_id":str(batch),
        "status":"completed_with_errors","archive_state":"ready",
        "ad_pipeline":{"enabled":True,"status":"completed","errors":2},
        "models":{"megaloc":{"status":"completed"}}})
    with connect() as db:
        row=db.execute("SELECT delete_after_at,confirmed_run_id FROM batches WHERE id=%s",
                       (batch,)).fetchone()
        state=db.execute("SELECT status FROM jobs WHERE id=%s",(run,)).fetchone()["status"]
    assert state=="completed_with_errors"
    assert row["delete_after_at"] is not None
    assert row["confirmed_run_id"]==run

def test_fifo_signature_changes_if_paddle_weights_manifest_changes(tmp_path,monkeypatch):
    from app.ad_recognition import ocr
    monkeypatch.setattr(ocr,"ROOT",tmp_path)
    monkeypatch.setattr(ocr,"_verify",lambda:True)
    file=tmp_path/"manifest.json"
    file.write_text('{"version":"OCR","hash":"111"}',encoding="utf-8")
    old=ocr.signature()
    file.write_text('{"version":"OCR","hash":"222"}',encoding="utf-8")
    assert ocr.signature()!=old

def test_fifo_with_no_annotation_never_reads_later_live_screens(monkeypatch,tmp_path):
    from server.services import screen_search
    def prohibited(*args):
        raise AssertionError("Stage 4 must use frozen FIFO annotations ONLY")
    monkeypatch.setattr(screen_search,"_screen_data",prohibited)
    rows=[{"assigned_sam":"SAM 0001","query":"unused"}]
    frozen=ad_pipeline._references({"annotations":[]},rows)
    assert frozen=={"SAM 0001":[]}
    result,image=screen_search._analyse_photo(
        object(),{"index":0,"assigned_sam":"SAM 0001"},
        tmp_path/"file-never-accessed.jpg",frozen,{})
    assert result["status"]=="no_annotations"
    assert image is None
