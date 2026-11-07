"""Immutable expected-file manifest for a photo batch.

The browser provides stable upload IDs before transferring bytes. PostgreSQL is the
source of truth; no in-memory counters are used for batch completion.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from fastapi import HTTPException
from . import batches as batch_service
from ..database import connect


def _validated(files):
    # Import lazily: uploads.py calls this service when initiating/finalizing.
    from .upload_validation import safe_name, MAX_FILE_BYTES
    if not files or len(files) > 20000:
        raise HTTPException(422, "Манифест должен содержать от 1 до 20000 фотографий")
    result = []
    ids, paths = set(), set()
    for item in files:
        upload_id = item.upload_id
        relative = item.relative_path
        filename = safe_name(item.filename)
        if (not isinstance(relative, str) or len(relative) > 1024 or
                "\\" in relative or "\x00" in relative or
                relative.startswith("/") or
                any(segment in ("", ".", "..") for segment in relative.split("/")) or
                relative.split("/")[-1] != filename):
            raise HTTPException(422, "Неверный относительный путь ФО")
        if item.size <= 0 or item.size > MAX_FILE_BYTES:
            raise HTTPException(422, "Неверный размер фотографии")
        if upload_id in ids or relative in paths:
            raise HTTPException(422, "Повтор файла или пути в манифесте")
        ids.add(upload_id)
        paths.add(relative)
        result.append((upload_id, relative, filename, item.size))
    return sorted(result, key=lambda row: (row[1], str(row[0])))


def register(batch_id, files, *, auto_process=False, grouping_threshold=0.50):
    """Register exactly once; identical POSTs are safe after a lost response."""
    batch_id = batch_service.uid(batch_id)
    expected = _validated(files)
    raw = json.dumps(
        [(str(i), path, name, size) for i, path, name, size in expected],
        ensure_ascii=False, separators=(",", ":")
    )
    signature = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    with connect() as db:
        batch = db.execute("""SELECT delete_state, upload_manifest_signature
            FROM batches WHERE id=%s FOR UPDATE""", (batch_id,)).fetchone()
        if not batch:
            raise HTTPException(404, "Партия не найдена")
        if batch["delete_state"] != "active":
            raise HTTPException(409, "Партия удаляется или удалена")
        if batch["upload_manifest_signature"] is not None:
            if batch["upload_manifest_signature"] != signature:
                raise HTTPException(409, "Состав партии отличается от зарегистрированного манифеста")
        else:
            if db.execute("SELECT 1 FROM uploads WHERE batch_id=%s LIMIT 1", (batch_id,)).fetchone():
                raise HTTPException(409, "У старой партии уже есть файлы; она работает без манифеста")
            if db.execute("SELECT 1 FROM jobs WHERE batch_id=%s LIMIT 1", (batch_id,)).fetchone():
                raise HTTPException(409, "Партия уже обрабатывалась")
            with db.cursor() as cursor:
                cursor.executemany("""INSERT INTO batch_upload_manifest_files
                    (batch_id, upload_id, relative_path, filename, declared_size)
                    VALUES (%s,%s,%s,%s,%s)""",
                    [(batch_id, *item) for item in expected])
            db.execute("""UPDATE batches SET upload_manifest_signature=%s,
                upload_manifest_state='waiting', upload_manifest_completed_at=NULL,
                auto_process_state=%s,auto_process_threshold=%s,
                auto_process_run_id=NULL,auto_process_error=NULL,
                upload_state='open' WHERE id=%s""",
                (signature,'waiting' if auto_process else None,grouping_threshold,batch_id))
    return status(batch_id)


def require_expected_upload(db, batch_id, upload_id, filename, size):
    """Called inside the batch row lock during FO session creation."""
    batch = db.execute("SELECT upload_manifest_state FROM batches WHERE id=%s",
                       (batch_id,)).fetchone()
    if not batch or batch["upload_manifest_state"] is None:
        return
    expected = db.execute("""SELECT filename,declared_size
        FROM batch_upload_manifest_files WHERE batch_id=%s AND upload_id=%s""",
        (batch_id, upload_id)).fetchone()
    if not expected or expected["filename"] != filename or expected["declared_size"] != size:
        raise HTTPException(409, "Файл отсутствует в манифесте партии или изменился")
    if batch["upload_manifest_state"] == "complete":
        raise HTTPException(409, "Загрузка этой партии уже завершена")


def reconcile_locked(db, batch_id):
    """Caller holds batches FOR UPDATE. Verify every registered original on disk."""
    manifest = db.execute("""SELECT upload_manifest_state FROM batches
        WHERE id=%s""", (batch_id,)).fetchone()
    if not manifest or manifest["upload_manifest_state"] is None:
        return None
    # Most calls happen while thousands of files are still arriving.
    # A cheap indexed existence check avoids materializing every row on each finish.
    incomplete = db.execute("""SELECT 1 FROM batch_upload_manifest_files m
        LEFT JOIN uploads u ON u.id=m.upload_id
        WHERE m.batch_id=%s AND (u.id IS NULL OR u.kind!='fo'
            OR u.batch_id!=m.batch_id OR u.filename!=m.filename
            OR u.declared_size!=m.declared_size OR NOT u.finalized
            OR u.target_path IS NULL) LIMIT 1""", (batch_id,)).fetchone()
    complete = not bool(incomplete)
    if complete:
        rows = db.execute("""SELECT m.declared_size,u.target_path
            FROM batch_upload_manifest_files m JOIN uploads u ON u.id=m.upload_id
            WHERE m.batch_id=%s""", (batch_id,)).fetchall()
        complete = bool(rows)
        for row in rows:
            target = Path(row["target_path"])
            if (target.is_symlink() or not target.is_file() or
                    target.stat().st_size != row["declared_size"]):
                complete = False
                break
    db.execute("""UPDATE batches SET upload_manifest_state=%s,
        upload_manifest_completed_at=CASE WHEN %s THEN
            COALESCE(upload_manifest_completed_at,now()) ELSE NULL END
        WHERE id=%s""", ("complete" if complete else "waiting", complete, batch_id))
    if complete:
        # The receipt's unique batch ID prevents duplicate notifications after
        # repeated finish requests, a refresh, or maintenance reconciliation.
        from .library_notices import record_completed_fo
        record_completed_fo(db,batch_id)
    return complete


def status(batch_id):
    """Report new, unfinished and missing files, including uploads never started."""
    batch_id = batch_service.uid(batch_id)
    with connect() as db:
        batch = db.execute("""SELECT upload_manifest_state,upload_manifest_completed_at,
                auto_process_state,auto_process_run_id,auto_process_error,auto_process_threshold
            FROM batches WHERE id=%s""", (batch_id,)).fetchone()
        if not batch:
            raise HTTPException(404, "Партия не найдена")
        if batch["upload_manifest_state"] is None:
            return {"state": "legacy", "expected": 0, "finalized": 0,
                    "missing": 0, "pending": 0, "files": [], "auto_process_state": None,
                    "auto_process_run_id":None,"auto_process_error":None,
                    "auto_process_threshold":0.50}
        rows = db.execute("""SELECT m.upload_id,m.relative_path,m.filename,m.declared_size,
            u.id AS saved_id,u.finalized,u.target_path,u.received
            FROM batch_upload_manifest_files m LEFT JOIN uploads u ON u.id=m.upload_id
            WHERE m.batch_id=%s ORDER BY m.relative_path""", (batch_id,)).fetchall()
        # A lost acknowledgement cannot strand a batch: complete is derived server-side.
        if (rows and all(row["finalized"] for row in rows) and
                (batch["upload_manifest_state"] != "complete" or
                 any(not row["target_path"] or
                     not Path(row["target_path"]).is_file() or
                     Path(row["target_path"]).is_symlink() or
                     Path(row["target_path"]).stat().st_size != row["declared_size"]
                     for row in rows))):
            db.execute("SELECT 1 FROM batches WHERE id=%s FOR UPDATE", (batch_id,))
            reconcile_locked(db, batch_id)
            from ..db.repositories.batches import refresh_upload_state
            refresh_upload_state(db, batch_id)
            batch = db.execute("""SELECT upload_manifest_state,upload_manifest_completed_at,
                    auto_process_state,auto_process_run_id,auto_process_error,auto_process_threshold
                FROM batches WHERE id=%s""", (batch_id,)).fetchone()
        files = []
        missing = finalized = 0
        for row in rows:
            if row["saved_id"] is None:
                state = "not_started"
                missing += 1
            elif not row["finalized"]:
                state = "unfinished"
            elif (not row["target_path"] or
                    not Path(row["target_path"]).is_file() or
                    Path(row["target_path"]).is_symlink() or
                    Path(row["target_path"]).stat().st_size != row["declared_size"]):
                state = "missing_saved"
            else:
                state = "finalized"
                finalized += 1
            files.append({"upload_id": str(row["upload_id"]),
                          "relative_path": row["relative_path"],
                          "filename": row["filename"], "size": row["declared_size"],
                          "state": state, "received": row["received"] or 0})
        return {"state": batch["upload_manifest_state"],
                "completed_at": batch["upload_manifest_completed_at"],
                "expected": len(rows), "finalized": finalized,
                "auto_process_state":batch["auto_process_state"],
                "auto_process_run_id":batch["auto_process_run_id"],
                "auto_process_error":batch["auto_process_error"],
                "auto_process_threshold":batch["auto_process_threshold"],
                "missing": missing, "pending": len(rows)-finalized,
                "files": files}
