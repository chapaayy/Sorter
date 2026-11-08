"""Explicit stage-2 analysis of completed MegaLoc runs; NO secondary queue."""
from __future__ import annotations
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from PIL import Image
from app.config import DATA_DIR
from app.results.exporter import atomic_json
from app.screen_detection.xfeat_assets import load_model,MODEL_ID
from app.screen_detection.features import oriented_image,extract,match
from app.screen_detection.cache import prepare_reference
from app.screen_detection.geometry import solve
from ..database import connect
from ..db.repositories import screen_annotations as records
from ..storage.paths import owned_file,run_dir
from .result_pages import iter_rows

def _output(run_id):
    folder=run_dir(run_id,DATA_DIR/"outputs")/"screen_search"
    if folder.is_symlink():
        raise HTTPException(404,"Недопустимый каталог анализа")
    return folder

def _index(index):
    if not 0<=index<=10000000:
        raise HTTPException(422,"Некорректный индекс ФО")
    return index

def saved(run_id:str,index:int)->dict:
    _index(index)
    folder=_output(run_id)/str(index)
    if folder.is_symlink():
        raise HTTPException(404,"Недопустимый каталог анализа")
    path=folder/"result.json"
    if not path.is_file() or path.is_symlink():
        return {"status":"not_processed","index":index,"screens":[]}
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError,ValueError) as exc:
        raise HTTPException(500,"Повреждён результат поиска экрана") from exc

def crop(run_id:str,index:int,screen_id:uuid.UUID)->Path:
    item=saved(run_id,index)
    if not any(s.get("screen_id")==str(screen_id) and s.get("status")=="found"
               for s in item.get("screens",[])):
        raise HTTPException(404,"Экран не найден")
    root=_output(run_id)/str(index)
    path=owned_file(root/(str(screen_id)+".png"),root)
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404,"Фрагмент не найден")
    return path

def _run_rows(run_id,limit=None):
    with connect() as db:
        row=db.execute("""SELECT j.batch_id,j.status,b.delete_state FROM jobs j
            JOIN batches b ON b.id=j.batch_id WHERE j.id=%s""",(run_id,)).fetchone()
    if not row or row["status"] not in ("completed","completed_with_errors") or row["delete_state"]!="active":
        raise ValueError("Нужен завершённый MegaLoc run активной партии")
    root=DATA_DIR/"uploads"/str(row["batch_id"])
    for result in iter_rows(run_id):
        if limit is not None and result["index"]>=limit:break
        filename=Path(result["query"])
        path=owned_file(filename,root)
        if not path.is_file() or path.is_symlink():
            raise ValueError("Исходная ФО отсутствует или недоступна")
        yield result,path

def _screen_data(sam):
    with connect() as db:
        return [dict(r) for r in records.detection_references(db,sam)]

def _analyse_photo(model,row,path:Path,reference_groups:dict,reference_features:dict):
    sam=row.get("assigned_sam")
    result={"index":row["index"],"assigned_sam":sam,"status":"not_found",
            "reason":"","screens":[],"model_signature":MODEL_ID}
    if not sam or sam.startswith("_"):
        result.update(status="unknown_construction",reason="MegaLoc не назначил конструкцию")
        return result,None
    if sam not in reference_groups:
        reference_groups[sam]=_screen_data(sam)
    annotations=reference_groups[sam]
    if not annotations:
        result.update(status="no_annotations",reason="Для этой конструкции нет актуальных разметок")
        return result,None
    rgb=oriented_image(path)
    height,width=rgb.shape[:2]
    result["image_width"]=width;result["image_height"]=height
    query=extract(model,rgb)
    best={}
    for a in annotations:
        sid=str(a["screen_id"])
        candidate={"screen_id":sid,"screen_name":a["screen_name"],
                   "annotation_id":str(a["id"]),"reference_id":str(a["reference_id"]),
                   "annotation_version":a["version"],"status":"not_found",
                   "reason":"Не проверено"}
        try:
            key=(str(a["id"]),int(a["version"]))
            if key not in reference_features:
                refpath=owned_file(Path(a["target_path"]),DATA_DIR/"references"/sam)
                if not refpath.is_file():raise ValueError("Файл Образца отсутствует")
                reference_features[key]=prepare_reference(model,a,refpath)
            prepared=reference_features[key]
            refpoints,photopoints,sides=match(prepared,query)
            candidate.update(solve(refpoints,photopoints,sides,a["corners"],(width,height)))
        except (ValueError,OSError) as exc:
            candidate.update(status="not_found",reason="Образец/признаки: "+str(exc))
        current=best.get(sid)
        rank=lambda v:(v["status"]=="found",int(v.get("inliers",0)),
                       -float(v.get("reprojection_error_px") or 1e6))
        if current is None or rank(candidate)>rank(current):
            best[sid]=candidate
    result["screens"]=list(best.values())
    found=[s for s in result["screens"] if s["status"]=="found"]
    if found:
        result.update(status="found",reason="Экраны подтверждены геометрически")
    else:
        result["reason"]="XFeat не подтвердил геометрию экранов"
    return result,rgb

