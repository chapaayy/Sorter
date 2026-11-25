"""Durable manifests for the one supported reference-upload pipeline."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

from fastapi import HTTPException
from app.photos.construction import parse_folder_name,parse_key
from app.photos.labels import check_label
from ..database import connect
from ..db.repositories import reference_imports as repository
from ..storage import reference_objects as storage
from .reference_sides import normalize_side
from .reference_import_sides import desired_sides, validate_existing_sides

MAX_FILES=20000
MAX_PATH=1024
_SHA=re.compile(r"^[0-9a-f]{64}$")

def _uid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError,ValueError,AttributeError) as exc:
        raise HTTPException(422,"Некорректный идентификатор импорта") from exc

def _manifest(files):
    from ..services.upload_validation import safe_name,MAX_FILE_BYTES
    if not files or len(files)>MAX_FILES:
        raise HTTPException(422,"Выберите от 1 до 20000 фотографий")
    unique_ids=set()
    unique_paths=set()
    addresses={}
    valid=[]
    for item in files:
        uid=_uid(item.upload_id)
        relative=item.relative_path
        filename=safe_name(item.filename,reference=True)
        if filename!=item.filename:
            raise HTTPException(422,"Имя файла должно быть без пути")
        if (not relative or len(relative)>MAX_PATH or "\\" in relative or "\x00" in relative or
            relative.startswith("/") or
            any(part in ("",".","..") for part in relative.split("/")) or
            relative.split("/")[-1]!=filename):
            raise HTTPException(422,"Некорректный относительный путь образца")
        if item.size<=0 or item.size>MAX_FILE_BYTES:
            raise HTTPException(422,"Некорректный размер фотографии")
        if item.sha256 is not None and not _SHA.fullmatch(item.sha256):
            raise HTTPException(422,"Некорректная контрольная сумма SHA-256")
        sam=item.sam
        address=item.address
        try:
            if address is not None:
                folder=parse_folder_name(sam+" — "+address)
                if folder.key!=sam:
                    raise ValueError("Номер конструкции не совпадает")
            else:
                # Only pre-registered catalog entries may use custom labels.
                if check_label(sam)!=sam:
                    raise ValueError("Недопустимое название конструкции")
        except ValueError as exc:
            raise HTTPException(422,"Недопустимый номер или адрес конструкции") from exc
        if sam in addresses and addresses[sam]!=address:
            # For a complete manifest the address should be identical on every row.
            raise HTTPException(422,"Одна конструкция с разными адресами")
        addresses[sam]=address
        if uid in unique_ids or relative in unique_paths:
            raise HTTPException(422,"Повтор UUID или пути в манифесте")
        unique_ids.add(uid)
        unique_paths.add(relative)
        side=normalize_side(getattr(item,'side',None))
        valid.append((uid,sam,address,relative,filename,item.size,item.sha256,side))
    # Reject a manifest assigning two different sides to identical content.
    desired_sides({'sam':row[1],'checksum':row[6],'side':row[7]} for row in valid)
    return sorted(valid,key=lambda row:(row[3],str(row[0])))

def _check_catalog(db, rows):
    if db.execute("""
        SELECT 1 FROM uploads WHERE id=ANY(%s) LIMIT 1
    """,([row[0] for row in rows],)).fetchone():
        raise HTTPException(409,"UUID образца уже занят")
    sams=sorted({row[1] for row in rows})
    catalog={r["sam"]:r for r in db.execute("""
        SELECT sam,address,kind FROM reference_constructions WHERE sam=ANY(%s)
    """,(sams,)).fetchall()}
    from . import regions
    codes=[parse_key(sam)[0] for sam,address in
           {row[1]:row[2] for row in rows}.items() if address is not None]
    regions.ensure_registered(db,codes)
    for sam,address in {row[1]:row[2] for row in rows}.items():
        if sam in catalog:
            row=catalog[sam]
            if row["kind"]=="custom" and address is not None:
                raise HTTPException(422,"У индивидуальной конструкции нет адреса")
            if address is not None and row["address"]!=address:
                raise HTTPException(409,f"У конструкции {sam} другой сохранённый адрес")
        elif address is None:
            raise HTTPException(422,f"Новая конструкция {sam} требует адреса")

def _signature(rows):
    # Keep the exact signature of pre-upgrade sessions without sides.
    with_sides=any(row[7] is not None for row in rows)
    payload=[[str(uid),sam,address,path,name,size,sha]+([side] if with_sides else []) for
             uid,sam,address,path,name,size,sha,side in rows]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,
        separators=(",",":")).encode("utf-8")).hexdigest()

def create(session_id):
    session_id=_uid(session_id)
    with connect() as db:
        repository.create_session(db,session_id)
    return status(session_id)

def compare(files):
    """Read-only comparison with the currently published library."""
    keys=[(item.sam,item.sha256,item.size) for item in files]
    sams,digests,sizes=map(list,zip(*dict.fromkeys(keys)))
    with connect() as db:
        candidates=repository.compare_published(db,sams,digests,sizes)
    matches={}
    for row in candidates:
        key=(row["sam"],row["source_hash"],row["declared_size"])
        if key in matches:
            continue
        try:
            storage.verify_object(row["target_path"],key[2],digest=key[1])
        except (OSError,TypeError,ValueError):
            continue
        matches[key]=row["side"]
    result={"duplicates":[key in matches for key in keys]}
    # Preserve the old response for legacy clients without side metadata.
    requested=[normalize_side(getattr(item,"side",None)) for item in files]
    if any(requested):
        result["side_conflicts"]=[{"index":i,"existing_side":matches[key],"requested_side":side}
            for i,(key,side) in enumerate(zip(keys,requested))
            if side is not None and key in matches and matches[key]!=side]
    return result

def register_manifest(session_id,files):
    session_id=_uid(session_id)
    expected=_manifest(files)
    signature=_signature(expected)
    with connect() as db:
        # Serialize manifest registration with catalog relabels and FIFO claims.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        session=repository.session(db,session_id,lock=True)
        if not session:
            raise HTTPException(404,"Сессия загрузки образцов не найдена")
        if session["manifest_digest"] is not None:
            if session["manifest_digest"]!=signature:
                raise HTTPException(409,"Нельзя изменять ранее закреплённый манифест")
        else:
            if session["upload_state"]!="uploading":
                raise HTTPException(409,"Загрузка уже закрыта")
            _check_catalog(db,expected)
            validate_existing_sides(db,desired_sides(
                {'sam':row[1],'checksum':row[6],'side':row[7]} for row in expected))
            repository.register(db,session_id,expected,signature)
    return status(session_id)

def _file_state(db,session_id,upload_id,*,lock=False):
    session=repository.session(db,session_id)
    if not session:
        raise HTTPException(404,"Сессия не найдена")
    if session["manifest_digest"] is None:
        raise HTTPException(409,"Сначала зарегистрируйте манифест")
    entry=repository.file(db,session_id,upload_id,lock=lock)
    if not entry:
        raise HTTPException(404,"Файл отсутствует в манифесте")
    return session,entry

def file_status(session_id,upload_id):
    session_id,upload_id=_uid(session_id),_uid(upload_id)
    with connect() as db:
        _,entry=_file_state(db,session_id,upload_id)
    actual=0
    if entry["state"]=="pending":
        actual=storage.offset(session_id,upload_id,entry["declared_size"])
    return {"upload_id":str(upload_id),"state":entry["state"],
            "offset":actual if entry["state"]=="pending" else entry["received"],
            "size":entry["declared_size"],"sha256":entry["checksum"]}

def _completion(session_id,job=None):
    return {"session_id":str(session_id),"preparation_job_id":str(job["id"]) if job else None,
            "queue_seq":job["seq"] if job else None,"state":"queued" if job else "unchanged"}

def _complete_locked(db,session_id):
    """Caller locks session row (FOR UPDATE); enqueue only at verified completion."""
    session=repository.session(db,session_id)
    if session["upload_state"]=="complete":
        return _completion(session_id,repository.preparation(db,session_id))
    if session["upload_state"]!="uploading" or session["manifest_digest"] is None:
        return None
    entries=repository.files(db,session_id)
    if len(entries)!=session["expected_count"] or not entries:
        return None
    for entry in entries:
        if entry["state"] not in ("finalized","duplicate") or not entry["checksum"]:
            return None
        if entry["state"]=="finalized":
            try:
                storage.verify_object(entry["stored_path"],entry["declared_size"],digest=entry["checksum"])
            except (OSError,TypeError,ValueError):
                return None
    requested=desired_sides(entries)
    validate_existing_sides(db,requested)
    if all(entry["state"]=="duplicate" for entry in entries):
        repository.complete_without_preparation(db,session_id)
        return _completion(session_id)
    return _completion(session_id,repository.enqueue_completed(db,session_id,len(entries)))

def reconcile(db,session_id):
    """Called after each finish/duplicate; no browser callback needed."""
    repository.session(db,session_id,lock=True)
    return _complete_locked(db,session_id)

def complete(session_id):
    session_id=_uid(session_id)
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        if not repository.session(db,session_id,lock=True):
            raise HTTPException(404,"Сессия не найдена")
        result=_complete_locked(db,session_id)
        if result is None:
            raise HTTPException(409,"Не все файлы завершены и проверены")
        return result
    
def status(session_id):
    session_id=_uid(session_id)
    with connect() as db:
        session=repository.session(db,session_id)
        if not session:
            raise HTTPException(404,"Сессия загрузки образцов не найдена")
        entries=repository.files(db,session_id)
        job=repository.preparation(db,session_id)
    items=[]
    finalized=duplicates=missing=0
    for entry in entries:
        state=entry["state"]
        size=entry["declared_size"]
        saved_offset=0
        if state=="pending":
            saved_offset=storage.offset(session_id,entry["upload_id"],size)
            if saved_offset==0:missing+=1
        elif state=="finalized":
            if session["preparation_state"] in ("completed","stopped") or session["upload_state"]=="cancelled":
                # Historical transfer receipts are not physical owners.
                finalized+=1
            else:
                try:
                    storage.verify_object(entry["stored_path"],size,digest=entry["checksum"])
                    finalized+=1
                except (ValueError,OSError,TypeError):
                    state="missing_saved"
        else:
            duplicates+=1
        items.append({"upload_id":str(entry["upload_id"]),
                      "relative_path":entry["relative_path"],"sam":entry["sam"],
                      "filename":entry["filename"],"size":size,"state":state,
                      "side":entry["side"],
                      "received":saved_offset if state=="pending" else entry["received"],
                      "sha256":entry["checksum"]})
    return {"id":str(session_id),"state":session["upload_state"],
            "preparation_state":session["preparation_state"],
            "expected":session["expected_count"] or 0,
            "registered":session["manifest_digest"] is not None,
            "finalized":finalized,"duplicates":duplicates,
            "pending":len(items)-finalized-duplicates,"missing":missing,
            "completed_at":session["completed_at"],
            "preparation_job_id":str(job["id"]) if job else None,
            "queue_seq":job["seq"] if job else None,
            "files":items}

def list_sessions(limit=25,offset=0):
    if not 1<=limit<=100 or offset<0:
        raise HTTPException(422,"Неверная пагинация")
    with connect() as db:
        total=db.execute("SELECT count(*) AS n FROM reference_import_sessions").fetchone()["n"]
        rows=db.execute("""
            SELECT s.id,s.upload_state AS state,s.preparation_state,s.expected_count,
                   s.created_at,s.completed_at,
                   p.id AS preparation_job_id,p.total_count,p.completed_count,
                   p.failed_count,p.error,w.seq AS queue_seq,
                   count(f.upload_id) FILTER (WHERE f.state='finalized') AS finalized,
                   count(f.upload_id) FILTER (WHERE f.state='duplicate') AS duplicates
            FROM reference_import_sessions s
            LEFT JOIN reference_import_files f ON f.session_id=s.id
            LEFT JOIN reference_preparation_jobs p ON p.session_id=s.id
            LEFT JOIN work_queue w ON w.reference_job_id=p.id
            GROUP BY s.id,p.id,w.seq
            ORDER BY s.created_at DESC,s.id DESC LIMIT %s OFFSET %s
        """,(limit,offset)).fetchall()
    return {"sessions":rows,"total":total}
