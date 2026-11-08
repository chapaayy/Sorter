"""CRUD for construction-scoped screen annotations; no ML or queue mutations."""
from __future__ import annotations
import uuid
from pathlib import Path
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from app.config import DATA_DIR
from app.photos.labels import check_label
from ..database import connect
from ..storage.paths import owned_file
from .screen_geometry import validate

def _sam(sam: str) -> str:
    try:
        if check_label(sam) != sam:
            raise ValueError("Неверное название конструкции")
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    return sam

def _reference(db, sam: str, reference_id: uuid.UUID) -> dict:
    row = db.execute("""SELECT id,sam,checksum,target_path FROM uploads
        WHERE id=%s AND kind='reference' AND finalized AND sam=%s""",
        (reference_id,sam)).fetchone()
    if not row or not row["checksum"] or not row["target_path"]:
        raise HTTPException(404,"Опубликованный Образец не найден")
    return row

def _metadata(row: dict) -> dict:
    try:
        path = owned_file(Path(row["target_path"]),DATA_DIR/"references"/row["sam"])
        with Image.open(path) as image:
            width,height = image.size
            # Browsers display the EXIF-oriented image. Match that pixel space.
            if image.getexif().get(274,1) in (5,6,7,8):
                width,height = height,width
    except (OSError,ValueError,UnidentifiedImageError) as exc:
        raise HTTPException(422,"Не удалось прочитать размеры исходного Образца") from exc
    return {"reference_id":str(row["id"]),"width":width,"height":height,
            "source_sha256":row["checksum"]}

def metadata(sam: str, reference_id: uuid.UUID) -> dict:
    sam=_sam(sam)
    with connect() as db:
        return _metadata(_reference(db,sam,reference_id))

def list_screens(sam: str) -> dict:
    sam=_sam(sam)
    with connect() as db:
        if not db.execute("SELECT 1 FROM reference_constructions WHERE sam=%s",(sam,)).fetchone():
            raise HTTPException(404,"Конструкция не найдена")
        screens=db.execute("""SELECT id,name FROM reference_screens
            WHERE sam=%s ORDER BY created_at,id""",(sam,)).fetchall()
        annotations=db.execute("""SELECT a.id,a.screen_id,a.reference_id,
            a.corners,a.band_width_px,a.source_sha256,a.image_width,a.image_height,
            a.version FROM reference_screen_annotations a
            JOIN reference_screens s ON s.id=a.screen_id WHERE s.sam=%s
            ORDER BY a.created_at,a.id""",(sam,)).fetchall()
    by_screen={str(screen["id"]):{"id":str(screen["id"]),"name":screen["name"],
               "annotations":[]} for screen in screens}
    for item in annotations:
        by_screen[str(item["screen_id"])]["annotations"].append({
            "id":str(item["id"]),"reference_id":str(item["reference_id"]),
            "corners":item["corners"],"band_width_px":item["band_width_px"],
            "image_width":item["image_width"],"image_height":item["image_height"],
            "source_sha256":item["source_sha256"],"version":item["version"]})
    return {"screens":list(by_screen.values())}

def _annotate(db, row: dict, corners: list[dict], band: float) -> tuple[dict,list[dict]]:
    info=_metadata(row)
    try:
        points=validate(corners,band,info["width"],info["height"])
    except (ValueError,TypeError,KeyError) as exc:
        raise HTTPException(422,str(exc)) from exc
    return info,points

def create(sam: str, reference_id: uuid.UUID, screen_id: uuid.UUID | None,
           screen_name: str | None, corners: list[dict], band_width_px: float) -> dict:
    sam=_sam(sam)
    with connect() as db:
        row=_reference(db,sam,reference_id)
        info,points=_annotate(db,row,corners,band_width_px)
        if screen_id is None:
            name=(screen_name or "").strip()
            if not 1<=len(name)<=80:
                raise HTTPException(422,"Укажите название экрана (до 80 символов)")
            screen_id=uuid.uuid4()
            db.execute("INSERT INTO reference_screens(id,sam,name) VALUES (%s,%s,%s)",
                       (screen_id,sam,name))
        elif not db.execute("SELECT 1 FROM reference_screens WHERE id=%s AND sam=%s",
                            (screen_id,sam)).fetchone():
            raise HTTPException(404,"Экран этой конструкции не найден")
        identifier=uuid.uuid4()
        try:
            item=db.execute("""INSERT INTO reference_screen_annotations
                (id,screen_id,reference_id,corners,band_width_px,source_sha256,image_width,image_height)
                VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
                ON CONFLICT(screen_id,reference_id) DO NOTHING
                RETURNING id,version""",
                (identifier,screen_id,reference_id,__import__("json").dumps(points),
                 band_width_px,info["source_sha256"],info["width"],info["height"])).fetchone()
        except Exception:
            raise
        if not item:
            raise HTTPException(409,"Экран уже размечен на этом Образце. Откройте изменение разметки")
    return {"id":str(identifier),"screen_id":str(screen_id),"version":item["version"]}

def update(sam: str, annotation_id: uuid.UUID, version: int,
           corners: list[dict], band_width_px: float) -> dict:
    sam=_sam(sam)
    with connect() as db:
        item=db.execute("""SELECT a.*,s.sam FROM reference_screen_annotations a
            JOIN reference_screens s ON s.id=a.screen_id
            WHERE a.id=%s AND s.sam=%s FOR UPDATE OF a""",(annotation_id,sam)).fetchone()
        if not item:
            raise HTTPException(404,"Разметка не найдена")
        if item["version"]!=version:
            raise HTTPException(409,"Разметка изменена в другой вкладке. Обновите данные")
        row=_reference(db,sam,item["reference_id"])
        info,points=_annotate(db,row,corners,band_width_px)
        if info["source_sha256"]!=item["source_sha256"]:
            raise HTTPException(409,"Исходный Образец изменился. Создайте новую разметку")
        new=db.execute("""UPDATE reference_screen_annotations
            SET corners=%s::jsonb,band_width_px=%s,version=version+1,updated_at=now()
            WHERE id=%s RETURNING id,version""",
            (__import__("json").dumps(points),band_width_px,annotation_id)).fetchone()
    return {"id":str(new["id"]),"screen_id":str(item["screen_id"]),"version":new["version"]}

def remove_annotation(sam: str, annotation_id: uuid.UUID) -> dict:
    sam=_sam(sam)
    with connect() as db:
        item=db.execute("""DELETE FROM reference_screen_annotations a
            USING reference_screens s WHERE a.id=%s AND a.screen_id=s.id AND s.sam=%s
            RETURNING a.id""",(annotation_id,sam)).fetchone()
        if not item:
            raise HTTPException(404,"Разметка не найдена")
    return {"deleted":True}

def remove_screen(sam: str, screen_id: uuid.UUID) -> dict:
    sam=_sam(sam)
    with connect() as db:
        item=db.execute("DELETE FROM reference_screens WHERE id=%s AND sam=%s RETURNING id",
                        (screen_id,sam)).fetchone()
        if not item:
            raise HTTPException(404,"Экран не найден")
    return {"deleted":True}
