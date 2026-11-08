"""Manual Stage 3 DINOv2 + OCR over CONFIRMED stage-2 XFeat crops only."""
from __future__ import annotations
import json
import os
import time
import uuid
from pathlib import Path
import cv2
import numpy as np
from fastapi import HTTPException
from PIL import Image,ImageOps
from app.config import DATA_DIR
from app.results.exporter import atomic_json
from app.ad_recognition import dino,embedding_cache,scoring,ocr
from ..database import connect
from ..storage.paths import run_dir,owned_file
from . import ad_layouts,screen_search,operations
from .result_pages import iter_rows

def _folder(run_id:str)->Path:
    root=run_dir(run_id,DATA_DIR/"outputs")/"ad_recognition"
    if root.is_symlink():raise HTTPException(404,"Недопустимый каталог результатов")
    return root

def _path(run_id,index,screen_id):
    if not 0<=index<=10000000:raise HTTPException(422,"Недопустимый индекс ФО")
    identifier=uuid.UUID(str(screen_id))
    return _folder(run_id)/str(index)/(str(identifier)+".json")

def result(run_id,index,screen_id):
    path=_path(run_id,index,screen_id)
    if path.is_symlink():raise HTTPException(404,"Недоступный результат")
    if not path.is_file():
        return {"index":index,"screen_id":str(screen_id),"status":"not_processed"}
    try:return json.loads(path.read_text("utf-8"))
    except (ValueError,OSError) as exc:
        raise HTTPException(500,"Результат распознавания повреждён") from exc

def _crop_screen(image_path:Path,screen:dict)->Image.Image:
    """Mask background OUTSIDE XFeat quad, preserving unwarped screen pixels."""
    with Image.open(image_path) as photo:
        rgb=np.array(photo.convert("RGB"),dtype=np.uint8)
    box=screen["crop_box"]
    quad=np.array([[corner["x"]-box["x"],corner["y"]-box["y"]]
                   for corner in screen["corners"]],dtype=np.float32)
    mask=np.zeros(rgb.shape[:2],dtype="uint8")
    cv2.fillConvexPoly(mask,np.rint(quad).astype("int32"),255)
    rgb[mask==0]=0
    return Image.fromarray(rgb)

def _layout_vectors(model,layouts):
    available=[];errors=[]
    for row,path in layouts:
        try:
            # Prepared by FIFO ahead of the FO run, never inferred on demand.
            feature=embedding_cache.prepared(row)
            available.append((row,feature,path))
        except (ValueError,OSError,HTTPException) as exc:
            errors.append({"layout_id":str(row["id"]),"reason":str(exc)})
    return available,errors

def _ocr_check(engine,layout:dict,layout_path:Path,picture:Image.Image,
               layout_text_cache:dict,observed:list[dict]|None=None)->dict:
    if engine is None:
        return {"status":"unavailable","reason":"PP-OCRv5 ещё не установлен"}
    try:
        expected=layout.get("ocr_text")
        if expected is None:
            expected=(layout.get("ocr_corrected_text") if
                layout.get("ocr_corrected_text") is not None else
                layout["expected_text"] or layout.get("normalized_text",""))
        lines=observed if observed is not None else ocr.read(engine,picture)
        return ocr.confirm(expected,lines)
    except Exception as exc:
        # Optional verifier failure NEVER erases or rewrites DINO's decision.
        return {"status":"error","reason":"Ошибка OCR: "+str(exc)[:180]}

