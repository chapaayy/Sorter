"""Owner-facing projections of the existing registry, never a disk walk."""
from ..database import connect
from ..storage.accounting import SUMS,snapshot
from ..storage.reporting import counter
from app.storage.categories import ARCHIVE_TTL_SECONDS,TEMPORARY_GRACE_SECONDS
from . import heartbeat

def accounts(offset=0,limit=25):
    data=snapshot()
    with connect() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        total=db.execute("SELECT count(*) AS n FROM users").fetchone()["n"]
        rows=db.execute("""SELECT id::text,username,access_role FROM users
          ORDER BY id LIMIT %s OFFSET %s""",(limit,offset)).fetchall()
    for row in rows:
        row["usage"]=data.get("owners",{}).get(row["id"],counter() if data.get("sampled_at") else None)
    return {"rows":rows,"total":total,"offset":offset,"limit":limit,
            "sampled_at":data["sampled_at"],"partial":data["partial"]}

def account_detail(owner,offset=0,limit=25):
    from fastapi import HTTPException
    with connect() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        user=db.execute("SELECT id::text,username,access_role FROM users WHERE id=%s",(owner,)).fetchone()
        if not user:raise HTTPException(404,"Аккаунт не найден")
        groups=db.execute("SELECT category,"+SUMS+""" FROM storage_accounted_files
          WHERE owner_id=%s AND scope='personal' GROUP BY category ORDER BY category""",(owner,)).fetchall()
        total=db.execute("SELECT count(*) AS n FROM batches WHERE owner_id=%s AND delete_state<>'deleted'",(owner,)).fetchone()["n"]
        rows=db.execute("""WITH selected AS (
          SELECT id,display_name FROM batches WHERE owner_id=%s AND delete_state<>'deleted'
          ORDER BY created_at DESC,id LIMIT %s OFFSET %s)
          SELECT s.id::text AS batch_id,s.display_name,f.category,"""+SUMS+"""
          FROM selected s JOIN storage_accounted_files f ON f.batch_id=s.id
          WHERE f.owner_id=%s AND f.scope='personal' GROUP BY s.id,s.display_name,f.category""",
          (owner,limit,offset,owner)).fetchall()
        batches=db.execute("""SELECT id::text AS batch_id,display_name FROM batches
          WHERE owner_id=%s AND delete_state<>'deleted' ORDER BY created_at DESC,id LIMIT %s OFFSET %s""",
          (owner,limit,offset)).fetchall()
        sampled=db.execute("SELECT sampled_at FROM storage_accounting_state").fetchone()["sampled_at"]
    index={b["batch_id"]:dict(b,categories={}) for b in batches}
    for row in rows:
        index[row["batch_id"]]["categories"][row["category"]]={k:row[k] for k in counter()}
    return {"account":user,"categories":{r["category"]:{k:r[k] for k in counter()} for r in groups},
            "batches":list(index.values()),"total":total,"offset":offset,"limit":limit,
            "sampled_at":sampled.isoformat() if sampled else None,
            "basis":"live_registry_rows_global_inode_attribution"}

def operational():
    with connect() as db:
        active=db.execute("""SELECT w.seq,w.kind,w.state,w.fo_run_id,
          coalesce(w.media_batch_id,j.batch_id)::text AS batch_id,
          b.display_name,w.started_at
          FROM work_queue w LEFT JOIN jobs j ON j.id=w.fo_run_id
          LEFT JOIN batches b ON b.id=coalesce(w.media_batch_id,j.batch_id)
          WHERE w.state='running' ORDER BY w.seq LIMIT 100""").fetchall()
        # Ready ZIP expiry is based on the publication mtime, not last access.
        archives=db.execute("""SELECT category,count(*) AS files,
          min(mtime_ns) AS oldest_mtime_ns,
          count(*) FILTER(WHERE mtime_ns<=extract(epoch FROM now())*1000000000-%s*1000000000::numeric) AS expired
          FROM storage_files WHERE category IN ('zip_results','zip_construction','zip_references')
          AND kind='file' GROUP BY category""",(ARCHIVE_TTL_SECONDS,)).fetchall()
        fo=db.execute("""SELECT min(updated_at+interval '30 days') AS next_eligible_at
          FROM uploads WHERE kind='fo' AND NOT finalized""").fetchone()
        refs=db.execute("""SELECT min(GREATEST(s.created_at,COALESCE(s.manifest_registered_at,s.created_at),
            COALESCE((SELECT max(f.updated_at) FROM reference_import_files f WHERE f.session_id=s.id),s.created_at))
            +interval '30 days') AS next_eligible_at
          FROM reference_import_sessions s WHERE s.upload_state='uploading'""").fetchone()
        health=heartbeat.status(db)["cleanup"]
    for row in archives:
        from datetime import datetime,timezone
        row["next_eligible_at"]=datetime.fromtimestamp(row.pop("oldest_mtime_ns")/1e9+ARCHIVE_TTL_SECONDS,timezone.utc).isoformat()
    return {"active_queue":active,"archives":archives,"unfinished_fo_next_eligible_at":fo["next_eligible_at"],
            "unfinished_reference_next_eligible_at":refs["next_eligible_at"],
            "archive_ttl_seconds":ARCHIVE_TTL_SECONDS,"scratch_grace_seconds":TEMPORARY_GRACE_SECONDS,
            "cleanup_worker":health}

def request_reconciliation():
    with connect() as db:
        row=db.execute("""UPDATE storage_accounting_state SET requested_at=CASE
          WHEN requested_at IS NOT NULL AND (started_at IS NULL OR requested_at>started_at)
          THEN requested_at ELSE clock_timestamp() END RETURNING requested_at""").fetchone()
    return {"requested_at":row["requested_at"]}
