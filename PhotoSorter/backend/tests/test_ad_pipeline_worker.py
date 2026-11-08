"""Stage 4 combined worker path without loading massive pretrained neural nets in pytest."""
from __future__ import annotations
import uuid
from pathlib import Path
import numpy as np
from PIL import Image
from app.ad_recognition import dino,ocr
from app.screen_detection import xfeat_assets
from server.jobs import ServerJob
from server.services import ad_pipeline,archive_pipeline

def test_server_job_integrates_ad_before_final_zip(monkeypatch):
    events=[]
    monkeypatch.setattr(ad_pipeline,"process",lambda job:events.append("ad"))
    monkeypatch.setattr(archive_pipeline,"build_for_job",lambda job:events.append("zip"))
    job=ServerJob({"id":"20261108T120000-123abc123abc",
                   "ad_pipeline":{"enabled":True},"models":{},"progress":{}})
    job.finalize_results()
    assert events==["ad","zip"]
    events.clear()
    job.info["ad_pipeline"]={"enabled":False}
    job.finalize_results()
    assert events==["zip"]

def test_full_cpu_screen_pipeline_writes_best_before_zip(monkeypatch,tmp_path):
    from server.services import screen_search,ad_recognition,ad_layouts
    from app.ad_recognition import quality
    root=tmp_path/"data"
    run="20261108T120000-123abc123abc"
    batch=str(uuid.uuid4())
    layout_id=str(uuid.uuid4())
    screen_id=str(uuid.uuid4())
    sam="SAM 0001"
    source_root=root/"uploads"/batch
    source_root.mkdir(parents=True)
    output=root/"outputs"/run/"megaloc"/sam
    output.mkdir(parents=True)
    rows=[]
    for i in range(2):
        path=source_root/(f"FO{i}.png")
        if i==0:
            rgb=np.zeros((240,360,3),dtype=np.uint8)
            for y in range(0,240,16):
                for x in range(0,360,16):
                    rgb[y:y+16,x:x+16]=[235,230,210] if (x//16+y//16)%2 else [20,30,45]
        else:
            rgb=np.full((240,360,3),225,dtype=np.uint8)
        Image.fromarray(rgb).save(path)
        copy=output/(f"FO{i}.png")
        copy.write_bytes(path.read_bytes())
        rows.append({"query":str(path),"copy":str(copy),"assigned_sam":sam})
    item={"id":layout_id,"name":"Реклама","checksum":"a"*64,"version":1,
          "expected_text":"СКИДКИ 50","byte_size":123,"target_path":str(root/"ad_layouts"/"layout.png")}
    snapshot={"enabled":True,"status":"queued","annotations":[],
              "layouts":[item],"xfeat_signature":xfeat_assets.MODEL_ID,
              "dino_signature":dino.SIGNATURE,"ocr_version":ocr.VERSION,
              "ocr_signature":"synthetic-paddle-sha"}
    monkeypatch.setattr(ad_pipeline,"DATA_DIR",root)
    monkeypatch.setattr(screen_search,"DATA_DIR",root)
    monkeypatch.setattr(ad_recognition,"DATA_DIR",root)
    monkeypatch.setattr(ad_pipeline,"load_model",lambda *_:rows)
    monkeypatch.setattr(ad_pipeline,"_layouts_pinned",lambda *_:[(item,Path(item["target_path"]))])
    monkeypatch.setattr(xfeat_assets,"load_model",lambda:object())
    monkeypatch.setattr(dino,"load",lambda:object())
    monkeypatch.setattr(ocr,"status",lambda:{"available":True})
    monkeypatch.setattr(ocr,"signature",lambda:"synthetic-paddle-sha")
    monkeypatch.setattr(ocr,"load",lambda:object())
    monkeypatch.setattr(ad_recognition,"_layout_vectors",
                        lambda *_:([(item,np.zeros(384,dtype="float32"),Path(item["target_path"]))],[]))
    corners=[{"x":20,"y":20},{"x":340,"y":20},{"x":340,"y":220},{"x":20,"y":220}]
    def fake_xfeat(_model,row,path,*_args):
        screen={"screen_id":screen_id,"screen_name":"LED",
                "annotation_id":str(uuid.uuid4()),"annotation_version":1,
                "status":"found","reference_id":str(uuid.uuid4()),
                "crop_box":{"x":20,"y":20,"width":320,"height":200},"corners":corners}
        with Image.open(path) as picture:rgb=np.asarray(picture.convert("RGB")).copy()
        return {"index":row["index"],"assigned_sam":sam,
                "image_width":rgb.shape[1],"image_height":rgb.shape[0],
                "model_signature":xfeat_assets.MODEL_ID,
                "status":"found","screens":[screen]},rgb
    monkeypatch.setattr(screen_search,"_analyse_photo",fake_xfeat)
    def fake_dino(_model,_ocr,screen,_run,index,*_args):
        return {"index":index,"screen_id":screen_id,"status":"matched",
                "candidate_id":layout_id,"review_required":False,
                "ocr":{"status":"confirmed","reason":"Контрольный текст совпадает"},
                "source_xfeat_signature":xfeat_assets.MODEL_ID,
                "source_annotation_version":1,"dino_signature":dino.SIGNATURE}
    monkeypatch.setattr(ad_recognition,"_identify",fake_dino)
    stages=[]
    class FakeJob:
        info={"id":run,"batch_id":batch,"reference_version":2,"reference_version_id":7,
              "ad_pipeline":snapshot,"models":{}}
        def stopped(self):return False
        def progress(self,model,stage,current,total,detail):stages.append((stage,current,total))
        def save(self):pass
    ad_pipeline.process(FakeJob())
    result=ad_pipeline.summary(run)
    assert result["status"]=="completed"
    assert result["screens_found"]==2 and result["recognized"]==2
    assert len(result["best"])==1
    assert result["best"][0]["index"]==0
    assert result["best"][0]["quality"]["status"]=="measured"
    assert "copy" not in result["best"][0]
    assert "best" in [stage for stage,_,_ in stages]
    assert snapshot["status"]=="completed"
    assert (root/"outputs"/run/"screen_search"/"0"/"result.json").is_file()
    assert (root/"outputs"/run/"ad_recognition"/"0"/(screen_id+".json")).is_file()
    archive_items=ad_pipeline.best_archive_entries(run,snapshot)
    assert len(archive_items)==2
    assert archive_items[0][1].startswith("Best_by_layout/")
