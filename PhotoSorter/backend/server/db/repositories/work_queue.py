"""Authoritative FIFO claim under the original global scheduler advisory lock.

The old /api/runs still reads the jobs table. Every FO enqueue gets one ledger
row. Only the leader may claim a new CPU task from this ledger.
"""
from __future__ import annotations

from datetime import datetime,timezone
from psycopg.types.json import Jsonb
from app.system.model_store import signature

LOCK=723409133
FO_TERMINAL=("completed","completed_with_errors","failed","stopped","interrupted")
PREP_BARRIER=("failed","interrupted","blocked")

def backfill_legacy_queued(db):
    db.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK,))
    return db.execute("""
        INSERT INTO work_queue(kind,fo_run_id,state,created_at)
        SELECT 'fo_processing',id,'queued',created_at
        FROM jobs WHERE status='queued' ORDER BY created_at,id
        ON CONFLICT (fo_run_id) DO NOTHING RETURNING seq
    """).fetchall()

def insert_fo(db,run_id):
    row=db.execute("""
        INSERT INTO work_queue(kind,fo_run_id,state,created_at)
        SELECT 'fo_processing',id,'queued',created_at FROM jobs WHERE id=%s
        ON CONFLICT (fo_run_id) DO UPDATE SET
           fo_run_id=EXCLUDED.fo_run_id RETURNING seq
    """,(run_id,)).fetchone()
    if row is None:
        raise RuntimeError("Невозможно зарегистрировать ФО в общей очереди")
    return row["seq"]

def entries(db):
    return db.execute("""
        SELECT seq,kind,fo_run_id,reference_job_id,state,created_at,
               started_at,finished_at FROM work_queue ORDER BY seq
    """).fetchall()

def sync_legacy_status(db):
    """Repair any legacy or interrupted state without deleting queue history."""
    db.execute("""
        UPDATE work_queue w SET state=j.status,
            started_at=COALESCE(w.started_at,j.started_at),
            finished_at=COALESCE(w.finished_at,j.finished_at)
        FROM jobs j WHERE w.fo_run_id=j.id AND w.kind='fo_processing'
          AND w.state!=j.status
          AND (j.status IN ('stopped','failed','interrupted',
                           'completed','completed_with_errors') OR
               (w.state='queued' AND j.status='running'))
    """)
    # Deleted historical batches may have removed jobs without clearing ledger.
    db.execute("""
        UPDATE work_queue w SET state='stopped',finished_at=now()
        WHERE w.kind='fo_processing' AND w.state='queued'
          AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.id=w.fo_run_id)
    """)

