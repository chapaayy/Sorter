"""Published reference management on the one immutable staging architecture.

Deletion creates a new version; previous immutable objects remain available
to historical FO snapshots. Staged uploads are always accepted independently.
"""
from __future__ import annotations
import uuid
from fastapi import HTTPException
from app.photos.labels import check_label
from app.system.model_store import signature
from ..database import connect
from ..db.repositories import reference_versions
from . import reference_publication

def _sam(value):
    try:
        if check_label(value)!=value:
            raise ValueError('Некорректный номер или название')
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    return value

def _idle(db):
    # Synchronous removals cannot jump ahead of earlier FIFO work. Uploads
    # never use this guard: they always go to staging.
    if db.execute("""SELECT 1 FROM work_queue
        WHERE state IN ('queued','running')
           OR (kind='reference_preparation'
               AND state IN ('failed','interrupted','blocked'))
        LIMIT 1""").fetchone():
        raise HTTPException(409,"Удаление доступно после завершения очереди")

def _edit(db,*,sam=None,reference_id=None,skip_idle=False):
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    if not skip_idle:
        _idle(db)
    state=db.execute("""SELECT current_version_id FROM reference_library_state
        WHERE id=1 FOR UPDATE""").fetchone()
    if not state or state["current_version_id"] is None:
        raise HTTPException(409,"Библиотека не инициализирована")
    members=[dict(m) for m in reference_versions.members(db,state["current_version_id"])]
    selected=[m for m in members if
        (m["sam"]==sam if sam is not None else m["reference_id"]==reference_id)]
    if not selected:
        if sam is None or not db.execute(
            "SELECT 1 FROM reference_constructions WHERE sam=%s",(sam,)).fetchone():
            raise HTTPException(404,"Образец или конструкция не найдены")
    remaining=[m for m in members if m not in selected]
    current=reference_versions.current(db)
    fp=signature()
    # Removing a published entry does not compute vectors and must preserve
    # the signature of the snapshot, regardless of locally installed weights.
    version,_=reference_publication.publish(
        db,remaining,current["model_signature"] or fp,event_kind="reference_prepared")
    if sam is None:
        db.execute("DELETE FROM uploads WHERE id=%s AND kind='reference'",(reference_id,))
    else:
        db.execute("DELETE FROM uploads WHERE sam=%s AND kind='reference'",(sam,))
        db.execute("DELETE FROM reference_constructions WHERE sam=%s",(sam,))
    return version,len(selected)

def _has_busy_queue(db):
    return bool(db.execute("""SELECT 1 FROM work_queue
        WHERE state IN ('queued','running') OR
              (kind='reference_preparation' AND state IN ('failed','interrupted','blocked'))
        LIMIT 1""").fetchone())


def _enqueue_delete(db,*,reference_id=None,sam=None):
    # Validate against current library now, not only at eventual execution.
    if reference_id is not None:
        exists=db.execute("""SELECT 1 FROM reference_version_members m
            JOIN reference_library_state s ON s.current_version_id=m.version_id
            WHERE m.reference_id=%s""",(reference_id,)).fetchone()
    else:
        exists=db.execute("SELECT 1 FROM reference_constructions WHERE sam=%s",(sam,)).fetchone()
    if not exists:
        raise HTTPException(404,"Образец или конструкция не найдены")
    duplicate=db.execute("""SELECT d.id FROM reference_deletion_tasks d
        JOIN work_queue w ON w.reference_deletion_id=d.id
        WHERE w.state IN ('queued','running')
          AND (%s::uuid IS NOT NULL AND d.reference_id=%s OR
               %s::text IS NOT NULL AND d.sam=%s)
        LIMIT 1""",(reference_id,reference_id,sam,sam)).fetchone()
    if duplicate:
        return {"queued":True,"task_id":str(duplicate['id'])}
    task_id=uuid.uuid4()
    db.execute("""INSERT INTO reference_deletion_tasks(id,reference_id,sam)
        VALUES (%s,%s,%s)""",(task_id,reference_id,sam))
    db.execute("""INSERT INTO work_queue(kind,reference_deletion_id,state)
        VALUES ('reference_deletion',%s,'queued')""",(task_id,))
    return {"queued":True,"task_id":str(task_id)}


def delete_photo(reference_id):
    try:uid=uuid.UUID(str(reference_id))
    except ValueError as exc:raise HTTPException(422,"Неверный ID образца") from exc
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        if _has_busy_queue(db):
            return _enqueue_delete(db,reference_id=uid)
        version,count=_edit(db,reference_id=uid)
    return {"deleted":True,"version":version["version_number"],"photos":count}


def delete(source):
    source=_sam(source)
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        if _has_busy_queue(db):
            return _enqueue_delete(db,sam=source)
        version,count=_edit(db,sam=source)
    return {"deleted":True,"sam":source,"photos":count,
            "version":version["version_number"]}


def process_deferred(task_id):
    # Runs only after all earlier FIFO items have completed, using the same
    # immutable publication transaction as synchronous removal.
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        task=db.execute("""SELECT reference_id,sam FROM reference_deletion_tasks
            WHERE id=%s""",(task_id,)).fetchone()
        if not task:
            raise RuntimeError("Задание удаления образца не найдено")
        _edit(db,reference_id=task["reference_id"],sam=task["sam"],skip_idle=True)
        db.execute("""UPDATE work_queue SET state='completed',finished_at=now()
            WHERE reference_deletion_id=%s AND state='running'""",(task_id,))

def cache_status():
    try:fp=signature()
    except (OSError,ValueError):fp=None
    with connect() as db:
        row=db.execute("""
            SELECT count(DISTINCT m.source_hash) AS total,
               count(DISTINCT m.source_hash) FILTER (WHERE EXISTS (
                 SELECT 1 FROM reference_cache c
                 WHERE c.source_hash=m.source_hash AND c.model_signature=%s)) AS cached
            FROM reference_version_members m
            JOIN reference_library_state s ON s.current_version_id=m.version_id
            WHERE s.id=1
        """,(fp or "",)).fetchone()
    return {"total":row["total"],"cached":row["cached"],"current_signature":fp}