def _identify(model,ocr_engine,screen,run_id,index,embeddings,
              layout_text_cache,layout_errors,matching_threshold=scoring.MIN_SIMILARITY,
              screen_feature=None,group_match=None,ocr_entry=None):
    sid=str(screen["screen_id"])
    filename=screen_search.crop(run_id,index,uuid.UUID(sid))
    picture=_crop_screen(filename,screen)
    query=screen_feature if screen_feature is not None else dino.embed(model,picture)
    ranking=scoring.rank(query,[(row,feature) for row,feature,_ in embeddings],
                         minimum=matching_threshold)
    # Group matching is provisional. Preserve the full individual ranking to
    # expose weak members or a different per-screen favorite without a second
    # DINO inference. The group decision remains the primary visual candidate.
    decision=group_match if group_match is not None else ranking
    candidate_id=decision["candidate_id"]
    # OCR evidence is captured for EVERY detected screen, regardless of
    # whether DINOv2 could assign a layout. It never changes the visual ID.
    observed=[]
    if ocr_entry is not None:
        observed=ocr_entry.get("lines",[])
        observation=ocr.describe(observed)
        if ocr_entry.get("error"):
            observation={**observation,"status":"error",
                         "reason":"OCR: "+str(ocr_entry["error"])[:180]}
    elif ocr_engine is None:
        observation={**ocr.describe([]),"status":"unavailable",
                     "reason":"PaddleOCR не установлен"}
    else:
        try:
            observed=ocr.read(ocr_engine,picture)
            observation=ocr.describe(observed)
        except Exception as exc:
            observation={**ocr.describe([]),"status":"error",
                         "reason":"OCR: "+str(exc)[:180]}
    result={"index":index,"screen_id":sid,"status":decision["status"],
            "reason":decision["reason"],"candidate_id":candidate_id,
            "top":ranking["top"],"margin":ranking.get("margin"),
            "thresholds":ranking.get("thresholds"),"layout_errors":layout_errors,
            "source_annotation_id":screen.get("annotation_id"),
            "source_annotation_version":screen.get("annotation_version"),
            "source_xfeat_signature":screen_search.saved(run_id,index).get("model_signature"),
            "dino_signature":dino.SIGNATURE,"ocr_version":ocr.VERSION,
            "ocr":{"status":"not_run","reason":"Нет кандидата DINOv2"},
            "ocr_observation":observation,
            "review_required":decision["status"]!="matched"}
    if group_match is not None:
        # The group's DINO score determines its visual match. A blurry or
        # uninformative individual frame is not a manual-review error.
        result["visual_group_id"]=group_match["group_id"]
        result["group_match"]={
            key:group_match.get(key) for key in
            ("status","reason","candidate_id","best_score","margin",
             "matching_threshold","candidate_count","method",
             "decision_version","ocr_leader_id","visual_leader_id",
             "ocr_margin","ocr_conflicting_members","evidence_member_count")}
        result["member_match"]={key:ranking.get(key) for key in
                                ("status","reason","candidate_id","margin","thresholds")}
    if candidate_id and decision["status"] in ("matched","uncertain"):
        selected=next((row,path) for row,feature,path in embeddings
                      if str(row["id"])==candidate_id)
        check=_ocr_check(ocr_engine,selected[0],selected[1],picture,
                         layout_text_cache,observed)
        # A text match cannot confirm a layout if the very same readable
        # photo also confirms another visually eligible layout. Evaluate all
        # individual DINO candidates above the frozen threshold using the
        # *same* OCR lines; never run another network or replace candidate_id.
        if (check["status"]=="confirmed" and observed
                and not (group_match and group_match.get("decision_version"))):
            alternatives=[]
            visual_options={item["id"] for item in ranking["top"]
                            if item["score"]>=matching_threshold
                            and item["id"]!=candidate_id}
            for row,feature,path in embeddings:
                alt_id=str(row["id"])
                if alt_id not in visual_options:
                    continue
                alt_text=row.get("ocr_text")
                if alt_text is None:
                    alt_text=(row.get("ocr_corrected_text") if
                              row.get("ocr_corrected_text") is not None else
                              row.get("expected_text") or row.get("normalized_text",""))
                if alt_text and ocr.confirm(alt_text,observed)["status"]=="confirmed":
                    alternatives.append(alt_id)
            if alternatives:
                check={**check,"status":"probable",
                       "ambiguous_candidates":alternatives,
                       "reason":"Прочитанный текст подходит нескольким визуально совместимым макетам"}
        result["ocr"]=check
        # OCR is used as scoring evidence, never a mandatory gate for a
        # DINO-matched group. Unreadable text means "visual-only", not review.
        result["verification_basis"]=(
            "visual_and_ocr" if check["status"]=="confirmed" else "visual_only"
        )
    result["classification"]=(
        "unidentified" if result["status"]!="matched" or not candidate_id
        else "confirmed" if result["ocr"].get("status")=="confirmed"
             and not result["review_required"]
        else "probable")
    result["ocr_independent"]=True
    return result

