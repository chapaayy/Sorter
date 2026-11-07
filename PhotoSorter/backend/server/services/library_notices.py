"""One site-wide acknowledgement of recognition-affecting library changes.

Future actor scopes use separate library_notice_cursors rows, never browser
localStorage. Display is read-only; only explicit user acknowledgement writes.
"""
from __future__ import annotations

import os
from fastapi import HTTPException
from ..database import connect

INSTALLATION="installation"
RECOGNITION_EVENTS=("reference_prepared","legacy_reconcile")
MESSAGE=("Образцы конструкций обновились с момента предыдущей загрузки ФО. "
         "Результаты новых обработок могут отличаться от прежних.")

def _latest(db):
    return db.execute("""
        SELECT v.id,v.version_number,v.published_at,v.manifest_digest,
               s.baseline_state,s.baseline_error
        FROM reference_library_state s
        LEFT JOIN reference_library_versions v ON v.id=s.current_version_id
        WHERE s.id=1
    """).fetchone()

def _cursor(db,scope=INSTALLATION,lock=False):
    return db.execute("""
        SELECT scope_key,last_fo_upload_version_id,last_fo_uploaded_at,
               acknowledged_version_id,acknowledged_at
        FROM library_notice_cursors WHERE scope_key=%s
    """ + (" FOR UPDATE" if lock else ""), (scope,)).fetchone()

def _changed_since(db,version_id):
    return db.execute("""
        SELECT count(*) AS n,max(e.version_id) AS latest
        FROM reference_library_events e
        WHERE e.version_id > %s
          AND e.event_kind=ANY(%s)
    """,(version_id, list(RECOGNITION_EVENTS))).fetchone()

def seed_existing_fo_cursor(db):
    """On upgrade, seed the global acknowledgement after a verified baseline.

    The SQL migration also attempts this for installs with existing versions.
    This second, ON CONFLICT DO NOTHING path covers direct upgrades where
    ensure_baseline publishes the first V1 *after* migrations run.
    """
    current=_latest(db)
    if not current or current["id"] is None:
        return
    db.execute("""
        WITH old_completed AS (
            SELECT MAX(completed_at) AS last_fo FROM (
                SELECT b.upload_manifest_completed_at AS completed_at
                FROM batches b
                WHERE b.upload_manifest_state='complete'
                  AND b.upload_manifest_completed_at IS NOT NULL
                UNION ALL
                SELECT MAX(u.updated_at) AS completed_at
                FROM jobs j JOIN uploads u ON u.batch_id=j.batch_id
                  AND u.kind='fo' AND u.finalized
            ) existing
        )
        INSERT INTO library_notice_cursors(
            scope_key,last_fo_upload_version_id,last_fo_uploaded_at,
            acknowledged_version_id,acknowledged_at)
        SELECT %s,%s,old_completed.last_fo,%s,now()
        FROM old_completed WHERE old_completed.last_fo IS NOT NULL
        ON CONFLICT(scope_key) DO NOTHING
    """,(INSTALLATION,current["id"],current["id"]))

def record_completed_fo(db,batch_id):
    """Call in the same transaction as a verified FO-manifest completion.

    Receipt is unique per batch; repeat finish/reconcile never updates baseline.
    Older FO batches do not reset the cursor after their next processing run.
    """
    current=_latest(db)
    if not current or current["id"] is None:
        return
    # Always serialize concurrent file-finalization completions at the cursor.
    db.execute("""
        INSERT INTO library_notice_cursors(scope_key)
        VALUES (%s) ON CONFLICT(scope_key) DO NOTHING
    """,(INSTALLATION,))
    cursor=_cursor(db,lock=True)
    receipt=db.execute("""
        INSERT INTO fo_library_upload_receipts(batch_id,version_id)
        VALUES (%s,%s) ON CONFLICT(batch_id) DO NOTHING RETURNING batch_id
    """,(batch_id,current["id"])).fetchone()
    if not receipt:
        return
    # First successfully uploaded FO establishes the baseline; no warning
    # about earlier reference changes.
    if cursor["last_fo_uploaded_at"] is None:
        db.execute("""
            UPDATE library_notice_cursors SET
                last_fo_upload_version_id=%s,last_fo_uploaded_at=now(),
                acknowledged_version_id=%s,acknowledged_at=now()
            WHERE scope_key=%s
        """,(current["id"],current["id"],INSTALLATION))
    else:
        db.execute("""
            UPDATE library_notice_cursors SET
                last_fo_upload_version_id=%s,last_fo_uploaded_at=now()
            WHERE scope_key=%s
        """,(current["id"],INSTALLATION))

