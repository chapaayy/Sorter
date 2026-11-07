"""One CPU-bound preparation job. Invoked only by the global leader."""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.system.model_store import signature
from app.config import DATA_DIR
REFERENCE_GALLERY=DATA_DIR/"references"
from app.recognition.engines.megaloc.extractor import MegaLocEngine
from ..database import connect
from ..reference_cache import ReferenceCachedMegaLoc,cached_feature
from ..storage import reference_objects,reference_versions as objects
from ..services import reference_publication
from ..services import thumbnails

CHUNK=24

class PreparationCancelled(InterruptedError):
    pass

def _should_stop(job_id):
    with connect() as db:
        row=db.execute("SELECT stop_requested FROM reference_preparation_jobs WHERE id=%s",
                       (job_id,)).fetchone()
    return bool(row and row["stop_requested"])

def _progress(job_id,done,total):
    with connect() as db:
        db.execute("""
            UPDATE reference_preparation_jobs SET completed_count=%s,
                total_count=%s,updated_at=now()
            WHERE id=%s AND state='running'
        """,(done,total,job_id))

def _source_files(db,job_id):
    return db.execute("""
        SELECT f.upload_id,f.sam,f.address,f.filename,f.declared_size,
               f.checksum,f.stored_path,f.state
        FROM reference_import_files f JOIN reference_preparation_jobs p
          ON p.session_id=f.session_id WHERE p.id=%s
        ORDER BY f.relative_path,f.upload_id
    """,(job_id,)).fetchall()

def _prepare_embeddings(job_id,items,model_signature):
    """Reuse (SHA-256,signature) cache and instantiate MegaLoc only if missing."""
    unique={}
    for item in items:
        key=(item["checksum"],str(item["stored_path"]))
        unique[key]=Path(item["stored_path"])
    paths=list(unique.values())
    with connect() as db:
        missing=[]
        for (digest,_),path in unique.items():
            if cached_feature(db,digest,model_signature) is None:
                missing.append(path)
    if not missing:
        _progress(job_id,len(items),len(items))
        return
    engine=None
    try:
        engine=ReferenceCachedMegaLoc(MegaLocEngine())
        if engine.fingerprint!=model_signature:
            raise RuntimeError("Сигнатура MegaLoc изменилась во время подготовки")
        processed=0
        for offset in range(0,len(missing),CHUNK):
            if _should_stop(job_id):
                raise PreparationCancelled("Подготовка остановлена пользователем")
            block=missing[offset:offset+CHUNK]
            for path,feature,error in engine.extract_many(block,stop=lambda:_should_stop(job_id)):
                if error is not None or feature is None:
                    raise RuntimeError(f"Не удалось подготовить {path.name}: {error}")
                processed+=1
                _progress(job_id,min(len(items),processed),len(items))
        _progress(job_id,len(items),len(items))
    finally:
        if engine is not None:
            engine.unload()

def _mirror_reference(db,item,source):
    """Create legacy-gallery hardlink without altering immutable staged input."""
    from ..storage.reference_objects import verify
    from app.photos.construction import parse_key
    from pathlib import Path
    import os
    base=REFERENCE_GALLERY
    destination_dir=base/item["sam"]
    if base.is_symlink() or destination_dir.is_symlink():
        raise ValueError("Недоверенный каталог образцов")
    destination_dir.mkdir(parents=True,exist_ok=True)
    target=destination_dir/(str(item["upload_id"])+"_"+item["filename"])
    if target.is_symlink():
        raise ValueError("Недоверенный путь Образца")
    if not target.exists():
        try:
            os.link(source,target,follow_symlinks=False)
        except FileExistsError:
            pass
    verify(target,base,item["declared_size"],digest=item["checksum"])
    existing=db.execute("SELECT id FROM uploads WHERE id=%s",(item["upload_id"],)).fetchone()
    if not existing:
        db.execute("""
            INSERT INTO uploads(id,kind,batch_id,sam,filename,declared_size,
                received,checksum,finalized,target_path)
            VALUES (%s,'reference',NULL,%s,%s,%s,%s,%s,true,%s)
        """,(item["upload_id"],item["sam"],item["filename"],
             item["declared_size"],item["declared_size"],
             item["checksum"],str(target)))
        thumbnails.enqueue(db,item["upload_id"],item["checksum"])

