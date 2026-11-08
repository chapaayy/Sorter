"""One integrated FIFO step: XFeat -> DINO -> OCR -> screen quality -> best.

Runs after MegaLoc publishes its immutable manifest and before ZIP publishes.
Run metadata was frozen at FIFO CLAIM, never read from the live libraries here.
"""
from __future__ import annotations
import gc
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
from . import screen_search,ad_recognition,ad_layouts,ad_pipeline_steps

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
        snapshot["ocr_version"]!=ocr.VERSION or
        snapshot["ocr_signature"]!=ocr.signature()):
        raise RuntimeError("Версия модели изменилась после фиксации задания")
    started=time.monotonic()
    snapshot["status"]="running"
    job.save()
    try:
        refs=_references(snapshot)
        layouts=_layouts_pinned(snapshot)
        rows=load_model(run_id,"megaloc")
        if job.stopped():raise InterruptedError("Обработка остановлена")
        # Process every photo with XFeat, then release its network and
        # reference descriptors before loading DINOv2 and PP-OCRv5.
        model_x=xfeat_assets.load_model()
        try:
            detections,errors_count=ad_pipeline_steps.detect(
                job,model_x,rows,refs,run_id,DATA_DIR)
        finally:
            del model_x
            gc.collect()
        found=len(detections)
        count=len(rows)
        analyses=[]
        recognized=review_count=0
        if found:
            model_d=dino.load()
            if not ocr.status()["available"]:
                raise RuntimeError("Проверенные OCR-веса отсутствуют")
            engine_ocr=ocr.load()
            try:
                vectors,errors=ad_recognition._layout_vectors(model_d,layouts)
                if errors or len(vectors)!=len(layouts):
                    raise RuntimeError("Невозможно вычислить признаки всех закреплённых макетов")
                analyses,recognized,review_count,failed_recognition=ad_pipeline_steps.recognize(
                    job,model_d,engine_ocr,detections,run_id,vectors,errors)
                errors_count+=failed_recognition
            finally:
                del model_d
                del engine_ocr
                gc.collect()
        else:
            job.progress("ad_pipeline","ad_recognition",1,1,
                         "Нет геометрически подтверждённых экранов")
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
                  "ocr_version":ocr.VERSION,"ocr_signature":snapshot["ocr_signature"],
                  "quality_version":quality.VERSION,
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