def status():
    with connect() as db:
        current=_latest(db)
        cursor=_cursor(db)
        ack=cursor["acknowledged_version_id"] if cursor else None
        pending=(_changed_since(db,ack or 0) if cursor and
                 cursor["last_fo_uploaded_at"] is not None else {"n":0,"latest":None})
        latest=db.execute("""
            SELECT count(*) AS n FROM reference_version_members
            WHERE version_id=%s
        """,(current["id"],)).fetchone()["n"] if current and current["id"] else 0
    unified=os.environ.get("PHOTOSORTER_UNIFIED_QUEUE")=="1"
    staging=os.environ.get("REFERENCE_IMPORT_STAGING_ENABLED")=="1" and unified
    return {
        "unified_queue_enabled":unified,
        "staged_imports_enabled":staging,
        "current_version_id":current["id"] if current else None,
        "current_version":current["version_number"] if current else None,
        "published_at":current["published_at"] if current else None,
        "published_references":latest,
        "baseline_state":current["baseline_state"] if current else "pending",
        "baseline_error":current["baseline_error"] if current else None,
        "last_fo_uploaded_at":cursor["last_fo_uploaded_at"] if cursor else None,
        "last_fo_upload_version_id":cursor["last_fo_upload_version_id"] if cursor else None,
        "acknowledged_version_id":ack,
        "pending_changes":pending["n"],
        "notice_version_id":pending["latest"],
        "notice":bool(pending["n"]),
        "message":MESSAGE,
    }

def history(limit=30,after_version=None):
    if limit<1 or limit>100:
        raise HTTPException(422,"Неверный размер истории")
    with connect() as db:
        events=db.execute("""
            SELECT e.id,e.version_id,v.version_number,e.event_kind,
                   e.actor,e.details,e.created_at
            FROM reference_library_events e
            JOIN reference_library_versions v ON v.id=e.version_id
            WHERE (%s::bigint IS NULL OR e.version_id > %s::bigint)
            ORDER BY e.id DESC LIMIT %s
        """,(after_version,after_version,limit)).fetchall()
    return {"events":events}

def acknowledge(version_id:int):
    with connect() as db:
        db.execute("""
            INSERT INTO library_notice_cursors(scope_key)
            VALUES (%s) ON CONFLICT(scope_key) DO NOTHING
        """,(INSTALLATION,))
        cursor=_cursor(db,lock=True)
        current=_latest(db)
        if not current or current["id"] is None:
            raise HTTPException(409,"Пока нет опубликованной библиотеки")
        if not cursor["last_fo_uploaded_at"]:
            raise HTTPException(409,"Сначала должна завершиться загрузка хотя бы одной партии ФО")
        if version_id<=0 or version_id>current["id"]:
            raise HTTPException(409,"Неизвестная версия уведомления")
        # A response can be repeated after VPN reconnection, but an older
        # acknowledgement cannot hide a newer publication.
        previous=cursor["acknowledged_version_id"] or 0
        if version_id>previous:
            db.execute("""
                UPDATE library_notice_cursors SET acknowledged_version_id=%s,
                    acknowledged_at=now() WHERE scope_key=%s
            """,(version_id,INSTALLATION))
    return status()
