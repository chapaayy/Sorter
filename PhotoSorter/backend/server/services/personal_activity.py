"""Small authenticated status projection. Never expose names, paths or foreign IDs."""
from ..database import connect
from ..security.roles import has

def snapshot(user):
    owner=user["id"]
    parts=[]
    args=[]
    def include(sql):
        parts.append(sql)
        args.append(owner)
    if has(user,"queue.view"):
        include("""
            SELECT 'fo' AS kind,w.seq,w.fo_run_id AS run_id,w.finished_at,
                   CASE WHEN w.state='running' AND j.status='stopping' THEN 'stopping' ELSE w.state END AS state,
                   j.snapshot->'progress'->'overall_percent' AS progress
            FROM batches b JOIN jobs j ON j.batch_id=b.id
            JOIN work_queue w ON w.fo_run_id=j.id
            WHERE b.owner_id=%s AND b.delete_state='active' AND w.kind='fo_processing'
        """)
        include("""
            SELECT 'media',w.seq,'media:'||w.seq::text,w.finished_at,w.state,
                   to_jsonb(w.media_progress_percent)
            FROM batches b JOIN work_queue w ON w.media_batch_id=b.id
            WHERE b.owner_id=%s AND b.delete_state='active' AND w.kind='media_preparation'
        """)
    if has(user,"references.view") and has(user,"references.import"):
        include("""
            SELECT 'reference',w.seq,'reference:'||p.id::text,w.finished_at,
                   CASE WHEN w.state='running' AND p.stop_requested THEN 'stopping' ELSE w.state END,
                   to_jsonb(100.0*p.completed_count/nullif(p.total_count,0))
            FROM reference_import_sessions s JOIN reference_preparation_jobs p ON p.session_id=s.id
            JOIN work_queue w ON w.reference_job_id=p.id WHERE s.requested_by=%s
        """)
    if has(user,"references.view") and (has(user,"references.delete") or has(user,"references.delete_file")):
        include("""
            SELECT 'reference-delete',w.seq,'reference-delete:'||d.id::text,w.finished_at,w.state,NULL::jsonb
            FROM reference_deletion_tasks d JOIN work_queue w ON w.reference_deletion_id=d.id
            WHERE d.requested_by=%s
        """)
    if has(user,"photos.view") and has(user,"photos.delete"):
        include("""
            SELECT 'cleanup',0::bigint,'cleanup:'||c.batch_id::text,
                   CASE WHEN c.state IN ('completed','failed') THEN c.updated_at END,
                   CASE WHEN c.state='pending' THEN 'queued' ELSE c.state END,
                   CASE WHEN c.progress->>'phase'='files' THEN
                     to_jsonb(100.0*(c.progress->>'done')::numeric/nullif((c.progress->>'total')::numeric,0))
                     ELSE NULL::jsonb END
            FROM cleanup_tasks c JOIN batches b ON b.id=c.batch_id WHERE b.owner_id=%s
              AND c.state IN ('pending','running','completed','failed')
        """)
    for kind,allowed in (
        ("results",has(user,"results.view") and has(user,"results.zip")),
        ("references",has(user,"references.view") and has(user,"references.export"))
    ):
        if allowed:
            # kind is a fixed internal literal, never a request parameter.
            include("""
                SELECT 'zip',0::bigint,'zip:'||id::text,
                       CASE WHEN state<>'running' THEN updated_at END,state,NULL::jsonb
                FROM favicon_archive_activity WHERE actor_id=%s
                  AND kind='"""+kind+"""' AND updated_at>=now()-interval '24 hours'
            """)
    with connect() as db:
        if not parts:
            data=db.execute("SELECT statement_timestamp() AS sampled_at,'[]'::jsonb AS tasks").fetchone()
        else:
            data=db.execute("""
                WITH own AS ("""+ " UNION ALL ".join(parts)+"""), classified AS (
                    SELECT *,CASE WHEN state IN ('failed','interrupted','completed_with_errors')
                                  THEN 'error' ELSE state END AS bucket
                    FROM own WHERE state IN ('running','stopping','queued','blocked')
                       OR finished_at>=now()-interval '24 hours'
                ), latest AS (
                    SELECT DISTINCT ON (kind,bucket) kind,seq,run_id,state,progress,finished_at
                    FROM classified ORDER BY kind,bucket,finished_at DESC NULLS LAST,seq DESC,run_id
                )
                SELECT statement_timestamp() AS sampled_at,
                       coalesce((SELECT jsonb_agg(to_jsonb(latest)) FROM latest),'[]'::jsonb) AS tasks
            """,tuple(args)).fetchone()
    return {"account_id":str(owner),"username":user["username"],"sampled_at":data["sampled_at"],"tasks":data["tasks"]}
