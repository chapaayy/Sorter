"""PostgreSQL operations for durable reference import sessions and FIFO enqueue."""
from __future__ import annotations

import uuid

def create_session(db, session_id):
    db.execute("""
        INSERT INTO reference_import_sessions(id)
        VALUES (%s) ON CONFLICT(id) DO NOTHING
    """,(session_id,))

def session(db, session_id, *, lock=False):
    return db.execute("""
        SELECT id,upload_state,preparation_state,expected_count,
               manifest_digest,manifest_registered_at,created_at,
               completed_at,error FROM reference_import_sessions
        WHERE id=%s
    """+(" FOR UPDATE" if lock else ""), (session_id,)).fetchone()

def file(db, session_id, upload_id, *, lock=False):
    return db.execute("""
        SELECT session_id,upload_id,sam,address,relative_path,filename,
               declared_size,checksum,received,stored_path,state,updated_at
        FROM reference_import_files WHERE session_id=%s AND upload_id=%s
    """+(" FOR UPDATE" if lock else ""), (session_id,upload_id)).fetchone()

def files(db, session_id):
    return db.execute("""
        SELECT session_id,upload_id,sam,address,relative_path,filename,
               declared_size,checksum,received,stored_path,state,updated_at
        FROM reference_import_files WHERE session_id=%s
        ORDER BY relative_path,upload_id
    """,(session_id,)).fetchall()

def register(db, session_id, manifest, digest):
    with db.cursor() as cursor:
        cursor.executemany("""
            INSERT INTO reference_import_files(
                session_id,upload_id,sam,address,relative_path,filename,
                declared_size,checksum)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,[(session_id,*item) for item in manifest])
    db.execute("""
        UPDATE reference_import_sessions SET
            expected_count=%s,manifest_digest=%s,manifest_registered_at=now()
        WHERE id=%s
    """,(len(manifest),digest,session_id))

def update_received(db, session_id, upload_id, amount):
    db.execute("""
        UPDATE reference_import_files SET received=%s,updated_at=now()
        WHERE session_id=%s AND upload_id=%s
    """,(amount,session_id,upload_id))

def finish_file(db, session_id, upload_id, digest, path):
    db.execute("""
        UPDATE reference_import_files SET state='finalized',
            received=declared_size,checksum=%s,stored_path=%s,updated_at=now()
        WHERE session_id=%s AND upload_id=%s
    """,(digest,str(path),session_id,upload_id))

def mark_duplicate(db, session_id, upload_id, digest):
    db.execute("""
        UPDATE reference_import_files SET state='duplicate',
            checksum=%s,received=0,stored_path=NULL,updated_at=now()
        WHERE session_id=%s AND upload_id=%s
    """,(digest,session_id,upload_id))

def matching_legacy(db, sam, digest, size):
    return db.execute("""
        SELECT target_path FROM uploads
        WHERE kind='reference' AND finalized AND sam=%s
          AND checksum=%s AND declared_size=%s AND target_path IS NOT NULL
        ORDER BY created_at,id
    """,(sam,digest,size)).fetchall()

def matching_staged(db, session_id, sam, digest, size, exclude_id):
    return db.execute("""
        SELECT stored_path FROM reference_import_files
        WHERE session_id=%s AND sam=%s AND checksum=%s
          AND declared_size=%s AND state='finalized'
          AND stored_path IS NOT NULL AND upload_id!=%s
        ORDER BY upload_id
    """,(session_id,sam,digest,size,exclude_id)).fetchall()

def preparation(db, session_id):
    return db.execute("""
        SELECT p.id,p.state,p.total_count,p.completed_count,
               p.failed_count,p.created_at,w.seq
        FROM reference_preparation_jobs p
        LEFT JOIN work_queue w ON w.reference_job_id=p.id
        WHERE p.session_id=%s
    """,(session_id,)).fetchone()

def enqueue_completed(db, session_id, count):
    """Atomic with state=complete: one prep job and one FIFO entry per session."""
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    job = preparation(db,session_id)
    if job:
        return job
    job_id=uuid.uuid4()
    db.execute("""
        INSERT INTO reference_preparation_jobs(id,session_id,total_count)
        VALUES (%s,%s,%s)
    """,(job_id,session_id,count))
    db.execute("""
        INSERT INTO work_queue(kind,reference_job_id,state)
        VALUES ('reference_preparation',%s,'queued')
    """,(job_id,))
    db.execute("""
        UPDATE reference_import_sessions SET upload_state='complete',
            preparation_state='queued',completed_at=now(),error=NULL
        WHERE id=%s
    """,(session_id,))
    return preparation(db,session_id)