def claim_next(db):
    """Never skip a failed reference preparation or an earlier work item."""
    from ...services import reference_publication
    db.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK,))
    backfill_legacy_queued(db)
    sync_legacy_status(db)
    if db.execute("""SELECT 1 FROM jobs WHERE status IN ('running','stopping') LIMIT 1""").fetchone():
        return None
    if db.execute("""SELECT 1 FROM reference_preparation_jobs WHERE state='running' LIMIT 1""").fetchone():
        return None

    row=db.execute("""
        SELECT seq,kind,fo_run_id,reference_job_id,state FROM work_queue
        WHERE state='queued' OR (kind='reference_preparation'
                     AND state IN ('failed','interrupted','blocked'))
        ORDER BY seq FOR UPDATE LIMIT 1
    """).fetchone()
    if not row or row["state"]!='queued':
        return None

    # Stage-1 V1 contains legacy mutable paths. Convert/synchronize it under
    # the same scheduler lock before dispatching EITHER kind of CPU task.
    fp=signature()
    if not fp:
        raise RuntimeError("MegaLoc недоступна — очередь остаётся неизменной")
    current=reference_publication.reconcile_legacy(db,model_signature=fp)

    if row["kind"]=="reference_preparation":
        prep=db.execute("""
            SELECT id,session_id,state FROM reference_preparation_jobs
            WHERE id=%s FOR UPDATE
        """,(row["reference_job_id"],)).fetchone()
        if not prep or prep["state"]!="queued":
            raise RuntimeError("Несогласованное состояние подготовки образцов")
        db.execute("""
            UPDATE reference_preparation_jobs SET state='running',
                stop_requested=false,started_at=now(),updated_at=now()
            WHERE id=%s
        """,(prep["id"],))
        db.execute("""
            UPDATE reference_import_sessions SET preparation_state='running'
            WHERE id=%s
        """,(prep["session_id"],))
        db.execute("""
            UPDATE work_queue SET state='running',started_at=now() WHERE seq=%s
        """,(row["seq"],))
        return {"kind":"reference_preparation","id":prep["id"],
                "session_id":prep["session_id"],"seq":row["seq"]}

    job=db.execute("""
        SELECT j.id,j.status,j.snapshot,b.delete_state
        FROM jobs j JOIN batches b ON b.id=j.batch_id
        WHERE j.id=%s FOR UPDATE OF j
    """,(row["fo_run_id"],)).fetchone()
    if not job or job["status"]!="queued" or job["delete_state"]!="active":
        db.execute("""
            UPDATE work_queue SET state='stopped',finished_at=now() WHERE seq=%s
        """,(row["seq"],))
        return None
    # Resolve newest published version at *actual claim*, never on enqueue.
    pinned=reference_publication.snapshot(db,current["id"])
    if not pinned:
        raise RuntimeError("Нет подготовленных образцов")
    info=dict(job["snapshot"])
    info.update({"status":"running","actual_started_at":datetime.now(timezone.utc).isoformat(),
                 "reference_version":current["version_number"],
                 "reference_version_id":current["id"],
                 "reference_manifest_digest":current["manifest_digest"],
                 "model_signature":fp,"reference_members":pinned})
    db.execute("""
        UPDATE jobs SET status='running',stop_requested=false,started_at=now(),
            updated_at=now(),snapshot=%s WHERE id=%s
    """,(Jsonb(info),job["id"]))
    db.execute("""
        UPDATE work_queue SET state='running',started_at=now() WHERE seq=%s
    """,(row["seq"],))
    return {"kind":"fo_processing","id":job["id"],"info":info,"seq":row["seq"]}

def finish_fo(db,run_id,status):
    db.execute("""
        UPDATE work_queue SET state=%s,finished_at=now()
        WHERE fo_run_id=%s AND state IN ('queued','running','blocked')
    """,(status,run_id))

def finish_preparation(db,job_id,status,error=None):
    db.execute("""
        UPDATE reference_preparation_jobs SET state=%s,error=%s,
            finished_at=now(),updated_at=now() WHERE id=%s
            AND state NOT IN ('completed','stopped')
    """,(status,error,job_id))
    db.execute("""
        UPDATE reference_import_sessions s SET preparation_state=%s,error=%s
        FROM reference_preparation_jobs p WHERE p.id=%s AND p.session_id=s.id
    """,(status,error,job_id))
    db.execute("""
        UPDATE work_queue SET state=%s,finished_at=now()
        WHERE reference_job_id=%s AND state='running'
    """,(status,job_id))

def mark_interrupted(db):
    db.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK,))
    db.execute("""
        UPDATE reference_preparation_jobs SET state='interrupted',
            error='Worker завершился во время подготовки',finished_at=now()
        WHERE state='running'
    """)
    db.execute("""
        UPDATE reference_import_sessions s SET preparation_state='interrupted',
            error='Worker завершился во время подготовки'
        FROM reference_preparation_jobs p WHERE p.session_id=s.id
          AND p.state='interrupted' AND s.preparation_state='running'
    """)
    db.execute("""
        UPDATE work_queue SET state='interrupted',finished_at=now()
        WHERE kind='reference_preparation' AND state='running'
    """)
    sync_legacy_status(db)
