"""Stage 3 OCR contradictions, text variants, review states and ZIP selection."""
from __future__ import annotations

import json
import uuid

import numpy as np
from PIL import Image
from app.ad_recognition import best, dino, ocr
from server.services import ad_recognition, ad_pipeline, ad_text_subgroups, ad_visual_groups


def _line(text, score=.97):
    return [{"text":text,"score":score,
             "polygon":[[0,0],[20,0],[20,10],[0,10]]}]


def _screen(index, text, *, candidate, expected="Акция 10.11.2026 Скидка 50%", score=70):
    lines=_line(text) if text else []
    verification=ocr.confirm(expected,lines)
    return {"index":index,"assigned_sam":"SAM 0001",
            "screen_id":str(uuid.UUID(int=1)), "status":"matched",
            "visual_group_id":"R0001","candidate_id":candidate,
            "layout_name":"Реклама","ocr":verification,
            "ocr_observation":ocr.describe(lines),
            "review_required":verification["status"]!="confirmed",
            "quality":{"status":"measured","score":score}}


def test_generic_ocr_words_preserve_diagnostics_without_semantic_decisions():
    expected="Акция 10 ноября 2026! Скидка 50% Цена 1000 ₽"
    actual=_line("Акция 11 ноября 2026! Скидка 40% Цена 2000 ₽")
    observed=ocr.describe(actual)
    assert observed["status"]=="readable"
    assert observed["confidence"]==.97
    assert observed["regions"][0]["polygon"]==[[0.,0.],[20.,0.],[20.,10.],[0.,10.]]
    # Legacy diagnostic fields stay available but are no longer used to rank.
    assert observed["significant"]["dates"]==["11.11.2026"]
    score=ocr.confirm(expected,actual)
    assert score["status"]=="probable"
    assert score["matched_terms"]>=3
    assert not score["contradictions"]
    assert ocr.confirm(expected,[])["status"]=="unreadable"
    assert ocr.confirm("Акция 50%",_line("Акция",.94))["status"]=="confirmed"
    assert ocr.confirm("Акция 50%",_line("Акция 50%",.55))["status"]=="unreadable"
    assert ocr.confirm("Акция 50%",_line("Акция 50%",.98))["status"]=="confirmed"


def test_text_subgroups_split_numerical_variants_keep_visual_members_and_quality(tmp_path,monkeypatch):
    monkeypatch.setattr(ad_visual_groups,"DATA_DIR",tmp_path)
    stored=[]
    monkeypatch.setattr(ad_text_subgroups.ad_recognition,"_write",
                        lambda run,index,sid,item:stored.append((index,item["text_subgroup_id"])))
    cid=str(uuid.UUID(int=10))
    sid=str(uuid.UUID(int=1))
    photos=[
        _screen(0,"Акция 10.11.2026 Скидка 50%",candidate=cid,score=70),
        _screen(1,"Акция 10.11.2026 Скидка 50%",candidate=cid,score=85),
        _screen(2,"Акция 11.11.2026 Скидка 40%",candidate=cid,score=98),
        _screen(3,"",candidate=cid,score=90),
    ]
    group={"id":"R0001","assigned_sam":"SAM 0001","screen_id":sid,
           "members":[{"index":i,"screen_id":sid} for i in range(4)]}
    class Job:
        def stopped(self):return False
        def progress(self,*args):pass
    run="20261108T120000-123abc123abc"
    document=ad_text_subgroups.form(Job(),run,[group],photos,data_root=tmp_path)
    assert document["subgroup_count"]==3
    assert (document["confirmed"],document["probable"],document["unidentified"])==(1,2,0)
    assert [[m["index"] for m in g["members"]] for g in document["subgroups"]]==[
        [0,1],[2],[3]]
    assert {m["visual_group_id"] for g in document["subgroups"]
            for m in g["members"]}=={"R0001"}
    assert len(stored)==4
    assert [item["classification"] for item in photos]==[
        "confirmed","confirmed","probable","probable"]
    winners=best.select(photos)
    assert {item["index"] for item in winners}=={1,2,3}
    assert len({item["text_subgroup_id"] for item in winners})==3
    assert winners[0]["candidate_id"]==winners[1]["candidate_id"]
    assert not photos[2]["review_required"] and not photos[3]["review_required"]
    paged=ad_text_subgroups.saved(run,limit=2,offset=1)
    assert paged["total"]==3 and len(paged["subgroups"])==2
    assert all("members" not in row for row in paged["subgroups"])
    assert ad_text_subgroups.detail(run,"T0001")["member_count"]==2
    assert ad_text_subgroups.saved(run,group_id="R0001")["total"]==3


