"""Read published reference metadata without consulting live reference directories."""
from __future__ import annotations

def current(db):
    return db.execute("""
        SELECT s.baseline_state,s.baseline_error,v.id,v.version_number,
               v.manifest_digest,v.model_signature,v.published_at
        FROM reference_library_state s
        LEFT JOIN reference_library_versions v ON v.id=s.current_version_id
        WHERE s.id=1
    """).fetchone()

def members(db,version_id):
    return db.execute("""
        SELECT reference_id,sam,filename,source_hash,target_path,declared_size
        FROM reference_version_members WHERE version_id=%s ORDER BY sam,reference_id
    """,(version_id,)).fetchall()
