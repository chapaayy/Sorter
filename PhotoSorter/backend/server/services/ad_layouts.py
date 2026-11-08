"""Safe immutable ad-layout image storage and independent metadata revisions."""
from __future__ import annotations
import hashlib
import io
import os
import tempfile
import uuid
from pathlib import Path
from fastapi import HTTPException
from PIL import Image,UnidentifiedImageError
from app.config import DATA_DIR
from ..database import connect
from ..db.repositories import ad_layouts as records
from ..storage.paths import owned_file

ROOT=DATA_DIR/"ad_layouts"
MAX_BYTES=20*1024*1024
MAX_PIXELS=40_000_000
FORMATS={"JPEG":".jpg","PNG":".png","WEBP":".webp"}

def _name(value,limit,label):
    value=(value or "").strip()
    if not 1<=len(value)<=limit:raise HTTPException(422,label)
    return value

def _text(value):
    value=(value or "").strip()
    if len(value)>1000:raise HTTPException(422,"Текст макета не более 1000 символов")
    return value

def _picture(data:bytes)->str:
    if not data or len(data)>MAX_BYTES:
        raise HTTPException(413,"Макет должен быть не больше 20 МиБ")
    try:
        with Image.open(io.BytesIO(data)) as picture:
            width,height=picture.size
            if width<32 or height<32 or width*height>MAX_PIXELS:
                raise HTTPException(422,"Некорректные размеры макета")
            fmt=picture.format
            if fmt not in FORMATS:raise HTTPException(422,"Разрешены только JPG, PNG и WEBP")
            picture.verify()
    except (OSError,ValueError,UnidentifiedImageError) as exc:
        raise HTTPException(422,"Файл не является корректным изображением") from exc
    return FORMATS[fmt]

def _public(row):
    return {"id":str(row["id"]),"name":row["name"],"filename":row["filename"],
            "checksum":row["checksum"],"byte_size":row["byte_size"],
            "expected_text":row["expected_text"],"active":row["active"],
            "version":row["version"],"image_url":"/api/ad-layouts/"+str(row["id"])+"/image"}

def list_layouts(active_only=False):
    with connect() as db: rows=records.all_rows(db,active_only)
    return {"layouts":[_public(row) for row in rows],"total":len(rows)}

def create(data:bytes,filename:str,name:str,expected_text:str=""):
    name=_name(name,120,"Укажите название макета")
    expected_text=_text(expected_text)
    suffix=_picture(data)
    digest=hashlib.sha256(data).hexdigest()
    uid=uuid.uuid4()
    target=ROOT/(str(uid)+suffix)
    ROOT.mkdir(parents=True,exist_ok=True)
    if ROOT.is_symlink():raise HTTPException(409,"Недоступно хранилище макетов")
    fd,temp=tempfile.mkstemp(prefix=".layout.",dir=ROOT)
    published=False
    try:
        with os.fdopen(fd,"wb") as out:out.write(data)
        with connect() as db:
            saved=records.insert(db,uid,name,Path(filename).name[:200],digest,target,
                                 len(data),expected_text)
            if not saved:raise HTTPException(409,"Этот макет уже добавлен")
            os.replace(temp,target)
            published=True
        return {"id":str(uid),"name":name,"version":1}
    except Exception:
        if published:target.unlink(missing_ok=True)
        raise
    finally:
        Path(temp).unlink(missing_ok=True)

def _keep_one_active(db):
    if db.execute("SELECT ad_pipeline_enabled FROM processing_settings WHERE id=1").fetchone()["ad_pipeline_enabled"]:
        active=db.execute("SELECT count(*) AS n FROM ad_layouts WHERE active=true").fetchone()["n"]
        if active<=1:
            raise HTTPException(409,"Сначала выключите распознавание рекламы: активный макет последний")

def update(uid,version:int,name:str,expected_text:str,active:bool):
    name=_name(name,120,"Укажите название макета")
    expected_text=_text(expected_text)
    with connect() as db:
        if not active:
            db.execute("SELECT pg_advisory_xact_lock(723409133)")
        row=records.by_id(db,uid,lock=True)
        if not row:raise HTTPException(404,"Макет не найден")
        if row["active"] and not active:
            _keep_one_active(db)
        if row["version"]!=version:
            raise HTTPException(409,"Макет изменён в другой вкладке")
        result=records.edit(db,uid,version,name,expected_text,active)
        if not result:raise HTTPException(409,"Версия макета устарела")
    return {"id":str(uid),"version":version+1}

def _file(row):
    try:
        path=owned_file(Path(row["target_path"]),ROOT)
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in FORMATS.values():
            raise ValueError("Missing image")
        return path
    except (ValueError,OSError) as exc:
        raise HTTPException(404,"Изображение макета недоступно") from exc

def image(uid):
    with connect() as db:row=records.by_id(db,uid)
    if not row:raise HTTPException(404,"Макет не найден")
    return _file(row)

def active_files():
    with connect() as db:rows=records.all_rows(db,True)
    return [(dict(row),_file(row)) for row in rows]

def delete(uid):
    with connect() as db:
        # Never unlink a pinned immutable layout while its FIFO job is running.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        busy=db.execute("""SELECT 1 FROM jobs
            WHERE status IN ('running','stopping')
              AND snapshot->'ad_pipeline'->>'enabled'='true' LIMIT 1""").fetchone()
        if busy:
            raise HTTPException(409,"Дождитесь окончания обработки рекламы перед удалением макета")
        row=records.by_id(db,uid,lock=True)
        if not row:raise HTTPException(404,"Макет не найден")
        if row["active"]:
            _keep_one_active(db)
        path=_file(row)
        records.remove(db,uid)
    path.unlink(missing_ok=True)
    return {"deleted":True}
