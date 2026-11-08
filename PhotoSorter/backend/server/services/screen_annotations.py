"""Construction-scoped screen geometry and original-image checks; no SQL here."""
from __future__ import annotations
import uuid
from pathlib import Path
from fastapi import HTTPException
from PIL import Image,UnidentifiedImageError
from app.config import DATA_DIR
from app.photos.labels import check_label
from ..database import connect
from ..db.repositories import screen_annotations as records
from ..storage.paths import owned_file
from .screen_geometry import validate

def _sam(sam:str)->str:
    try:
        if check_label(sam)!=sam:
            raise ValueError("Неверное название конструкции")
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    return sam

def _reference(db,sam:str,reference_id:uuid.UUID)->dict:
    row=records.reference(db,sam,reference_id)
    if not row or not row["checksum"] or not row["target_path"]:
        raise HTTPException(404,"Опубликованный Образец не найден")
    return row

def _metadata(row:dict)->dict:
    try:
        path=owned_file(Path(row["target_path"]),DATA_DIR/"references"/row["sam"])
        with Image.open(path) as image:
            width,height=image.size
            # SVG canvas and browser viewer use EXIF-oriented pixel coordinates.
            if image.getexif().get(274,1) in (5,6,7,8):
                width,height=height,width
    except (OSError,ValueError,UnidentifiedImageError) as exc:
        raise HTTPException(422,"Не удалось прочитать размеры исходного Образца") from exc
    return {"reference_id":str(row["id"]),"width":width,"height":height,
            "source_sha256":row["checksum"]}

def metadata(sam:str,reference_id:uuid.UUID)->dict:
    sam=_sam(sam)
    with connect() as db:
        return _metadata(_reference(db,sam,reference_id))

def list_screens(sam:str)->dict:
    sam=_sam(sam)
    with connect() as db:
        if not records.has_construction(db,sam):
            raise HTTPException(404,"Конструкция не найдена")
        screens=records.list_screens(db,sam)
        annotations=records.list_annotations(db,sam)
    by_screen={str(screen["id"]):{"id":str(screen["id"]),"name":screen["name"],
               "annotations":[]} for screen in screens}
    for item in annotations:
        by_screen[str(item["screen_id"])]["annotations"].append({
            "id":str(item["id"]),"reference_id":str(item["reference_id"]),
            "corners":item["corners"],"band_width_px":item["band_width_px"],
            "image_width":item["image_width"],"image_height":item["image_height"],
            "source_sha256":item["source_sha256"],"version":item["version"]})
    return {"screens":list(by_screen.values())}

def _annotate(row:dict,corners:list[dict],band:float)->tuple[dict,list[dict]]:
    info=_metadata(row)
    try:
        points=validate(corners,band,info["width"],info["height"])
    except (ValueError,TypeError,KeyError) as exc:
        raise HTTPException(422,str(exc)) from exc
    return info,points

def create(sam:str,reference_id:uuid.UUID,screen_id:uuid.UUID|None,
           screen_name:str|None,corners:list[dict],band_width_px:float)->dict:
    sam=_sam(sam)
    with connect() as db:
        row=_reference(db,sam,reference_id)
        info,points=_annotate(row,corners,band_width_px)
        if screen_id is None:
            name=(screen_name or "").strip()
            if not 1<=len(name)<=80:
                raise HTTPException(422,"Укажите название экрана (до 80 символов)")
            screen_id=uuid.uuid4()
            records.insert_screen(db,screen_id,sam,name)
        elif not records.has_screen(db,screen_id,sam):
            raise HTTPException(404,"Экран этой конструкции не найден")
        identifier=uuid.uuid4()
        item=records.insert_annotation(db,identifier,screen_id,reference_id,points,
                                       band_width_px,info)
        if not item:
            raise HTTPException(409,"Экран уже размечен на этом Образце. Откройте изменение разметки")
    return {"id":str(identifier),"screen_id":str(screen_id),"version":item["version"]}

def update(sam:str,annotation_id:uuid.UUID,version:int,corners:list[dict],
           band_width_px:float)->dict:
    sam=_sam(sam)
    with connect() as db:
        item=records.lock_annotation(db,annotation_id,sam)
        if not item:
            raise HTTPException(404,"Разметка не найдена")
        if item["version"]!=version:
            raise HTTPException(409,"Разметка изменена в другой вкладке. Обновите данные")
        row=_reference(db,sam,item["reference_id"])
        info,points=_annotate(row,corners,band_width_px)
        if info["source_sha256"]!=item["source_sha256"]:
            raise HTTPException(409,"Исходный Образец изменился. Создайте новую разметку")
        new=records.revise_annotation(db,annotation_id,points,band_width_px)
    return {"id":str(new["id"]),"screen_id":str(item["screen_id"]),"version":new["version"]}

def remove_annotation(sam:str,annotation_id:uuid.UUID)->dict:
    sam=_sam(sam)
    with connect() as db:
        if not records.delete_annotation(db,annotation_id,sam):
            raise HTTPException(404,"Разметка не найдена")
    return {"deleted":True}

def remove_screen(sam:str,screen_id:uuid.UUID)->dict:
    sam=_sam(sam)
    with connect() as db:
        if not records.delete_screen(db,screen_id,sam):
            raise HTTPException(404,"Экран не найден")
    return {"deleted":True}