def run(job_id):
    """Preparation does not publish anything until all embedding work succeeds."""
    with connect() as db:
        job=db.execute("""
            SELECT session_id,state,model_signature
            FROM reference_preparation_jobs WHERE id=%s
        """,(job_id,)).fetchone()
        if not job or job["state"]!="running":
            raise RuntimeError("Задание подготовки не запущено")
        items=_source_files(db,job_id)
        session_id=job["session_id"]
    if not items:
        raise ValueError("Пустая сессия образцов")
    fp=signature()
    if not fp:
        raise RuntimeError("Отсутствует установленная MegaLoc")
    actual=[]
    for item in items:
        if _should_stop(job_id):
            raise PreparationCancelled("Подготовка остановлена")
        if item["state"]=="finalized":
            file=reference_objects.verify(item["stored_path"],
                reference_objects.session_root(session_id),item["declared_size"],
                digest=item["checksum"])
            actual.append({**item,"stored_path":str(file)})
        elif item["state"]!="duplicate":
            raise ValueError("Не все файлы подготовлены")
    if actual:
        _prepare_embeddings(job_id,actual,fp)
    else:
        _progress(job_id,len(items),len(items))
    # No future job can start before this transaction finishes. Publication
    # state, status and version pointer all commit together.
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        db.execute("SELECT id FROM reference_preparation_jobs WHERE id=%s FOR UPDATE",(job_id,))
        if _should_stop(job_id):
            raise PreparationCancelled("Подготовка остановлена")
        if signature()!=fp:
            raise RuntimeError("Сигнатура модели изменилась")
        state=db.execute("""
            SELECT current_version_id FROM reference_library_state WHERE id=1 FOR UPDATE
        """).fetchone()
        if not state or state["current_version_id"] is None:
            raise RuntimeError("Нет опубликованной базы образцов")
        previous=reference_publication.snapshot(db,state["current_version_id"])
        from ..db.repositories import reference_versions as version_repo
        members=[dict(m) for m in version_repo.members(db,state["current_version_id"])]
        seen={(m["sam"],m["source_hash"]) for m in members}
        for item in actual:
            key=item["sam"],item["checksum"]
            if key in seen:
                continue
            seen.add(key)
            # Add the source, but do not expose anything to FO until all
            # input features and catalog entries are verified.
            members.append({"reference_id":item["upload_id"],"sam":item["sam"],
                "filename":item["filename"],"source_hash":item["checksum"],
                "target_path":item["stored_path"],
                "declared_size":item["declared_size"],"source_kind":"staged"})
        # No new construction metadata is visible until this transaction.
        from app.photos.construction import parse_key
        for item in actual:
            if item["address"] is None:
                continue
            city,number=parse_key(item["sam"])
            db.execute("""
                INSERT INTO reference_constructions(sam,city_code,construction_number,address)
                VALUES (%s,%s,%s,%s) ON CONFLICT(sam) DO NOTHING
            """,(item["sam"],city,number,item["address"]))
            catalog=db.execute("""
                SELECT address FROM reference_constructions WHERE sam=%s FOR UPDATE
            """,(item["sam"],)).fetchone()
            if not catalog or catalog["address"]!=item["address"]:
                raise ValueError("Адрес конструкции изменился с момента загрузки")
        version,changed=reference_publication.publish(
            db,members,fp,job_id=job_id,event_kind="reference_prepared")
        for item in actual:
            # Gallery/backwards-compatible files are a mirror, not the source
            # consumed by pinned FO jobs.
            if not db.execute("SELECT 1 FROM uploads WHERE kind='reference' AND finalized AND sam=%s AND checksum=%s LIMIT 1",
                              (item["sam"],item["checksum"])).fetchone():
                _mirror_reference(db,item,Path(item["stored_path"]))
        db.execute("""
            UPDATE reference_preparation_jobs SET state='completed',
                completed_count=total_count,model_signature=%s,error=NULL,
                finished_at=now(),updated_at=now() WHERE id=%s
        """,(fp,job_id))
        db.execute("""
            UPDATE reference_import_sessions SET preparation_state='completed',error=NULL
            WHERE id=%s
        """,(session_id,))
        db.execute("""
            UPDATE work_queue SET state='completed',finished_at=now()
            WHERE reference_job_id=%s
        """,(job_id,))
    return {"version":version["version_number"],"changed":changed}
