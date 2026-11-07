"""Passive ledger for the future shared scheduler; does not claim CPU work in stage 1."""
from __future__ import annotations

def backfill_legacy_queued(db):
    """Idempotently register legacy pending FO in their original FIFO order.

    This is a migration/reconciliation helper, NOT an alternate job selector.
    Caller must not activate the ledger until the worker switch in stage 3.
    """
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    return db.execute("""
        INSERT INTO work_queue(kind,fo_run_id,state,created_at)
        SELECT 'fo_processing',id,'queued',created_at
        FROM jobs WHERE status='queued' ORDER BY created_at,id
        ON CONFLICT (fo_run_id) DO NOTHING RETURNING seq
    """).fetchall()

def entries(db):
    """Read-only inspection of the future FIFO ledger."""
    return db.execute("""
        SELECT seq,kind,fo_run_id,reference_job_id,state,created_at
        FROM work_queue ORDER BY seq
    """).fetchall()
