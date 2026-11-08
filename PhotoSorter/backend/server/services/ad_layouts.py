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
            "expected_text":row["expected_text"],"corrected_text":row["ocr_corrected_text"],
            "ocr_raw_lines":row["ocr_lines"] or [],
            "ocr_normalized_text":row["normalized_text"] or "",
            "preparation_state":row["preparation_state"],
            "preparation_stage":row["preparation_stage"],
            "preparation_progress":row["preparation_progress"],
            "preparation_error":row["preparation_error"],
            "prepared_at":row["prepared_at"],
            "active":row["active"],"version":row["version"],
            "image_url":"/api/ad-layouts/"+str(row["id"])+"/image"}

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
            db.execute("SELECT pg_advisory_xact_lock(723409133)")
            saved=records.insert(db,uid,name,Path(filename).name[:200],digest,target,
                                 len(data),expected_text)
            if not saved:raise HTTPException(409,"Этот макет уже добавлен")
            if expected_text:
                db.execute("UPDATE ad_layouts SET ocr_corrected_text=%s WHERE id=%s",
                           (expected_text,uid))
            prep_id=uuid.uuid4()
            db.execute("""INSERT INTO ad_layout_preparation_jobs
                (id,layout_id,checksum,target_path) VALUES (%s,%s,%s,%s)""",
                (prep_id,uid,digest,str(target)))
            from ..db.repositories.work_queue import insert_layout
            insert_layout(db,prep_id)
            os.replace(temp,target)
            published=True
        return {"id":str(uid),"name":name,"version":1,"preparation_state":"queued"}
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
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        row=records.by_id(db,uid,lock=True)
        if not row:raise HTTPException(404,"Макет не найден")
        if row["active"] and not active:
            _keep_one_active(db)
        if row["version"]!=version:
            raise HTTPException(409,"Макет изменён в другой вкладке")
        result=records.edit(db,uid,version,name,expected_text,active)
        if not result:raise HTTPException(409,"Версия макета устарела")
        if row["preparation_state"]=="completed" and row["published_snapshot"]:
            from psycopg.types.json import Jsonb
            snapshot=dict(row["published_snapshot"])
            snapshot.update(name=name,version=version+1,expected_text=expected_text,
                ocr_corrected_text=expected_text or None,
                ocr_text=expected_text or row["normalized_text"] or "")
            db.execute("UPDATE ad_layouts SET published_snapshot=%s WHERE id=%s",
                       (Jsonb(snapshot),uid))
        db.execute("UPDATE ad_layout_library_state SET revision=revision+1 WHERE id=1")
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
    from app.ad_recognition import dino,ocr
    if not ocr.status()["available"]:
        return []
    signature=ocr.signature()
    ready=[row["published_snapshot"] for row in rows if row["published_snapshot"]
           and row["published_snapshot"]["dino_signature"]==dino.SIGNATURE
           and row["published_snapshot"]["ocr_signature"]==signature]
    return [(layout,_file(layout)) for layout in ready]

def replace_image(uid,version:int,data:bytes,filename:str):
    """Publish a new immutable original and enqueue its preparation atomically."""
    suffix=_picture(data)
    checksum=hashlib.sha256(data).hexdigest()
    ROOT.mkdir(parents=True,exist_ok=True)
    if ROOT.is_symlink():raise HTTPException(409,"Недоступно хранилище макетов")
    target=ROOT/(str(uid)+"-"+str(uuid.uuid4())+suffix)
    fd,temp=tempfile.mkstemp(prefix=".layout.",dir=ROOT)
    published=False
    try:
        with os.fdopen(fd,"wb") as output:output.write(data)
        with connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(723409133)")
            row=records.by_id(db,uid,lock=True)
            if not row:raise HTTPException(404,"Макет не найден")
            if row["version"]!=version:
                raise HTTPException(409,"Версия макета устарела")
            if db.execute("""SELECT 1 FROM ad_layout_preparation_jobs
                WHERE layout_id=%s AND state='running'""",(uid,)).fetchone():
                raise HTTPException(409,"Дождитесь завершения текущей подготовки макета")
            if checksum==row["checksum"]:
                return {"id":str(uid),"version":version,
                        "preparation_state":row["preparation_state"]}
            if db.execute("SELECT 1 FROM ad_layouts WHERE checksum=%s",(checksum,)).fetchone():
                raise HTTPException(409,"Этот макет уже добавлен")
            old=_file(row)
            db.execute("""UPDATE work_queue SET state='stopped',finished_at=now()
                WHERE layout_job_id IN (SELECT id FROM ad_layout_preparation_jobs
                    WHERE layout_id=%s) AND state IN ('queued','failed','interrupted')""",(uid,))
            db.execute("""UPDATE ad_layout_preparation_jobs SET state='stopped',
                finished_at=now() WHERE layout_id=%s AND state IN
                ('queued','failed','interrupted')""",(uid,))
            db.execute("""INSERT INTO ad_layout_retired_assets(target_path,checksum)
                VALUES (%s,%s) ON CONFLICT(target_path) DO NOTHING""",
                (str(old),row["checksum"]))
            db.execute("""UPDATE ad_layouts SET checksum=%s,target_path=%s,
                filename=%s,byte_size=%s,expected_text='',ocr_corrected_text=NULL,
                prepared_key=NULL,preparation_state='queued',preparation_stage='queued',
                preparation_progress=0,preparation_error=NULL,prepared_at=NULL,
                version=version+1,updated_at=now() WHERE id=%s""",
                (checksum,str(target),Path(filename).name[:200],len(data),uid))
            prep=uuid.uuid4()
            db.execute("""INSERT INTO ad_layout_preparation_jobs(id,layout_id,checksum,target_path)
                VALUES (%s,%s,%s,%s)""",(prep,uid,checksum,str(target)))
            from ..db.repositories.work_queue import insert_layout
            insert_layout(db,prep)
            db.execute("UPDATE ad_layout_library_state SET revision=revision+1 WHERE id=1")
            os.replace(temp,target)
            published=True
        return {"id":str(uid),"version":version+1,"preparation_state":"queued"}
    except Exception:
        if published:target.unlink(missing_ok=True)
        raise
    finally:
        Path(temp).unlink(missing_ok=True)



