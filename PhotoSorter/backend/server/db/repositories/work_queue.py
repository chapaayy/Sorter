"""The single authoritative FIFO queue for FO and reference preparations.

All insertions and claims use advisory lock 723409133. Never bypass a failed
reference preparation: explicit retry/skip keeps the original sequence number.
"""
from __future__ import annotations
from datetime import datetime,timezone
from psycopg.types.json import Jsonb
from app.system.model_store import signature
from . import reference_versions

LOCK=723409133
MAX_WAITING=20
TERMINAL=("completed","completed_with_errors","failed","stopped","interrupted")

def queued_fo_count(db):
    return db.execute("""
        SELECT count(*) AS n FROM work_queue
        WHERE kind='fo_processing' AND state='queued'
    """).fetchone()["n"]

def position(db,run_id):
    entry=db.execute("""
        SELECT seq FROM work_queue WHERE fo_run_id=%s AND state='queued'
    """,(run_id,)).fetchone()
    if not entry:return None
    return db.execute("""
        SELECT count(*) AS n FROM work_queue
        WHERE seq<=%s AND (state='queued' OR
          (kind='reference_preparation' AND state IN ('failed','interrupted','blocked')))
    """,(entry["seq"],)).fetchone()["n"]

def insert_fo(db,run_id):
    """Caller owns FIFO advisory lock; jobs and queue row commit together."""
    result=db.execute("""
        INSERT INTO work_queue(kind,fo_run_id,state,created_at)
        SELECT 'fo_processing',id,'queued',created_at FROM jobs WHERE id=%s
        RETURNING seq
    """,(run_id,)).fetchone()
    if result is None:
        raise RuntimeError("Failed to place FO into the common FIFO")
    return result["seq"]

def entries(db):
    return db.execute("""
        SELECT seq,kind,fo_run_id,reference_job_id,state,created_at,
               started_at,finished_at FROM work_queue ORDER BY seq
    """).fetchall()

def claim_next(db):
    """Claim at most one global CPU task. Never scan old live directories."""
    from ...services import reference_publication
    db.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK,))
    if db.execute("""
        SELECT 1 FROM work_queue WHERE state='running' LIMIT 1
    """).fetchone():
        return None
    row=db.execute("""
        SELECT seq,kind,fo_run_id,reference_job_id,state FROM work_queue
        WHERE state='queued' OR
          (kind='reference_preparation' AND state IN ('failed','interrupted','blocked'))
        ORDER BY seq FOR UPDATE LIMIT 1
    """).fetchone()
    if row is None or row["state"]!="queued":
        return None
    if row["kind"]=="reference_preparation":
        prep=db.execute("""
            SELECT id,session_id,state FROM reference_preparation_jobs
            WHERE id=%s FOR UPDATE
        """,(row["reference_job_id"],)).fetchone()
        if not prep or prep["state"]!="queued":
            raise RuntimeError("Reference preparation queue state mismatch")
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
            UPDATE work_queue SET state='running',started_at=now()
            WHERE seq=%s
        """,(row["seq"],))
        return {"kind":"reference_preparation","id":prep["id"],
                "session_id":prep["session_id"],"seq":row["seq"]}

    fo=db.execute("""
        SELECT j.id,j.status,j.snapshot,b.delete_state
        FROM jobs j JOIN batches b ON b.id=j.batch_id
        WHERE j.id=%s FOR UPDATE OF j
    """,(row["fo_run_id"],)).fetchone()
    if not fo or fo["status"]!="queued" or fo["delete_state"]!="active":
        db.execute("""
            UPDATE work_queue SET state='stopped',finished_at=now()
            WHERE seq=%s
        """,(row["seq"],))
        return None
    fp=signature()
    if not fp:
        raise RuntimeError("MegaLoc model not installed")
    current=reference_versions.current(db)
    if not current or current["baseline_state"]!="ready" or current["id"] is None:
        raise RuntimeError("Reference library not initialized")
    if current["model_signature"] and current["model_signature"]!=fp:
        raise RuntimeError("Reference vectors require preparation with current MegaLoc")
    pinned=reference_publication.snapshot(db,current["id"])
    if not pinned:
        raise RuntimeError("Published reference library is empty")
    info=dict(fo["snapshot"])
    info.update({"status":"running",
        "actual_started_at":datetime.now(timezone.utc).isoformat(),
        "reference_version":current["version_number"],
        "reference_version_id":current["id"],
        "reference_manifest_digest":current["manifest_digest"],
        "model_signature":fp,"reference_members":pinned})
    db.execute("""
        UPDATE jobs SET status='running',stop_requested=false,started_at=now(),
            updated_at=now(),snapshot=%s WHERE id=%s
    """,(Jsonb(info),fo["id"]))
    db.execute("""
        UPDATE work_queue SET state='running',started_at=now() WHERE seq=%s
    """,(row["seq"],))
    return {"kind":"fo_processing","id":fo["id"],"info":info,"seq":row["seq"]}

def finish_fo(db,run_id,status):
    db.execute("""
        UPDATE work_queue SET state=%s,finished_at=now()
        WHERE fo_run_id=%s AND state IN ('queued','running','blocked')
    """,(status,run_id))

def fail_fo(db,run_id):
    db.execute("""
        UPDATE jobs SET status='failed',finished_at=now(),updated_at=now()
        WHERE id=%s AND status IN ('running','stopping')
    """,(run_id,))
    finish_fo(db,run_id,"failed")

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
    """Leader recovery; failed preparations remain FIFO barriers."""
    db.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK,))
    db.execute("""
        UPDATE jobs SET status='interrupted',finished_at=now(),updated_at=now(),
            snapshot=CASE
              WHEN snapshot->>'archive_state'='preparing'
              THEN jsonb_set(jsonb_set(snapshot,'{status}',to_jsonb('interrupted'::text)),
                  '{archive_state}',to_jsonb('failed'::text))
              ELSE jsonb_set(snapshot,'{status}',to_jsonb('interrupted'::text))
            END
        WHERE status IN ('running','stopping')
    """)
    db.execute("""
        UPDATE reference_preparation_jobs SET state='interrupted',
            error='Worker stopped during preparation',finished_at=now()
        WHERE state='running'
    """)
    db.execute("""
        UPDATE reference_import_sessions s SET preparation_state='interrupted',
            error='Worker stopped during preparation'
        FROM reference_preparation_jobs p WHERE p.session_id=s.id
          AND p.state='interrupted' AND s.preparation_state='running'
    """)
    db.execute("""
        UPDATE work_queue SET state='interrupted',finished_at=now()
        WHERE state='running'
    """)
