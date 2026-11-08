"""Stage 2: independent visual groups, all-layout rankings and saved-result APIs."""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image

from app.ad_recognition import scoring, visual_grouping, dino
from server.services import ad_visual_groups, ad_recognition


def unit(axis=0):
    value=np.zeros(384,dtype="float32")
    value[axis]=1.0
    return value


def sample(index, sam="SAM 0001", screen=None, feature=None):
    return {"index":index, "sam":sam,
            "screen_id":screen or str(uuid.UUID(int=1)),
            "screen_name":"LED", "annotation_id":"a",
            "embedding_file":f"embeddings/{index}/1.npy",
            "feature":unit() if feature is None else feature}


def test_group_before_any_layout_and_keep_physical_screens_separate():
    sid=str(uuid.UUID(int=1))
    other=str(uuid.UUID(int=2))
    close=unit()*0.96+unit(1)*0.28
    rows=[
        sample(0,screen=sid),
        sample(1,screen=sid,feature=close),
        sample(2,screen=sid,feature=unit(1)),
        sample(3,sam="TLT 0001",screen=sid),
        sample(4,screen=other),
    ]
    groups=visual_grouping.group_screens(rows,.85)
    assert [g["id"] for g in groups]==["R0001","R0002","R0003","R0004"]
    assert [g["member_count"] for g in groups]==[2,1,1,1]
    first=groups[0]
    assert first["assigned_sam"]=="SAM 0001" and first["screen_id"]==sid
    assert [m["index"] for m in first["members"]]==[0,1]
    assert first["members"][1]["joined_via"]["index"]==0
    assert first["members"][1]["joined_via"]["similarity"]>.85
    assert first["nearest_other_group"]=="R0002"
    assert first["nearest_other_similarity"]<.85
    assert groups[2]["assigned_sam"]=="TLT 0001"
    assert groups[3]["screen_id"]==other
    assert groups==visual_grouping.group_screens(rows,.85)
    assert all(g["separation_reason"] for g in groups)


def test_transitive_grouping_documents_weak_pair_without_splitting():
    sid=str(uuid.UUID(int=1))
    a=unit()
    b=unit()*.8+unit(1)*.6
    c=unit()*.28+unit(1)*.96
    groups=visual_grouping.group_screens(
        [sample(0,screen=sid,feature=a),sample(1,screen=sid,feature=b),
         sample(2,screen=sid,feature=c)],.75)
    assert len(groups)==1 and groups[0]["member_count"]==3
    assert groups[0]["min_pairwise_similarity"]<.75
    assert groups[0]["members"][2]["joined_via"]["index"]==1


def test_group_ranking_retains_every_layout_and_each_member_score():
    rows=[sample(1,feature=unit()),sample(2,feature=unit(1)),
          sample(3,feature=unit())]
    layouts=[]
    for i in range(9):
        layouts.append(({"id":str(uuid.UUID(int=100+i)),"name":f"layout-{i}",
                         "version":1,"checksum":str(i)*64},
                        unit() if i==0 else unit(i)))
    result=scoring.rank_group(rows,layouts,minimum=.5)
    assert result["method"]=="mean_member_cosine"
    assert len(result["rankings"])==9
    assert result["rankings"][0]["score"]==pytest.approx(2/3,abs=1e-5)
    assert len(result["rankings"][0]["member_scores"])==3
    assert result["rankings"][0]["member_scores"][1]["score"]==0
    assert result["status"]=="matched"
    assert result["matching_threshold"]==.5
    assert scoring.rank(unit(),layouts)["top"]==sorted(
        scoring.rank(unit(),layouts)["top"],key=lambda r:(-r["score"],r["id"]))
    assert len(scoring.rank(unit(),layouts)["top"])==9