def requeue_stale_models():
    """Detect changed model/preprocessing signatures and enqueue once in FIFO."""
    from app.ad_recognition import dino,ocr
    if not dino.verify() or not ocr.status()["available"]:
        return 0
    ocr_sig=ocr.signature()
    count=0
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        stale=db.execute("""SELECT l.id,l.checksum,l.target_path FROM ad_layouts l
            LEFT JOIN ad_layout_prepared_cache c ON c.cache_key=l.prepared_key
            WHERE l.preparation_state='completed' AND
            (c.cache_key IS NULL OR c.dino_signature<>%s OR c.ocr_signature<>%s)
            ORDER BY l.created_at,l.id""",(dino.SIGNATURE,ocr_sig)).fetchall()
        from ..db.repositories.work_queue import insert_layout
        for item in stale:
            db.execute("""UPDATE ad_layouts SET preparation_state='queued',
                preparation_stage='queued',preparation_progress=0,
                preparation_error=NULL,prepared_key=NULL,prepared_at=NULL
                WHERE id=%s""",(item["id"],))
            job=uuid.uuid4()
            db.execute("""INSERT INTO ad_layout_preparation_jobs
                (id,layout_id,checksum,target_path) VALUES (%s,%s,%s,%s)""",
                (job,item["id"],item["checksum"],item["target_path"]))
            insert_layout(db,job)
            count+=1
        if count:
            db.execute("UPDATE ad_layout_library_state SET revision=revision+1 WHERE id=1")
    return count

def gc_retired(limit=25):
    """Do not remove an original still referenced by a retained immutable run."""
    removed=0
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        files=db.execute("""SELECT target_path FROM ad_layout_retired_assets
            ORDER BY retired_at LIMIT %s FOR UPDATE""",(limit,)).fetchall()
        for item in files:
            path=item["target_path"]
            pinned=db.execute("""SELECT 1 FROM jobs
                WHERE snapshot->'ad_pipeline'->'layouts' @>
                    jsonb_build_array(jsonb_build_object('target_path',%s::text))
                LIMIT 1""",(path,)).fetchone()
            if pinned:continue
            still_published=db.execute("""SELECT 1 FROM ad_layouts
                WHERE published_snapshot->>'target_path'=%s LIMIT 1""",
                (path,)).fetchone()
            if still_published:continue
            original=owned_file(Path(path),ROOT)
            original.unlink(missing_ok=True)
            db.execute("DELETE FROM ad_layout_retired_assets WHERE target_path=%s",(path,))
            removed+=1
    return removed


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
        db.execute("""UPDATE work_queue SET state='stopped',finished_at=now()
            WHERE layout_job_id IN (SELECT id FROM ad_layout_preparation_jobs
                WHERE layout_id=%s) AND state IN ('queued','failed','interrupted')""",(uid,))
        db.execute("""UPDATE ad_layout_preparation_jobs SET state='stopped',finished_at=now()
            WHERE layout_id=%s AND state IN ('queued','failed','interrupted')""",(uid,))
        if db.execute("""SELECT 1 FROM ad_layout_preparation_jobs
            WHERE layout_id=%s AND state='running'""",(uid,)).fetchone():
            raise HTTPException(409,"Подготовка макета ещё выполняется")
        db.execute("""INSERT INTO ad_layout_retired_assets(target_path,checksum)
            VALUES (%s,%s) ON CONFLICT(target_path) DO NOTHING""",
            (str(path),row["checksum"]))
        records.remove(db,uid)
        db.execute("UPDATE ad_layout_library_state SET revision=revision+1 WHERE id=1")
    return {"deleted":True}
