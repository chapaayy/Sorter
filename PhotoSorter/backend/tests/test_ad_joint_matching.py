"""Relative DINO + independent OCR: distant screens, ambiguity and old path."""
from __future__ import annotations

import uuid

import numpy as np
from PIL import Image

from app.ad_recognition import joint_matching, scoring
from server.services import ad_recognition, ad_pipeline_steps


def vec(score: float):
    result=np.zeros(384,dtype=np.float32)
    result[0]=score
    result[1]=(1.-score*score)**.5
    return result


SCREEN=str(uuid.UUID(int=1))
A=str(uuid.UUID(int=10))
B=str(uuid.UUID(int=11))


def layouts(first="БИГФЕСТ Больше выгоды 49 25 октября",
            second="Скорость нового поколения 5G"):
    return [
        ({"id":A,"name":"IMG_5796","version":2,"checksum":"a"*64,
          "ocr_text":first},vec(.307),None),
        ({"id":B,"name":"IMG_5795","version":1,"checksum":"b"*64,
          "ocr_text":second},vec(.020),None),
    ]


def group_rank(files, first=0):
    item=[{"index":first,"screen_id":SCREEN,"feature":vec(1.)}]
    rank=scoring.rank_group(item,[(r,v) for r,v,_ in files],minimum=.50)
    return rank,item


def recognized(*texts, score=.96):
    return {"lines":[{"text":text,"score":score} for text in texts]}


def test_distant_bigfest_relative_ocr_rescues_visual_score_0307_below_050():
    files=layouts()
    rank,group=group_rank(files)
    assert rank["status"]=="no_match"
    assert rank["rankings"][0]["score"]==.307
    assert rank["rankings"][1]["score"]==.02
    evidence={(0,SCREEN):recognized("БИГФЕСТ","Больше","выгоды",
                                     "49Р","25","октября")}
    decision=joint_matching.decide(rank,group,files,evidence,.50)
    assert decision["status"]=="matched"
    assert decision["candidate_id"]==A
    assert decision["method"]=="visual_ocr_agreement"
    assert decision["ocr_leader_id"]==A
    assert decision["rankings"][0]["ocr_matched_terms"]>=5
    assert decision["rankings"][0]["ocr_support"]>.70
    assert decision["rankings"][0]["combined_score"]>decision["rankings"][1]["combined_score"]


def test_tiny_cosines_without_ocr_dont_choose_least_bad_of_two():
    files=[(row,vec(.11 if i==0 else .01),None)
           for i,(row,_,_) in enumerate(layouts())]
    rank,group=group_rank(files)
    decision=joint_matching.decide(rank,group,files,{(0,SCREEN):recognized()},.50)
    assert decision["status"] in ("no_match","uncertain")
    assert decision["candidate_id"] is None


def test_visual_only_can_choose_clear_relative_winner_below_configured_minimum():
    files=[(row,vec(.41 if i==0 else .07),None)
           for i,(row,_,_) in enumerate(layouts())]
    rank,group=group_rank(files)
    decision=joint_matching.decide(rank,group,files,{},.50)
    assert decision["status"]=="matched"
    assert decision["candidate_id"]==A
    assert decision["method"]=="relative_visual_only"


def test_strong_ocr_breaks_close_dino_tie_for_other_layout():
    files=[(row,vec(.34 if i==0 else .31),None)
           for i,(row,_,_) in enumerate(layouts())]
    rank,group=group_rank(files)
    assert rank["status"]=="no_match"
    decision=joint_matching.decide(rank,group,files,{
        (0,SCREEN):recognized("Скорость","нового","поколения","5G")
    },.5)
    assert decision["status"]=="matched"
    assert decision["candidate_id"]==B
    assert decision["method"]=="ocr_resolved_visual_tie"


def test_ocr_and_dino_strongly_disagree_without_a_visual_tie_abstain():
    rank,group=group_rank(layouts())
    decision=joint_matching.decide(rank,group,layouts(),{
        (0,SCREEN):recognized("Скорость","нового","поколения","5G")
    },.5)
    assert decision["status"]=="uncertain"
    assert decision["candidate_id"] is None
    assert decision["method"]=="visual_ocr_disagreement"


def test_strong_different_text_on_two_group_members_must_abstain():
    files=layouts()
    members=[{"index":n,"screen_id":SCREEN,"feature":vec(1.)} for n in (0,1)]
    rank=scoring.rank_group(members,[(r,v) for r,v,_ in files],minimum=.5)
    decision=joint_matching.decide(rank,members,files,{
        (0,SCREEN):recognized("БИГФЕСТ","Больше","выгоды","49Р"),
        (1,SCREEN):recognized("Скорость","нового","поколения","5G"),
    },.5)
    assert decision["status"]=="uncertain"
    assert decision["candidate_id"] is None
    assert decision["ocr_conflicting_members"] is True


def test_one_word_or_only_one_layout_cannot_rescue_weak_visual_evidence():
    rank,group=group_rank(layouts())
    decision=joint_matching.decide(rank,group,layouts(),{
        (0,SCREEN):recognized("БИГФЕСТ")
    },.5)
    assert decision["status"]!="matched"
    single=[layouts()[0]]
    rank,group=group_rank(single)
    decision=joint_matching.decide(rank,group,single,{
        (0,SCREEN):recognized("БИГФЕСТ","Больше","выгоды","49Р")
    },.5)
    assert decision["status"]!="matched"


def test_visual_only_above_default_threshold_still_works_without_ocr():
    files=[(row,vec(.79 if i==0 else .12),None)
           for i,(row,_,_) in enumerate(layouts())]
    rank,group=group_rank(files)
    decision=joint_matching.decide(rank,group,files,{},.5)
    assert decision["status"]=="matched"
    assert decision["candidate_id"]==A


def test_pre_read_ocr_is_reused_by_individual_analysis_without_second_inference(tmp_path,monkeypatch):
    photo=tmp_path/"crop.png"
    Image.new("RGB",(80,80),"red").save(photo)
    from app.ad_recognition import ocr, dino
    from server.services import screen_search
    monkeypatch.setattr(screen_search,"crop",lambda *_:photo)
    monkeypatch.setattr(screen_search,"saved",
                        lambda *_:{"model_signature":"xfeat"})
    monkeypatch.setattr(ad_recognition,"_crop_screen",
                        lambda *_:Image.new("RGB",(80,80),"red"))
    calls=[]
    monkeypatch.setattr(ocr,"read",lambda *_:(
        calls.append("ocr") or [{"text":"БИГФЕСТ","score":.95}]))
    monkeypatch.setattr(dino,"embed",lambda *_:(_ for _ in ()).throw(
        AssertionError("group embedding already saved")))
    class Job:
        def stopped(self):return False
        def progress(self,*_):pass
    screen={"screen_id":SCREEN}
    observed=ad_pipeline_steps.read_ocr(
        Job(),object(),[(0,"SAM 1193",screen,(80,80))],"run")
    assert calls==["ocr"]
    match={"group_id":"R0001","status":"matched","reason":"Joint",
           "candidate_id":A,"best_score":.307,"margin":.287,
           "matching_threshold":.5,"candidate_count":2,
           "decision_version":joint_matching.VERSION,"method":"visual_ocr_agreement",
           "visual_leader_id":A,"ocr_leader_id":A}
    item=ad_recognition._identify(
        object(),object(),screen,"run",0,
        layouts(),{},[],.5,vec(1.),match,ocr_entry=observed[(0,SCREEN)])
    assert item["status"]=="matched"
    assert item["ocr_observation"]["raw_lines"][0]["text"]=="БИГФЕСТ"
    assert calls==["ocr"]