def test_saved_results_include_scoped_groups_and_paginated_cosines(tmp_path,monkeypatch):
    run="20261108T120000-123abc123abc"
    root=tmp_path/"data"
    monkeypatch.setattr(ad_visual_groups,"DATA_DIR",root)
    monkeypatch.setattr(ad_visual_groups.screen_search,"crop",
                        lambda _run,index,sid:tmp_path/(str(index)+".png"))
    def crop(path,screen):
        with Image.open(path) as image:return image.convert("RGB")
    monkeypatch.setattr(ad_visual_groups.ad_recognition,"_crop_screen",crop)
    calls=[]
    def embed(model,image):
        calls.append(image.getpixel((0,0)))
        return unit() if image.getpixel((0,0))[0]>100 else unit(1)
    monkeypatch.setattr(dino,"embed",embed)
    for index,color in [(0,(255,0,0)),(1,(255,0,0)),(2,(0,0,255))]:
        Image.new("RGB",(50,50),color).save(tmp_path/(str(index)+".png"))
    screen=str(uuid.UUID(int=1))
    detections=[(i,"SAM 0001",{"screen_id":screen,"screen_name":"Main",
                              "annotation_id":"a"},(1280,720)) for i in range(3)]
    class Job:
        info={"id":run}
        def stopped(self):return False
        def progress(self,*_):pass
    job=Job()
    groups,vectors,errors=ad_visual_groups.collect(job,object(),detections,run,.8)
    assert len(calls)==3
    assert len(vectors)==3 and errors=={}
    assert len(groups)==2 and [g["id"] for g in groups]==["R0001","R0002"]
    for group in groups:
        for member in group["members"]:
            assert (root/"outputs"/run/"ad_pipeline"/member["embedding_file"]).is_file()
    page=ad_visual_groups.overview(run,limit=1,offset=0)
    assert page["total"]==2 and len(page["groups"])==1
    assert page["match_status"]=="pending"
    layouts=[({"id":str(uuid.UUID(int=i+10)),"name":f"Layout {i}","version":2,
               "checksum":str(i)*64},unit() if i==0 else unit(i))
             for i in range(9)]
    layouts=[(row,vector,Path("/unused")) for row,vector in layouts]
    matches=ad_visual_groups.match(job,run,groups,vectors,layouts,.75)
    assert len(matches)==3
    first=matches[(0,screen)]
    assert first["group_id"]=="R0001"
    assert first["status"]=="matched" and first["candidate_count"]==9
    assert ad_visual_groups.overview(run)["match_status"]=="completed"
    detail=ad_visual_groups.detail(run,"R0001")
    assert len(detail["members"])==2
    assert detail["match"]["candidate_id"]==str(uuid.UUID(int=10))
    ranks=ad_visual_groups.rankings(run,"R0001",limit=3,offset=2)
    assert ranks["total"]==9 and len(ranks["rankings"])==3
    assert "member_scores" not in ranks["rankings"][0]
    member=ad_visual_groups.rankings(run,"R0001",limit=3,
                                    index=0,screen_id=uuid.UUID(screen))
    assert member["rankings"][0]["member_score"]==1
    assert member["member_margin"] is not None
    all_members=ad_visual_groups.layout_members(run,"R0001",
                                                str(uuid.UUID(int=10)),limit=1)
    assert all_members["total"]==2 and len(all_members["scores"])==1
    with pytest.raises(HTTPException):
        ad_visual_groups.rankings(run,"R0001",index=55,screen_id=uuid.UUID(screen))


def test_existing_member_recognition_reuses_embedding_without_second_inference(tmp_path,monkeypatch):
    from app.ad_recognition import dino as model
    sid=str(uuid.UUID(int=1))
    picture=tmp_path/"screen.png"
    Image.new("RGB",(80,80),"red").save(picture)
    monkeypatch.setattr(ad_recognition.screen_search,"crop",lambda *_:picture)
    monkeypatch.setattr(ad_recognition.screen_search,"saved",
                        lambda *_:{"model_signature":"xfeat"})
    monkeypatch.setattr(ad_recognition,"_crop_screen",lambda *_:Image.open(picture).convert("RGB"))
    monkeypatch.setattr(model,"embed",lambda *_:(_ for _ in ()).throw(
        AssertionError("DINO re-inference is forbidden")))
    monkeypatch.setattr(ad_recognition,"_ocr_check",
                        lambda *_:{"status":"confirmed","reason":"ok"})
    layout={"id":str(uuid.UUID(int=10)),"name":"Layout","version":1,"checksum":"a"*64,
            "expected_text":"Ad"}
    match={"group_id":"R0001","status":"matched","reason":"group score high",
           "candidate_id":layout["id"],"best_score":1.0,"margin":None,
           "matching_threshold":.8,"candidate_count":1}
    result=ad_recognition._identify(object(),object(),{"screen_id":sid}, "20261108T120000-123abc123abc",
                                   0,[(layout,unit(),picture)],{},[],.8,unit(),match)
    assert result["visual_group_id"]=="R0001"
    assert result["candidate_id"]==layout["id"]
    assert result["group_match"]["best_score"]==1.0
    assert result["member_match"]["status"]=="matched"
    assert not result["review_required"]
