"""One integrated FIFO step: XFeat -> DINO -> OCR -> screen quality -> best.

Runs after MegaLoc publishes its immutable manifest and before ZIP publishes.
Run metadata was frozen at FIFO CLAIM, never read from the live libraries here.
"""
from __future__ import annotations
import hashlib
import json
import re
import time
from pathlib import Path
from fastapi import HTTPException
from PIL import Image
from app.config import DATA_DIR
from app.results.exporter import atomic_json
from app.results.repository import load_model
from app.ad_recognition import dino,ocr,quality,best
from app.screen_detection import xfeat_assets
from ..storage.paths import owned_file,run_dir
from . import screen_search,ad_recognition,ad_layouts

def _root(run_id):
    return run_dir(run_id,DATA_DIR/"outputs")/"ad_pipeline"

def digest(snapshot):
    payload={key:snapshot.get(key) for key in
             ("enabled","annotations","layouts","xfeat_signature","dino_signature","ocr_version","ocr_signature")}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,
                           separators=(",",":")).encode()).hexdigest()

def summary(run_id,*,internal=False):
    root=_root(run_id)
    path=root/"summary.json"
    if path.is_symlink() or root.is_symlink():
        raise HTTPException(404,"Небезопасный каталог анализа")
    if not path.is_file():
        return {"status":"not_processed","run_id":run_id,"best":[]}
    try:
        data=json.loads(path.read_text("utf-8"))
        if data["run_id"]!=run_id or data["status"]!="completed":
            raise ValueError("Unpublished summary")
        if internal:return data
        return {**data,"best":[
            {key:value for key,value in item.items() if key!="copy"}
            for item in data["best"]]}
    except (ValueError,OSError,KeyError) as exc:
        raise HTTPException(500,"Результат выбора лучших повреждён") from exc

def _layouts_pinned(snapshot):
    """Verify immutable original bytes, not the current active registry."""
    selected=[]
    for row in snapshot["layouts"]:
        path=ad_layouts._file(row)
        if path.stat().st_size!=row["byte_size"]:
            raise RuntimeError("Макет изменён после фиксации: "+row["name"])
        with path.open("rb") as stream:
            checksum=hashlib.file_digest(stream,"sha256").hexdigest()
        if checksum!=row["checksum"]:
            raise RuntimeError("SHA макета изменился после фиксации: "+row["name"])
        selected.append((row,path))
    return selected

def _references(snapshot):
    grouped={}
    for item in snapshot["annotations"]:
        a=dict(item)
        # Keep full member origin as captured at FIFO claim. No live library scans.
        grouped.setdefault(a["sam"],[]).append(a)
    return grouped

