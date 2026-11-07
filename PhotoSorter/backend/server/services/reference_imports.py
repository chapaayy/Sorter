"""Durable reference import manifests, completion and idempotent FIFO enqueue.

No CPU model is loaded here. These routes remain behind a disabled-by-default
gate until the shared scheduler and immutable reference snapshots are enabled.
"""
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

MAX_FILES=20000
MAX_PATH=1024
_SHA=re.compile(r"^[0-9a-f]{64}$")

def _uid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError,ValueError,AttributeError) as exc:
        raise HTTPException(422,"Некорректный идентификатор импорта") from exc

def _manifest(files):
    from ..uploads import safe_name,MAX_FILE_BYTES
    if not files or len(files)>MAX_FILES:
        raise HTTPException(422,"Выберите от 1 до 20000 фотографий")
    unique_ids=set()
    unique_paths=set()
    addresses={}
    valid=[]
    for item in files:
        uid=_uid(item.upload_id)
        relative=item.relative_path
        filename=safe_name(item.filename)
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
            parse_key(sam)
            if address is not None:
                construction=parse_folder_name(sam+" — "+address)
                if construction.key!=sam:raise ValueError("Неверный номер конструкции")
        except ValueError as exc:
            # Only previously registered legacy keys may be extended;
            # the server checks actual existence below.
            try:
                if check_label(sam)!=sam or not re.fullmatch(r"SAM-\d{4}(?:-[A-Za-zА-Яа-я0-9]{1,8}){0,2}",sam):
                    raise ValueError("Недопустимая старая конструкция")
                if address is not None:
                    raise ValueError("Нельзя менять адрес старой конструкции")
            except ValueError as label_error:
                raise HTTPException(422,"Неверный SAM или адрес образца") from label_error
        if sam in addresses and addresses[sam]!=address:
            # For a complete manifest the address should be identical on every row.
            raise HTTPException(422,"Одна конструкция с разными адресами")
        addresses[sam]=address
        if uid in unique_ids or relative in unique_paths:
            raise HTTPException(422,"Повтор UUID или пути в манифесте")
        unique_ids.add(uid)
        unique_paths.add(relative)
        valid.append((uid,sam,address,relative,filename,item.size,item.sha256))
    return sorted(valid,key=lambda row:(row[3],str(row[0])))

def _check_catalog(db, rows):
    sams=sorted({row[1] for row in rows})
    catalog={r["sam"]:r["address"] for r in db.execute("""
        SELECT sam,address FROM reference_constructions WHERE sam=ANY(%s)
    """,(sams,)).fetchall()}
    for sam,address in {row[1]:row[2] for row in rows}.items():
        if sam in catalog:
            if address is not None and catalog[sam]!=address:
                raise HTTPException(409,f"У конструкции {sam} другой сохранённый адрес")
        elif address is None:
            # Only legacy SAM-nnnn references may be extended without address.
            old=db.execute("""
                SELECT 1 FROM uploads WHERE kind='reference'
                 AND finalized AND sam=%s LIMIT 1
            """,(sam,)).fetchone()
            if not old:
                raise HTTPException(422,f"Новый номер {sam} требует адрес конструкции")
        else:
            # New key + address was checked in _manifest; do not insert into
            # reference_constructions here (publication is in stage 3).
            try:
                parse_key(sam)
            except ValueError:
                raise HTTPException(422,"Старый формат нельзя использовать для новой конструкции")

def _signature(rows):
    payload=[[str(uid),sam,address,path,name,size,sha] for
             uid,sam,address,path,name,size,sha in rows]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,
        separators=(",",":")).encode("utf-8")).hexdigest()

def create(session_id):
    session_id=_uid(session_id)
    with connect() as db:
        repository.create_session(db,session_id)
    return status(session_id)

def register_manifest(session_id,files):
    session_id=_uid(session_id)
    expected=_manifest(files)
    signature=_signature(expected)
    with connect() as db:
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
            "offset":actual if entry["state"]=="pending" else entry["declared_size"],
            "size":entry["declared_size"],"sha256":entry["checksum"]}

def _complete_locked(db,session_id):
    """Caller locks session row (FOR UPDATE); enqueue only at verified completion."""
    session=repository.session(db,session_id)
    if session["upload_state"]=="complete":
        return repository.preparation(db,session_id)
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
                storage.verify(entry["stored_path"],storage.session_root(session_id),
                               entry["declared_size"])
            except (OSError,TypeError,ValueError):
                return None
    return repository.enqueue_completed(db,session_id,len(entries))

def reconcile(db,session_id):
    """Called after each finish/duplicate; no browser callback needed."""
    repository.session(db,session_id,lock=True)
    return _complete_locked(db,session_id)

def complete(session_id):
    session_id=_uid(session_id)
    with connect() as db:
        if not repository.session(db,session_id,lock=True):
            raise HTTPException(404,"Сессия не найдена")
        job=_complete_locked(db,session_id)
        if not job:
            raise HTTPException(409,"Не все файлы завершены и проверены")
        return {"session_id":str(session_id),"preparation_job_id":str(job["id"]),
                "queue_seq":job["seq"],"state":"queued"}
    
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
            try:
                storage.verify(entry["stored_path"],storage.session_root(session_id),size)
                finalized+=1
            except (ValueError,OSError,TypeError):
                state="missing_saved"
        else:
            duplicates+=1
        items.append({"upload_id":str(entry["upload_id"]),
                      "relative_path":entry["relative_path"],"sam":entry["sam"],
                      "filename":entry["filename"],"size":size,"state":state,
                      "received":saved_offset if state=="pending" else size,
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