def _write(run_id,index,screen_id,item):
    path=_path(run_id,index,screen_id)
    path.parent.mkdir(parents=True,exist_ok=True)
    atomic_json(path,item)

def analyze_run(run_id:str,*,limit:int|None=None,start_index:int=0,
                progress=None)->dict:
    """No new queue, no writes to published MegaLoc results/ZIP."""
    if limit is not None and not 1<=limit<=100000:
        raise ValueError("limit вне допустимого диапазона")
    if not 0<=start_index<=10000000:raise ValueError("Invalid start-index")
    with connect() as db:
        job=db.execute("""SELECT j.batch_id,j.status,b.delete_state,j.snapshot FROM jobs j
            JOIN batches b ON b.id=j.batch_id WHERE j.id=%s""",(run_id,)).fetchone()
    if not job or job["status"] not in ("completed","completed_with_errors") or job["delete_state"]!="active":
        raise ValueError("Нужен завершённый MegaLoc run активной партии")
    if (job["snapshot"] or {}).get("ad_pipeline",{}).get("enabled"):
        raise ValueError("Этот запуск уже ведёт единый конвейер. Повторный DINO через CLI запрещён")
    token=operations.start(job["batch_id"],"ad-recognition")
    try:
        layouts=ad_layouts.active_files()
        if not layouts:
            raise ValueError("Сначала загрузите хотя бы один активный рекламный макет")
        model=dino.load()
        embeddings,layout_errors=_layout_vectors(model,layouts)
        if not embeddings:
            raise ValueError("Не удалось подготовить признаки рекламных макетов")
        ocr_engine=None
        ocr_problem=None
        if ocr.status()["available"]:
            try:ocr_engine=ocr.load()
            except Exception as exc:ocr_problem=str(exc)
        layout_text_cache={}
        total=matched=review=skipped=0
        last_heartbeat=time.monotonic()
        for row in iter_rows(run_id):
            index=row["index"]
            if index<start_index:continue
            if limit is not None and index>=start_index+limit:break
            data=screen_search.saved(run_id,index)
            for screen in data.get("screens",[]):
                if screen.get("status")!="found":continue
                sid=screen["screen_id"]
                started=time.perf_counter()
                try:item=_identify(model,ocr_engine,screen,run_id,index,embeddings,
                                   layout_text_cache,layout_errors)
                except (OSError,ValueError,HTTPException) as exc:
                    item={"index":index,"screen_id":sid,"status":"error",
                          "reason":str(exc),"candidate_id":None,"top":[],
                          "review_required":True}
                if ocr_problem and item.get("ocr",{}).get("status")=="unavailable":
                    item["ocr"]["reason"]="OCR не запустился: "+ocr_problem[:180]
                item["elapsed_seconds"]=round(time.perf_counter()-started,2)
                _write(run_id,index,sid,item)
                total+=1;matched+=int(item["status"]=="matched")
                review+=int(item.get("review_required",False))
                if progress:progress(item)
                if time.monotonic()-last_heartbeat>25:
                    operations.heartbeat(token)
                    last_heartbeat=time.monotonic()
            if not any(s.get("status")=="found" for s in data.get("screens",[])):
                skipped+=1
        return {"run_id":run_id,"screens":total,"matched":matched,
                "review_required":review,"photos_without_confirmed_screen":skipped,
                "dino_signature":dino.SIGNATURE,"ocr_available":ocr_engine is not None}
    finally:operations.finish(token)

def prune_old_layout_cache()->dict:
    """Explicit cleanup only: retain current and disabled layout embeddings."""
    from ..db.repositories import ad_layouts as registry
    with connect() as db:
        rows=registry.all_rows(db,False)
        prepared=db.execute("SELECT checksum FROM ad_layout_prepared_cache").fetchall()
    checksums={row["checksum"] for row in rows}
    checksums.update(row["published_snapshot"]["checksum"] for row in rows
                     if row["published_snapshot"])
    checksums.update(entry["checksum"] for entry in prepared)
    return embedding_cache.prune_inactive({embedding_cache.key(checksum)
                                           for checksum in checksums})
