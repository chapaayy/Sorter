"""Public run summaries for photo batches, without leaking filesystem paths.

Read-only PostgreSQL projections. The authoritative run/job status comes from
jobs.status, not the potentially stale snapshot.status.
"""
from __future__ import annotations

from ..db.repositories import batches as batch_repo

_RUNS = """WITH queue_order AS (
    SELECT id, row_number() OVER (ORDER BY created_at,id)::integer AS queue_position
    FROM jobs WHERE status='queued'
) """


def _public(row):
    if not row:
        return None
    snapshot = row["snapshot"] or {}
    progress = snapshot.get("progress")
    result = {
        "id": row["id"],
        "batch_id": str(row["batch_id"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "actual_started_at": row["started_at"],
        "actual_finished_at": row["finished_at"],
        "queue_position": row["queue_position"] if row["status"] == "queued" else None,
        "grouping_threshold": snapshot.get("grouping_threshold"),
        "source": snapshot.get("source", "manual"),
        "selected_models": snapshot.get("selected_models", ["megaloc"]),
        "progress": progress if isinstance(progress, dict) else {},
        "error": snapshot.get("error"),
    }
    return result


def latest(db, batch_ids):
    """One SQL statement for all paginated batches; never one query per card."""
    if not batch_ids:
        return {}
    rows = db.execute(_RUNS + """ , newest AS (
        SELECT DISTINCT ON (batch_id)
            id,batch_id,status,snapshot,created_at,started_at,finished_at
        FROM jobs WHERE batch_id=ANY(%s)
        ORDER BY batch_id,created_at DESC,id DESC
    )
    SELECT newest.*,queue_order.queue_position
    FROM newest LEFT JOIN queue_order ON queue_order.id=newest.id""",
        (batch_ids,)).fetchall()
    return {row["batch_id"]: _public(row) for row in rows}


def last_results(db, batch_ids):
    """Keep successful older results accessible even after a failed retry."""
    if not batch_ids:
        return {}
    rows = db.execute("""SELECT DISTINCT ON (batch_id) batch_id,id
        FROM jobs WHERE batch_id=ANY(%s)
        AND status IN ('completed','completed_with_errors')
        ORDER BY batch_id,created_at DESC,id DESC""",(batch_ids,)).fetchall()
    return {row["batch_id"]:row["id"] for row in rows}


def history(db, batch_id, *, limit=20, offset=0):
    if not batch_repo.get(db,batch_id):
        return None
    total = db.execute("SELECT count(*) AS n FROM jobs WHERE batch_id=%s",
                       (batch_id,)).fetchone()["n"]
    rows = db.execute(_RUNS + """ SELECT
        j.id,j.batch_id,j.status,j.snapshot,j.created_at,j.started_at,j.finished_at,
        q.queue_position
        FROM jobs j LEFT JOIN queue_order q ON q.id=j.id
        WHERE j.batch_id=%s
        ORDER BY j.created_at DESC,j.id DESC LIMIT %s OFFSET %s""",
        (batch_id,limit,offset)).fetchall()
    return {"runs":[_public(row) for row in rows],"total":total}