def _save(run_id:str,index:int,result:dict,rgb):
    root=_output(run_id)
    root.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix="."+str(index)+".",dir=root))
    target=root/str(index)
    try:
        if rgb is not None:
            for s in result.get("screens",[]):
                if s["status"]!="found":continue
                corners=s["corners"]
                x0=max(0,int(min(p["x"] for p in corners)))
                y0=max(0,int(min(p["y"] for p in corners)))
                x1=min(rgb.shape[1],int(max(p["x"] for p in corners)+.9999))
                y1=min(rgb.shape[0],int(max(p["y"] for p in corners)+.9999))
                if x1<=x0 or y1<=y0:
                    s.update(status="not_found",reason="Пустая область вырезания")
                    continue
                Image.fromarray(rgb[y0:y1,x0:x1]).save(work/(s["screen_id"]+".png"),format="PNG")
                s["crop_box"]={"x":x0,"y":y0,"width":x1-x0,"height":y1-y0}
        atomic_json(work/"result.json",result)
        if target.exists():
            if target.is_symlink():raise ValueError("Недопустимый каталог результатов")
            shutil.rmtree(target)
        os.replace(work,target)
    finally:
        if work.exists():shutil.rmtree(work)

def analyze_run(run_id:str,*,limit:int|None=None,progress=None)->dict:
    """Manual test command only. Current reference state is recorded in diagnostics.

    Stage 4 will pin annotation/model versions at actual FIFO claim; stage 2
    deliberately does not alter the active FIFO or ZIP lifecycle.
    """
    if limit is not None and not 1<=limit<=100000:
        raise ValueError("limit вне допустимого диапазона")
    # Refuse invalid runs before attempting expensive model initialization.
    rows=_run_rows(run_id,limit)
    try:first=next(rows)
    except StopIteration:return {"run_id":run_id,"processed":0,"found":0}
    model=load_model()
    grouped={};cached={}
    processed=found=0
    from itertools import chain
    for row,path in chain((first,),rows):
        started=time.perf_counter()
        try:
            item,rgb=_analyse_photo(model,row,path,grouped,cached)
        except (OSError,ValueError) as exc:
            item={"index":row["index"],"assigned_sam":row.get("assigned_sam"),
                  "status":"error","reason":str(exc),"screens":[],"model_signature":MODEL_ID}
            rgb=None
        item["elapsed_seconds"]=round(time.perf_counter()-started,2)
        _save(run_id,row["index"],item,rgb)
        processed+=1;found+=int(item["status"]=="found")
        if progress:progress(item)
    return {"run_id":run_id,"processed":processed,"found":found,
            "model_signature":MODEL_ID}

def prune_old_reference_cache()->dict:
    """Explicit maintenance, retaining all live annotation versions."""
    from app.screen_detection.cache import key,prune_inactive
    with connect() as db:
        live=records.cache_annotations(db)
    return prune_inactive({key(dict(item)) for item in live})