def test_ocr_does_not_reassign_group_visual_layout_when_offer_conflicts(tmp_path,monkeypatch):
    picture=tmp_path/"crop.png"
    Image.new("RGB",(80,80),"red").save(picture)
    monkeypatch.setattr(ad_recognition.screen_search,"crop",lambda *args:picture)
    monkeypatch.setattr(ad_recognition.screen_search,"saved",
                        lambda *args:{"model_signature":"xfeat"})
    monkeypatch.setattr(ad_recognition,"_crop_screen",
                        lambda *_:Image.new("RGB",(80,80),"red"))
    monkeypatch.setattr(ad_recognition.ocr,"read",
                        lambda *_:_line("Акция 11.11.2026 Скидка 40%"))
    monkeypatch.setattr(dino,"embed",lambda *_:(_ for _ in ()).throw(
        AssertionError("DINO was already computed")))
    feature=np.zeros(384,dtype="float32");feature[0]=1.
    cid=str(uuid.UUID(int=10));sid=str(uuid.UUID(int=1))
    layout={"id":cid,"name":"Реклама","version":1,"checksum":"a"*64,
            "ocr_text":"Акция 10.11.2026 Скидка 50%"}
    group={"group_id":"R0001","status":"matched","candidate_id":cid,
           "reason":"Визуальное сходство группы","best_score":.99,
           "margin":None,"matching_threshold":.8,"candidate_count":1}
    item=ad_recognition._identify(object(),object(),{"screen_id":sid},
         "20261108T120000-123abc123abc",0,[(layout,feature,picture)],
         {},[],.8,feature,group)
    assert item["candidate_id"]==cid
    assert item["visual_group_id"]=="R0001"
    assert item["status"]=="matched" and item["classification"]=="probable"
    assert item["ocr"]["status"]=="probable"
    assert item["ocr_observation"]["significant"]["percentages"]==["40"]
    assert item["review_required"] is False


def test_zip_contains_subgroup_artifact_and_distinct_group_names(tmp_path,monkeypatch):
    root=tmp_path/"data"
    monkeypatch.setattr(ad_pipeline,"DATA_DIR",root)
    run="20261108T120000-123abc123abc"
    folder=root/"outputs"/run
    photo=folder/"megaloc"/"SAM 0001"/"FO.png"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"synthetic file")
    published=folder/"ad_pipeline"
    published.mkdir()
    (published/"text_subgroups.json").write_text(json.dumps({
        "status":"completed","subgroups":[{"id":"T0001"}]}))
    snapshot={"enabled":True}
    summary={"status":"completed","run_id":run,
             "snapshot_digest":ad_pipeline.digest(snapshot),
             "best":[{"index":0,"assigned_sam":"SAM 0001",
                      "screen_id":str(uuid.UUID(int=1)), "layout_name":"Реклама",
                      "text_subgroup_id":"T0001","review_required":False,
                      "copy":"megaloc/SAM 0001/FO.png"}]}
    (published/"summary.json").write_text(json.dumps(summary))
    entries=ad_pipeline.best_archive_entries(run,snapshot)
    assert len(entries)==3
    assert "T0001" in entries[0][1] and entries[0][1].startswith("Best_by_layout/")
    assert {dest for _,dest in entries[1:]}=={
        "Ad_recognition/text_subgroups.json","Ad_recognition/summary.json"}
