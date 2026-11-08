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
    assert file.exists()  # Historical originals remain until lifecycle GC.
    ad_layouts.gc_retired()
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
    assert scoring.rank(unit(),[(a,unit(1))])["candidate_id"] is None
    assert scoring.rank(unit(),[])["status"]=="no_layouts"

def test_russian_ocr_text_verification_and_no_text():
    assert ocr.confirm("Скидки 50",[{"text":"СКИДКИ","score":.95},
                                  {"text":"50","score":.95}])["status"]=="confirmed"
    assert ocr.confirm("Скидки 50",[{"text":"Новинки","score":.95}])["status"]=="probable"
    assert ocr.confirm("Скидки 50",[{"text":"Скидки 40","score":.95}])["status"]=="probable"
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
    assert item["review_required"] is False
    monkeypatch.setattr(ad_recognition,"_ocr_check",
                        lambda *args:{"status":"not_configured","reason":"Текст неизвестен"})
    unverified=ad_recognition._identify(object(),object(),screen,
                              "20261108T120000-123abc123abc",0,
                              [(row,unit(),picture)],{},[])
    assert unverified["candidate_id"]==str(row["id"])
    assert unverified["review_required"] is False
    monkeypatch.setattr(ad_recognition,"_ocr_check",
                        lambda *args:{"status":"confirmed","reason":"Текст совпал"})
    verified=ad_recognition._identify(object(),object(),screen,
                          "20261108T120000-123abc123abc",0,
                          [(row,unit(),picture)],{},[])
    assert verified["review_required"] is False

def test_versioned_dino_cache_and_atomic_results(tmp_path,monkeypatch):
    assert embedding_cache.key("a"*64)!=embedding_cache.key("b"*64)
    monkeypatch.setattr(ad_recognition,"DATA_DIR",tmp_path)
    run="20261108T120000-123abc123abc";sid=uuid.uuid4()
    assert ad_recognition.result(run,0,sid)["status"]=="not_processed"
    ad_recognition._write(run,0,sid,{"status":"matched","candidate_id":"sample"})
    assert ad_recognition.result(run,0,sid)["candidate_id"]=="sample"
    with pytest.raises(ValueError):
        ad_recognition.result("../../etc",0,sid)

def test_completed_megaloc_run_reuses_xfeat_crop_without_tampering_zip(system,monkeypatch):
    import json
    from server.database import connect
    from server.services import result_pages,screen_search
    root=system
    monkeypatch.setattr(ad_layouts,"ROOT",root/"ad_layouts")
    monkeypatch.setattr(ad_recognition,"DATA_DIR",root)
    monkeypatch.setattr(screen_search,"DATA_DIR",root)
    monkeypatch.setattr(result_pages,"DATA_DIR",root)
    uid=uuid.UUID(ad_layouts.create(pixels(),"ad.png","Реклама","Скидки 50")["id"])
    # Simulate the completed FIFO layout publication without loading neural weights.
    source=ad_layouts.image(uid)
    monkeypatch.setattr(ad_layouts,"active_files",lambda:[({
        "id":uid,"name":"Реклама","checksum":"a"*64,"version":1,
        "expected_text":"Скидки 50","prepared_key":"prepared-test",
        "embedding_path":"test-vector"},source)])
    batch=uuid.uuid4()
    run="20261108T120000-"+uuid.uuid4().hex[:12]
    screen_id=uuid.uuid4()
    with connect() as db:
        db.execute("""INSERT INTO batches(id,display_name,upload_manifest_state)
            VALUES (%s,'Test FO','complete')""",(batch,))
        db.execute("""INSERT INTO jobs(id,batch_id,status,snapshot)
            VALUES (%s,%s,'completed','{}'::jsonb)""",(run,batch))
    output=root/"outputs"/run
    manifest=output/"megaloc"
    manifest.mkdir(parents=True)
    (manifest/"manifest.rows.jsonl").write_text(json.dumps({
        "index":0,"query":str(root/"uploads"/str(batch)/"fo.jpg"),"assigned_sam":"SAM 0001"})+"\n")
    archive=output/"photos.zip"
    archive.write_bytes(b"original ZIP untouched")
    stage2=output/"screen_search"/"0"
    stage2.mkdir(parents=True)
    screen={"screen_id":str(screen_id),"screen_name":"LED","status":"found",
            "annotation_id":str(uuid.uuid4()),"annotation_version":2,
            "crop_box":{"x":0,"y":0,"width":140,"height":100},
            "corners":[{"x":10,"y":10},{"x":130,"y":10},
                       {"x":130,"y":90},{"x":10,"y":90}]}
    (stage2/"result.json").write_text(json.dumps({"index":0,"status":"found",
        "model_signature":"xfeat-test","screens":[screen]}))
    (stage2/(str(screen_id)+".png")).write_bytes(pixels())
    monkeypatch.setattr(ad_recognition.dino,"load",lambda:object())
    monkeypatch.setattr(ad_recognition.dino,"embed",lambda *_args:unit())
    monkeypatch.setattr(ad_recognition.embedding_cache,"prepared",lambda *_args:unit())
    monkeypatch.setattr(ad_recognition.ocr,"status",lambda:{"available":False})
    done=ad_recognition.analyze_run(run,limit=1)
    assert done["screens"]==1 and done["matched"]==1
    saved=ad_recognition.result(run,0,screen_id)
    assert saved["candidate_id"]==str(uid)
    assert saved["source_xfeat_signature"]=="xfeat-test"
    assert saved["ocr"]["status"]=="unavailable" and not saved["review_required"]
    assert archive.read_bytes()==b"original ZIP untouched"
    with connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=%s",(run,)).fetchone()["status"]=="completed"
        assert db.execute("SELECT count(*) AS n FROM batch_operations WHERE batch_id=%s",
                          (batch,)).fetchone()["n"]==0

def test_manual_layout_cache_cleanup_preserves_active_and_recent(tmp_path,monkeypatch):
    import os
    import time
    monkeypatch.setattr(embedding_cache,"ROOT",tmp_path)
    old="a"*64
    kept="b"*64
    recent="c"*64
    for name in (old,kept,recent):
        (tmp_path/(name+".npy")).write_bytes(b"not touched")
    age=time.time()-9*86400
    os.utime(tmp_path/(old+".npy"),(age,age))
    os.utime(tmp_path/(kept+".npy"),(age,age))
    (tmp_path/"not-a-key.txt").write_text("unrelated")
    assert embedding_cache.prune_inactive({kept})=={"removed":1}
    assert (tmp_path/(kept+".npy")).is_file()
    assert (tmp_path/(recent+".npy")).is_file()
    assert (tmp_path/"not-a-key.txt").is_file()
