"""Published reference management on the one immutable staging architecture.

Deletion creates a new version; previous immutable objects remain available
to historical FO snapshots. Staged uploads are always accepted independently.
"""
from __future__ import annotations
from fastapi import HTTPException
from app.photos.construction import parse_key
from app.system.model_store import signature
from ..database import connect
from ..db.repositories import reference_versions
from . import reference_publication

def _sam(value):
    try:
        parse_key(value)
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

def _edit(db,*,sam=None,reference_id=None):
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    _idle(db)
    state=db.execute("""SELECT current_version_id FROM reference_library_state
        WHERE id=1 FOR UPDATE""").fetchone()
    if not state or state["current_version_id"] is None:
        raise HTTPException(409,"Библиотека не инициализирована")
    members=[dict(m) for m in reference_versions.members(db,state["current_version_id"])]
    selected=[m for m in members if
        (m["sam"]==sam if sam is not None else m["reference_id"]==reference_id)]
    if not selected:
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

def delete_photo(reference_id):
    import uuid
    try:uid=uuid.UUID(str(reference_id))
    except ValueError as exc:raise HTTPException(422,"Неверный ID образца") from exc
    with connect() as db:
        version,count=_edit(db,reference_id=uid)
    return {"deleted":True,"version":version["version_number"],"photos":count}

def delete(source):
    source=_sam(source)
    with connect() as db:
        version,count=_edit(db,sam=source)
    return {"deleted":True,"sam":source,"photos":count,
            "version":version["version_number"]}

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
