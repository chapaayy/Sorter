"""Stage 3 regression with disposable PostgreSQL and model-independent fixtures."""
from __future__ import annotations
import io
import uuid
import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image
from app.ad_recognition import ocr,scoring,embedding_cache
from server.services import ad_layouts,ad_recognition
from .test_unified_queue_stage3 import system

def pixels():
    out=io.BytesIO()
    Image.new("RGB",(140,100),"red").save(out,format="PNG")
    return out.getvalue()

def unit(i=0):
    value=np.zeros(384,dtype="float32")
    value[i]=1
    return value

def layout(name="Реклама"):
    return {"id":uuid.uuid4(),"name":name,"checksum":"a"*64,
            "version":1,"expected_text":"Скидки 50"}

def test_ad_library_crud_duplicate_version_and_deleted_bytes(system,monkeypatch):
    monkeypatch.setattr(ad_layouts,"ROOT",system/"ad_layouts")
    uid=uuid.UUID(ad_layouts.create(pixels(),"test.png","Реклама","Скидки 50")["id"])
    assert ad_layouts.list_layouts()["total"]==1
    file=ad_layouts.image(uid)
    assert file.is_file()
    with pytest.raises(HTTPException) as exc:
        ad_layouts.create(pixels(),"dup.png","Дубль")
    assert exc.value.status_code==409
    assert ad_layouts.update(uid,1,"Новый","Другая реклама",False)["version"]==2
    assert ad_layouts.active_files()==[]
    with pytest.raises(HTTPException) as exc:
        ad_layouts.update(uid,1,"Устарело","",True)
    assert exc.value.status_code==409
    assert ad_layouts.delete(uid)=={"deleted":True}
    assert not file.exists()
    assert ad_layouts.list_layouts()["total"]==0

@pytest.mark.parametrize("data",[b"not an image",b"x"*(20*1024*1024+1)])
def test_reject_invalid_layout(system,monkeypatch,data):
    monkeypatch.setattr(ad_layouts,"ROOT",system/"ad_layouts")
    with pytest.raises(HTTPException):
        ad_layouts.create(data,"bad.png","Invalid")
    assert ad_layouts.list_layouts()["total"]==0

def test_dino_margin_and_no_match():
    a,b=layout("A"),layout("B")
    near=unit();near[0]=.98;near[1]=.199;near/=np.linalg.norm(near)
    result=scoring.rank(unit(),[(a,unit()),(b,near)])
    assert result["status"]=="uncertain"
    assert result["candidate_id"]==str(a["id"])
    assert scoring.rank(unit(),[(a,unit(1))])["status"]=="no_match"
    assert scoring.rank(unit(),[])["status"]=="no_layouts"

def test_russian_ocr_text_verification_and_no_text():
    assert ocr.confirm("Скидки 50",[{"text":"СКИДКИ","score":.95},
                                  {"text":"50","score":.95}])["status"]=="confirmed"
    assert ocr.confirm("Скидки 50",[{"text":"Новинки","score":.95}])["status"]=="mismatch"
    assert ocr.confirm("Скидки 50",[{"text":"Скидки 40","score":.95}])["status"]=="mismatch"
    assert ocr.confirm("Скидки",[])["status"]=="unreadable"
    assert ocr.confirm("",[])["status"]=="not_configured"

def test_paddle_v3_public_json_result():
    class Result:
        json={"res":{"rec_texts":["Скидки 50","нечетко"],"rec_scores":[.96,.2]}}
    class Engine:
        def predict(self,img):
            assert isinstance(img,np.ndarray)
            return [Result()]
    assert ocr.read(Engine(),Image.new("RGB",(50,50)))==[
        {"text":"Скидки 50","score":.96}]

def test_screen_mask_excludes_background(tmp_path):
    path=tmp_path/"crop.png"
    Image.new("RGB",(100,100),(80,200,30)).save(path)
    screen={"crop_box":{"x":50,"y":70,"width":100,"height":100},
            "corners":[{"x":70,"y":90},{"x":120,"y":90},
                       {"x":120,"y":140},{"x":70,"y":140}]}
    arr=np.asarray(ad_recognition._crop_screen(path,screen))
    assert list(arr[0,0])==[0,0,0]
    assert list(arr[40,40])==[80,200,30]

def test_ocr_mismatch_never_changes_dino_candidate(monkeypatch,tmp_path):
    row=layout()
    picture=tmp_path/"crop.png"
    Image.new("RGB",(100,100),"red").save(picture)
    monkeypatch.setattr(ad_recognition.screen_search,"crop",lambda *args:picture)
    monkeypatch.setattr(ad_recognition.screen_search,"saved",
                        lambda *args:{"model_signature":"xfeat"})
    monkeypatch.setattr(ad_recognition.dino,"embed",lambda *_:unit())
    monkeypatch.setattr(ad_recognition,"_ocr_check",
                        lambda *args:{"status":"mismatch","reason":"Другие слова"})
    screen={"screen_id":str(uuid.uuid4()),"crop_box":{"x":0,"y":0},
            "corners":[{"x":10,"y":10},{"x":90,"y":10},
                       {"x":90,"y":90},{"x":10,"y":90}],
            "annotation_id":"example","annotation_version":5}
    item=ad_recognition._identify(object(),object(),screen,
                                 "20261108T120000-123abc123abc",0,
                                 [(row,unit(),picture)],{},[])
    assert item["status"]=="matched"
    assert item["candidate_id"]==str(row["id"])
    assert item["ocr"]["status"]=="mismatch"
    assert item["review_required"] is True

def test_versioned_dino_cache_and_atomic_results(tmp_path,monkeypatch):
    assert embedding_cache.key("a"*64)!=embedding_cache.key("b"*64)
    monkeypatch.setattr(ad_recognition,"DATA_DIR",tmp_path)
    run="20261108T120000-123abc123abc";sid=uuid.uuid4()
    assert ad_recognition.result(run,0,sid)["status"]=="not_processed"
    ad_recognition._write(run,0,sid,{"status":"matched","candidate_id":"sample"})
    assert ad_recognition.result(run,0,sid)["candidate_id"]=="sample"
    with pytest.raises(ValueError):
        ad_recognition.result("../../etc",0,sid)
