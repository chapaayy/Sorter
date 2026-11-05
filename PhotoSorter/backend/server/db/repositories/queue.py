"""Atomic PostgreSQL FIFO, one global MegaLoc leader and cancellation semantics."""
from __future__ import annotations
from datetime import datetime,timezone
from psycopg.types.json import Jsonb
from ..database import connect

MAX_WAITING=20
ACTIVE=("queued","running","stopping")
TERMINAL=("completed","completed_with_errors","failed","stopped","interrupted")

def queue_count(db):
    return db.execute("SELECT count(*) AS n FROM jobs WHERE status='queued'").fetchone()["n"]

def queue_position(db,run_id):
    row=db.execute("SELECT id,created_at,status FROM jobs WHERE id=%s",(run_id,)).fetchone()
    if not row or row["status"]!="queued":return None
    return db.execute("""SELECT count(*) AS n FROM jobs
        WHERE status='queued' AND (created_at,id)<=(%s,%s)""",
        (row["created_at"],run_id)).fetchone()["n"]

def decorated(db,row):
    info=dict(row["snapshot"])
    info["status"]=row["status"]
    info["queue_position"]=queue_position(db,row["id"]) if row["status"]=="queued" else None
    if row.get("started_at"):info["actual_started_at"]=row["started_at"].isoformat()
    if row.get("finished_at"):info["actual_finished_at"]=row["finished_at"].isoformat()
    return info

def next_job(db):
    # Global scheduling gate even if a second process bypasses worker leader loop.
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    if db.execute("SELECT 1 FROM jobs WHERE status IN ('running','stopping') LIMIT 1").fetchone():
        return None
    row=db.execute("""SELECT j.id,j.snapshot FROM jobs j JOIN batches b ON b.id=j.batch_id
        WHERE j.status='queued' AND b.delete_state='active'
        ORDER BY j.created_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1""").fetchone()
    if not row:return None
    snapshot=dict(row["snapshot"])
    snapshot["status"]="running"
    snapshot["actual_started_at"]=datetime.now(timezone.utc).isoformat()
    db.execute("""UPDATE jobs SET status='running',stop_requested=false,
        started_at=now(),updated_at=now(),snapshot=%s WHERE id=%s""",
        (Jsonb(snapshot),row["id"]))
    return snapshot

def mark_interrupted(db):
    db.execute("""UPDATE jobs SET status='interrupted',finished_at=now(),
      snapshot=jsonb_set(snapshot,'{status}',to_jsonb('interrupted'::text)),
      updated_at=now() WHERE status IN ('running','stopping')""")

def finish_job(db,run_id,status):
    db.execute("""UPDATE jobs SET status=%s,finished_at=now(),updated_at=now()
        WHERE id=%s AND status NOT IN ('completed','completed_with_errors','failed','stopped','interrupted')""",
        (status,run_id))
