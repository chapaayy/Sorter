"""Per-file staged chunk transfer, SHA/format verification and duplicate receipts."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException
from ..database import connect
from ..db.repositories import reference_imports as repository
from ..storage import reference_objects as storage
from . import reference_imports

def _claim_digest(db,sam,digest):
    """Serialize same-SAM/hash finalization across API processes."""
    lock=int.from_bytes(hashlib.sha256((sam+"\\x00"+digest).encode()).digest()[:4],
                        "big",signed=True)
    db.execute("SELECT pg_advisory_xact_lock(%s,%s)",(723409141,lock))

def _verified_duplicate(db,session_id,entry,digest,upload_id):
    published=repository.matching_published(db,entry["sam"],digest,entry["declared_size"])
    staged=repository.matching_staged(db,session_id,entry["sam"],digest,
                                      entry["declared_size"],upload_id)
    for match in published:
        try:
            storage.verify(match["target_path"],storage.ROOT,
                           entry["declared_size"],digest=digest)
            return True
        except (OSError,ValueError,TypeError):
            continue
    for match in staged:
        try:
            storage.verify(match["stored_path"],storage.session_root(session_id),
                           entry["declared_size"],digest=digest)
            return True
        except (OSError,ValueError,TypeError):
            continue
    return False

def _locked_pending(db,session_id,upload_id):
    session,entry=reference_imports._file_state(db,session_id,upload_id,lock=True)
    if session["upload_state"]!="uploading":
        raise HTTPException(409,"Сессия загрузки уже закрыта")
    if entry["state"]!="pending":
        raise HTTPException(409,"Файл уже подтверждён")
    return entry

def append(session_id,upload_id,offset,data):
    session_id,upload_id=reference_imports._uid(session_id),reference_imports._uid(upload_id)
    with connect() as db:
        entry=_locked_pending(db,session_id,upload_id)
        if offset<0:
            raise HTTPException(422,"Отрицательное смещение")
        actual=storage.append(session_id,upload_id,offset,entry["declared_size"],data)
        repository.update_received(db,session_id,upload_id,actual)
    return {"offset":actual}

def finish(session_id,upload_id):
    session_id,upload_id=reference_imports._uid(session_id),reference_imports._uid(upload_id)
    with connect() as db:
        # FIFO lock first, then file/session locks. No dependency deadlocks.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        session,entry=reference_imports._file_state(db,session_id,upload_id,lock=True)
        if entry["state"]=="finalized":
            return {"sha256":entry["checksum"],"already_finalized":True}
        if entry["state"]=="duplicate":
            return {"sha256":entry["checksum"],"already_present":True}
        if session["upload_state"]!="uploading":
            raise HTTPException(409,"Сессия уже закрыта")
        part=storage.partial(session_id,upload_id)
        # Recovery after a crash between hardlink creation and SQL commit.
        if part.exists():
            try:
                storage.verify(part,storage.session_root(session_id),entry["declared_size"])
            except (ValueError,OSError) as exc:
                raise HTTPException(409,"Образец загружен не полностью") from exc
        else:
            part=storage.object_path(session_id,upload_id,entry["filename"])
            try:
                storage.verify(part,storage.session_root(session_id),entry["declared_size"])
            except (ValueError,OSError) as exc:
                raise HTTPException(409,"Исходный файл отсутствует, повторите передачу") from exc
        with part.open("rb") as stream:
            digest=hashlib.file_digest(stream,"sha256").hexdigest()
        if entry["checksum"] is not None and entry["checksum"]!=digest:
            raise HTTPException(422,"SHA-256 образца не совпадает")
        storage.verify_picture(part)
        _claim_digest(db,entry["sam"],digest)
        duplicate=_verified_duplicate(db,session_id,entry,digest,upload_id)
        if duplicate:
            # A server-side duplicate also counts as a completed manifest item.
            repository.mark_duplicate(db,session_id,upload_id,digest)
        else:
            if part==storage.partial(session_id,upload_id):
                target=storage.publish_staged_file(session_id,upload_id,entry["filename"],
                                                   entry["declared_size"],digest)
            else:
                target=part
            repository.finish_file(db,session_id,upload_id,digest,target)
        # This takes session FOR UPDATE only after per-file processing.
        reference_imports.reconcile(db,session_id)
    storage.remove_partial_after_commit(session_id,upload_id)
    return {"sha256":digest,"already_finalized":False,"already_present":duplicate}

def confirm_duplicate(session_id,upload_id,digest):
    session_id,upload_id=reference_imports._uid(session_id),reference_imports._uid(upload_id)
    if not reference_imports._SHA.fullmatch(digest):
        raise HTTPException(422,"Укажите корректный SHA-256")
    with connect() as db:
        # FIFO lock first, then file/session locks. No dependency deadlocks.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        session,entry=reference_imports._file_state(db,session_id,upload_id,lock=True)
        if entry["state"]=="finalized":
            if entry["checksum"]!=digest:
                raise HTTPException(409,"Файл уже завершён с другим хешем")
            return {"already_finalized":True,"sha256":digest}
        if entry["state"]=="duplicate":
            if entry["checksum"]!=digest:
                raise HTTPException(409,"Файл уже подтверждён с другим хешем")
        else:
            if session["upload_state"]!="uploading":
                raise HTTPException(409,"Сессия уже закрыта")
            if entry["checksum"] is not None and entry["checksum"]!=digest:
                raise HTTPException(409,"Хеш не совпадает с манифестом")
            _claim_digest(db,entry["sam"],digest)
            if not _verified_duplicate(db,session_id,entry,digest,upload_id):
                raise HTTPException(409,"Совпадающий готовый образец не найден; отправьте файл")
            repository.mark_duplicate(db,session_id,upload_id,digest)
            reference_imports.reconcile(db,session_id)
    # A client can have sent partial bytes before discovering the duplicate.
    # Clean them only after the durable receipt commits.
    storage.remove_partial_after_commit(session_id,upload_id)
    return {"already_present":True,"sha256":digest}
