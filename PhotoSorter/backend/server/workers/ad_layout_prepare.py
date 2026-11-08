"""CPU-only DINOv2/PaddleOCR preparation in the existing global FIFO."""
from __future__ import annotations

import gc
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from app.ad_recognition import dino, embedding_cache, ocr
from ..database import connect
from ..services import ad_layouts
from ..db.repositories.work_queue import LOCK
from ..storage.paths import owned_file


def _stage(job_id, stage, percent):
    with connect() as db:
        db.execute("""UPDATE ad_layout_preparation_jobs
            SET progress_stage=%s,progress_percent=%s
            WHERE id=%s AND state='running'""",(stage,percent,job_id))
        db.execute("""UPDATE ad_layouts SET preparation_stage=%s,preparation_progress=%s
            WHERE id=(SELECT layout_id FROM ad_layout_preparation_jobs WHERE id=%s)
              AND preparation_state='running'""",(stage,percent,job_id))


def _key(checksum, dino_signature, ocr_signature):
    return hashlib.sha256(
        (checksum+":"+dino_signature+":"+ocr_signature).encode("ascii")).hexdigest()


def _vector_ready(path):
    if path.is_symlink() or not path.is_file():
        return False
    try:
        value=np.load(path,allow_pickle=False)
        return (value.shape==(dino.EMBED_DIM,) and np.isfinite(value).all()
                and abs(float(np.linalg.norm(value))-1)<.01)
    except (OSError,ValueError,EOFError):
        return False


def run(job_id):
    with connect() as db:
        job=db.execute("""SELECT p.*,l.id AS current_layout,l.checksum AS current_checksum
            FROM ad_layout_preparation_jobs p
            LEFT JOIN ad_layouts l ON l.id=p.layout_id
            WHERE p.id=%s""",(job_id,)).fetchone()
    if not job or job["state"]!="running" or job["current_layout"] is None:
        raise RuntimeError("Макет для подготовки отсутствует")
    if job["checksum"]!=job["current_checksum"]:
        raise RuntimeError("Исходный макет изменился")
    _stage(job_id,"validating",5)
    original=owned_file(Path(job["target_path"]),ad_layouts.ROOT)
    if original.is_symlink() or not original.is_file():
        raise FileNotFoundError("Исходное изображение макета не найдено")
    with original.open("rb") as stream:
        if hashlib.file_digest(stream,"sha256").hexdigest()!=job["checksum"]:
            raise ValueError("Контрольная сумма макета не совпадает")
    if not dino.verify() or not ocr.status()["available"]:
        raise RuntimeError("Для подготовки нужны установленные DINOv2 и PP-OCRv5")
    dino_sig=dino.SIGNATURE
    ocr_sig=ocr.signature()
    cache_key=_key(job["checksum"],dino_sig,ocr_sig)
    vector_path=embedding_cache.ROOT/(embedding_cache.key(job["checksum"])+".npy")
    with connect() as db:
        cached=db.execute("""SELECT ocr_lines,normalized_text FROM ad_layout_prepared_cache
            WHERE cache_key=%s AND dino_signature=%s AND ocr_signature=%s""",
            (cache_key,dino_sig,ocr_sig)).fetchone()

    if not _vector_ready(vector_path):
        _stage(job_id,"dino",15)
        model=dino.load()
        try:
            embedding_cache.vector(model,{"checksum":job["checksum"]},original)
        finally:
            del model
            gc.collect()
        if not _vector_ready(vector_path):
            raise RuntimeError("DINOv2 не сохранила корректные признаки")
    _stage(job_id,"ocr",55)
    if cached:
        lines=cached["ocr_lines"]
        normalized=cached["normalized_text"]
    else:
        engine=ocr.load()
        try:
            with Image.open(original) as picture:
                lines=ocr.read(engine,ImageOps.exif_transpose(picture))
        finally:
            del engine
            gc.collect()
        normalized=ocr._norm(" ".join(line["text"] for line in lines))
    _stage(job_id,"publishing",90)
    if dino.SIGNATURE!=dino_sig or ocr.signature()!=ocr_sig:
        raise RuntimeError("Сигнатура OCR изменилась при подготовке")
    from psycopg.types.json import Jsonb
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK,))
        current=db.execute("""SELECT p.state,p.layout_id,p.checksum,l.checksum AS current_checksum,
            l.name,l.filename,l.target_path,l.byte_size,l.expected_text,
            l.ocr_corrected_text,l.version
            FROM ad_layout_preparation_jobs p JOIN ad_layouts l ON l.id=p.layout_id
            WHERE p.id=%s FOR UPDATE OF p,l""",(job_id,)).fetchone()
        if not current or current["state"]!="running" or current["checksum"]!=current["current_checksum"]:
            raise RuntimeError("Макет изменён до публикации")
        db.execute("""INSERT INTO ad_layout_prepared_cache
            (cache_key,checksum,dino_signature,ocr_signature,embedding_path,ocr_lines,normalized_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(cache_key) DO NOTHING""",
            (cache_key,job["checksum"],dino_sig,ocr_sig,str(vector_path),Jsonb(lines),normalized))
        publication={"id":str(current["layout_id"]),
            "name":current["name"],"filename":current["filename"],
            "checksum":current["checksum"],"target_path":current["target_path"],
            "byte_size":current["byte_size"],"version":current["version"],
            "expected_text":current["expected_text"],
            "ocr_corrected_text":current["ocr_corrected_text"],
            "ocr_text":current["ocr_corrected_text"] if current["ocr_corrected_text"] is not None
                else current["expected_text"] or normalized,
            "prepared_key":cache_key,"embedding_path":str(vector_path),
            "dino_signature":dino_sig,"ocr_signature":ocr_sig}
        db.execute("""UPDATE ad_layouts SET prepared_key=%s,preparation_state='completed',
            preparation_stage='completed',preparation_progress=100,preparation_error=NULL,
            prepared_at=now(),published_snapshot=%s WHERE id=%s""",
            (cache_key,Jsonb(publication),current["layout_id"]))
        db.execute("""UPDATE ad_layout_preparation_jobs SET state='completed',
            progress_stage='completed',progress_percent=100,finished_at=now(),
            error=NULL WHERE id=%s""",(job_id,))
        db.execute("""UPDATE work_queue SET state='completed',finished_at=now()
            WHERE layout_job_id=%s AND state='running'""",(job_id,))
        db.execute("UPDATE ad_layout_library_state SET revision=revision+1 WHERE id=1")
    return {"layout_id":str(current["layout_id"]),"prepared_key":cache_key}
