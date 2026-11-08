"""Stage 4 streaming CPU passes: all XFeat first, DINO/OCR only afterwards.

Keeping model lifetimes disjoint avoids holding multiple neural networks in RAM
at once. Diagnostics stay under the run's existing output directory.
"""
from __future__ import annotations
import time
from pathlib import Path
from fastapi import HTTPException
from app.ad_recognition import quality
from ..storage.paths import owned_file
from . import screen_search,ad_recognition

def detect(job,model,rows,refs,run_id,data_root):
    features={}
    detections=[]
    failures=0
    total=len(rows)
    for index,row in enumerate(rows):
        if job.stopped():raise InterruptedError("Обработка остановлена")
        sam=row.get("assigned_sam")
        try:
            source=owned_file(Path(row["query"]),data_root/"uploads"/job.info["batch_id"])
            record,rgb=screen_search._analyse_photo(
                model,{"index":index,"assigned_sam":sam},source,refs,features)
            screen_search._save(run_id,index,record,rgb)
        except (OSError,ValueError,HTTPException) as exc:
            record={"index":index,"assigned_sam":sam,"status":"error",
                    "reason":str(exc)[:300],"screens":[]}
            screen_search._save(run_id,index,record,None)
            failures+=1
        for screen in record.get("screens",[]):
            if screen.get("status")=="found":
                detections.append((index,sam,screen,
                    (record["image_width"],record["image_height"])))
        job.progress("ad_pipeline","screen_search",index+1,total,
                     f"XFeat · ФО {index+1}/{total}")
    return detections,failures

def recognize(job,model,engine_ocr,detections,run_id,vectors,layout_errors):
    analyses=[]
    recognized=review_count=failures=0
    text_cache={}
    total=len(detections)
    if total==0:
        job.progress("ad_pipeline","ad_recognition",1,1,
                     "На ФО не найдены размеченные экраны")
        return analyses,recognized,review_count,failures
    for number,(index,sam,screen,full_size) in enumerate(detections,1):
        if job.stopped():raise InterruptedError("Обработка остановлена")
        started=time.monotonic()
        try:
            item=ad_recognition._identify(
                model,engine_ocr,screen,run_id,index,vectors,text_cache,layout_errors)
            crop=screen_search.crop(run_id,index,screen["screen_id"])
            picture=ad_recognition._crop_screen(crop,screen)
            item["quality"]=quality.assess(picture,screen,full_size)
            item["assigned_sam"]=sam
            item["screen_name"]=screen.get("screen_name","Экран")
            chosen=next((row for row,feature,path in vectors
                         if str(row["id"])==item.get("candidate_id")),None)
            if chosen:
                item["layout_name"]=chosen["name"]
                item["layout_version"]=chosen["version"]
                item["layout_checksum"]=chosen["checksum"]
            item["elapsed_seconds"]=round(time.monotonic()-started,2)
            recognized+=int(item["status"]=="matched")
            review_count+=int(item["review_required"])
            analyses.append(item)
        except (OSError,ValueError,HTTPException) as exc:
            item={"index":index,"screen_id":screen["screen_id"],
                  "status":"error","reason":str(exc)[:300],
                  "candidate_id":None,"review_required":True}
            failures+=1
        ad_recognition._write(run_id,index,screen["screen_id"],item)
        job.progress("ad_pipeline","ad_recognition",number,total,
                     f"DINOv2 / OCR · экран {number}/{total}")
    return analyses,recognized,review_count,failures
