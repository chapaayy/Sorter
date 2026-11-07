"""Read-only access to durable reference-import metadata in stage 1."""
from __future__ import annotations

def get_session(db,session_id):
    return db.execute("""
        SELECT id,upload_state,preparation_state,expected_count,
               manifest_digest,created_at,completed_at,error
        FROM reference_import_sessions WHERE id=%s
    """,(session_id,)).fetchone()

def get_preparation(db,session_id):
    return db.execute("""
        SELECT id,session_id,state,total_count,completed_count,
               failed_count,model_signature,error,created_at,started_at,finished_at
        FROM reference_preparation_jobs WHERE session_id=%s
    """,(session_id,)).fetchone()