def process(job):
    snapshot=job.info.get("ad_pipeline",{})
    if not snapshot.get("enabled"):return
    run_id=job.info["id"]
    if (snapshot["xfeat_signature"]!=xfeat_assets.MODEL_ID or
        snapshot["dino_signature"]!=dino.SIGNATURE or
        snapshot["ocr_version"]!=ocr.VERSION):
        raise RuntimeError("Версия модели изменилась после фиксации задания")
    started=time.monotonic()
    snapshot["status"]="running"
    job.save()
    try:
        refs=_references(snapshot)
        layouts=_layouts_pinned(snapshot)
        rows=load_model(run_id,"megaloc")
        if job.stopped():raise InterruptedError("Обработка остановлена")
        # Models initialize ONCE per run inside the existing CPU-limited worker.
        model_x=xfeat_assets.load_model()
        model_d=dino.load()
        if not ocr.status()["available"]:
            raise RuntimeError("Проверенные OCR-веса отсутствуют")
        engine_ocr=ocr.load()
        vectors,errors=ad_recognition._layout_vectors(model_d,layouts)
        if errors or len(vectors)!=len(layouts):
            raise RuntimeError("Невозможно вычислить признаки всех закреплённых макетов")
        reference_features={}
        text_cache={}
        analyses=[]
        found=recognized=review_count=errors_count=0
        count=len(rows)
        for index,row in enumerate(rows):
            if job.stopped():raise InterruptedError("Обработка остановлена")
            sam=row.get("assigned_sam")
            started_photo=time.monotonic()
            try:
                source=owned_file(Path(row["query"]),DATA_DIR/"uploads"/job.info["batch_id"])
                screen_result,rgb=screen_search._analyse_photo(
                    model_x,{"index":index,"assigned_sam":sam},source,refs,reference_features)
                screen_search._save(run_id,index,screen_result,rgb)
            except (OSError,ValueError,HTTPException) as exc:
                screen_result={"index":index,"assigned_sam":sam,"status":"error",
                    "reason":str(exc)[:300],"screens":[]}
                screen_search._save(run_id,index,screen_result,None)
                errors_count+=1
            job.progress("ad_pipeline","screen_search",index+1,count,
                         f"XFeat · ФО {index+1}/{count}")
            for screen in screen_result.get("screens",[]):
                if screen.get("status")!="found":continue
                found+=1
                try:
                    item=ad_recognition._identify(
                        model_d,engine_ocr,screen,run_id,index,vectors,text_cache,errors)
                    crop=screen_search.crop(run_id,index,screen["screen_id"])
                    picture=ad_recognition._crop_screen(crop,screen)
                    full_size=(screen_result["image_width"],screen_result["image_height"])
                    item["quality"]=quality.assess(picture,screen,full_size)
                    item["assigned_sam"]=sam
                    item["screen_name"]=screen.get("screen_name","Экран")
                    chosen=next((r for r,_,_ in vectors
                                 if str(r["id"])==item.get("candidate_id")),None)
                    if chosen:
                        item["layout_name"]=chosen["name"]
                        item["layout_version"]=chosen["version"]
                        item["layout_checksum"]=chosen["checksum"]
                    item["elapsed_seconds"]=round(time.monotonic()-started_photo,2)
                    recognized+=int(item["status"]=="matched")
                    review_count+=int(item["review_required"])
                    analyses.append(item)
                except (OSError,ValueError,HTTPException) as exc:
                    item={"index":index,"screen_id":screen["screen_id"],
                          "status":"error","reason":str(exc)[:300],
                          "candidate_id":None,"review_required":True}
                    errors_count+=1
                ad_recognition._write(run_id,index,screen["screen_id"],item)
            job.progress("ad_pipeline","ad_recognition",index+1,count,
                         f"DINOv2 / OCR · ФО {index+1}/{count}")
        job.progress("ad_pipeline","quality",count,count,
                     "Оценка фокуса, пересвета и видимости экрана")
        winners=best.select(analyses)
        for item in winners:
            item["best_for_layout"]=True
            ad_recognition._write(run_id,item["index"],item["screen_id"],item)
        # Add archive entries referencing the immutable MegaLoc copies.
        best_items=[]
        for item in winners:
            original=rows[item["index"]]
            original_copy=owned_file(Path(original["copy"]),DATA_DIR/"outputs")
            rel=original_copy.relative_to(run_dir(run_id,DATA_DIR/"outputs"))
            best_items.append({**best.public(item),"copy":rel.as_posix()})
        manifest={"status":"completed","run_id":run_id,
                  "snapshot_digest":digest(snapshot),
                  "reference_version_id":job.info.get("reference_version_id"),
                  "reference_version":job.info.get("reference_version"),
                  "dino_signature":dino.SIGNATURE,"xfeat_signature":xfeat_assets.MODEL_ID,
                  "ocr_version":ocr.VERSION,"quality_version":quality.VERSION,
                  "total_photos":count,"screens_found":found,
                  "recognized":recognized,"review_required":review_count,
                  "errors":errors_count,"best":best_items,
                  "seconds":round(time.monotonic()-started,2)}
        atomic_json(_root(run_id)/"summary.json",manifest)
        snapshot.update(status="completed",screens_found=found,recognized=recognized,
                        review_required=review_count,best_count=len(best_items),
                        errors=errors_count,snapshot_digest=manifest["snapshot_digest"])
        job.info.setdefault("models",{})["ad_pipeline"]={
            "status":"completed","screens_found":found,"recognized":recognized,
            "best_count":len(best_items),"review_required":review_count}
        job.progress("ad_pipeline","best",1,1,
                     f"Выбрано лучших ФО: {len(best_items)}")
        job.save()
    except BaseException:
        snapshot["status"]="failed"
        job.save()
        raise

def best_archive_entries(run_id,snapshot):
    """Exact same saved selections for first ZIP and ZIP-only recovery."""
    if not snapshot.get("enabled"):return []
    document=summary(run_id,internal=True)
    if (document["status"]!="completed" or
        document["snapshot_digest"]!=digest(snapshot)):
        raise RuntimeError("Результат распознавания не готов для архива")
    from . import archives
    result=[]
    for item in document["best"]:
        source=owned_file(run_dir(run_id,DATA_DIR/"outputs")/item["copy"],DATA_DIR/"outputs")
        if not source.is_file():raise FileNotFoundError("Лучшее фото отсутствует")
        def label(value):
            safe=re.sub(r"[^\w\- ]+","_",str(value),flags=re.UNICODE).strip(" ._")
            return safe[:55] or "Без_названия"
        filename=f"{label(item.get('layout_name'))}_{str(item['screen_id'])[:8]}_FO{item['index']+1}_{source.name}"
        section="Review_required" if item.get("review_required") else "Best_by_layout"
        result.append((source,section+"/"+archives.archive_member(item["assigned_sam"],filename)))
    report=_root(run_id)/"summary.json"
    result.append((report,"Ad_recognition/summary.json"))
    return result
