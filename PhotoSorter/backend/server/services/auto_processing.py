"""Opt-in server-side MegaLoc scheduling for newly completed manifest batches.

The cleanup service calls schedule_ready periodically; no browser, API process memory
or network acknowledgement is needed to enqueue. Every decision uses PostgreSQL.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from ..database import connect
from .batches import uid

LOGGER=logging.getLogger(__name__)


def settings():
    with connect() as db:
        row=db.execute("""SELECT auto_process_new_batches,grouping_threshold
            FROM processing_settings WHERE id=1""").fetchone()
    return {"auto_process_new_batches":row["auto_process_new_batches"],
            "grouping_threshold":row["grouping_threshold"],"model":"megaloc"}


def update_settings(*,enabled:bool,threshold:float):
    with connect() as db:
        db.execute("""UPDATE processing_settings SET
            auto_process_new_batches=%s,grouping_threshold=%s,updated_at=now()
            WHERE id=1""",(enabled,threshold))
    return settings()


def cancel(batch_id):
    """Disable only an unqueued new-batch auto request, never a queued job."""
    batch_id=uid(batch_id)
    with connect() as db:
        batch=db.execute("""SELECT delete_state,upload_manifest_state,
                auto_process_state,auto_process_run_id
            FROM batches WHERE id=%s FOR UPDATE""",(batch_id,)).fetchone()
        if not batch:raise HTTPException(404,"Партия не найдена")
        if batch["delete_state"]!="active":
            raise HTTPException(409,"Партия удаляется")
        if batch["upload_manifest_state"] is None:
            raise HTTPException(409,"Старые партии не используют автозапуск")
        if batch["auto_process_state"]=="queued" or batch["auto_process_run_id"]:
            raise HTTPException(409,"Обработка уже поставлена в очередь. Для остановки используйте задание.")
        if batch["auto_process_state"]=="manual":
            raise HTTPException(409,"Эту партию уже отправили на ручную обработку")
        db.execute("""UPDATE batches SET auto_process_state='cancelled',
            auto_process_error=NULL WHERE id=%s""",(batch_id,))
    return {"batch_id":str(batch_id),"auto_process_state":"cancelled"}


def schedule_ready(limit:int=10):
    """Create at most one run per eligible batch, serializing with manual enqueue.

    A full queue or unavailable references leaves an explicit waiting request,
    which may be checked again on the next maintenance tick. Once queued, its
    state is durable and terminal jobs never trigger a second automatic run.
    """
    from .. import jobs  # Avoid import cycle with the existing queue API.
    from app.system.model_store import files_present
    if not files_present():
        return []
    with connect() as db:
        candidates=db.execute("""SELECT id FROM batches
            WHERE auto_process_state='waiting' AND upload_manifest_state='complete'
              AND delete_state='active'
            ORDER BY upload_manifest_completed_at,id LIMIT %s""",(limit,)).fetchall()
    results=[]
    for candidate in candidates:
        batch_id=candidate["id"]
        try:
            with connect() as db:
                # Match the existing manual enqueue's lock acquisition order.
                db.execute("SELECT pg_advisory_xact_lock(723409133)")
                batch=db.execute("""SELECT id,auto_process_state,auto_process_threshold,
                    upload_manifest_state,delete_state
                    FROM batches WHERE id=%s FOR UPDATE""",(batch_id,)).fetchone()
                if (not batch or batch["auto_process_state"]!="waiting" or
                        batch["upload_manifest_state"]!="complete" or
                        batch["delete_state"]!="active"):
                    continue
                # Validate originals one last time before queueing, including
                # recovery from missing on-disk files after a previous restart.
                from .upload_manifest import reconcile_locked
                if not reconcile_locked(db,batch_id):
                    db.execute("""UPDATE batches SET auto_process_error=%s
                        WHERE id=%s""",("Проверка ФО выявила недостающие файлы",batch_id))
                    continue
                try:
                    result=jobs._enqueue_locked(db, jobs.NewRun(
                        batch_id=batch_id,grouping_threshold=batch["auto_process_threshold"]),
                        source="automatic", locked_batch=batch)
                except HTTPException as exc:
                    # No run was inserted. Retry only queue capacity / missing
                    # prerequisites, never an actual failed MegaLoc job.
                    db.execute("UPDATE batches SET auto_process_error=%s WHERE id=%s",
                               (str(exc.detail)[:500],batch_id))
                    continue
                db.execute("""UPDATE batches SET auto_process_state='queued',
                    auto_process_run_id=%s,auto_process_error=NULL WHERE id=%s""",
                    (result["id"],batch_id))
                results.append((str(batch_id),result["id"]))
        except Exception:
            LOGGER.exception("Auto enqueue failed for batch %s",batch_id)
    return results
