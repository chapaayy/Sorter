"""PostgreSQL persistence of batch and photo metadata (no filesystem side effects)."""
from __future__ import annotations

_NAME_ALLOCATION_LOCK=723409142

def get(db, batch_id, *, for_update=False, include_deletion=False):
    if include_deletion:
        return db.execute("""SELECT b.*,c.progress AS deletion_progress FROM batches b
            LEFT JOIN cleanup_tasks c ON c.batch_id=b.id WHERE b.id=%s""",(batch_id,)).fetchone()
    suffix=" FOR UPDATE" if for_update else ""
    return db.execute("SELECT * FROM batches WHERE id=%s"+suffix,(batch_id,)).fetchone()

def lock_names(db):
    db.execute("SELECT pg_advisory_xact_lock(%s)",(_NAME_ALLOCATION_LOCK,))

def by_creation_request(db,request_id):
    return db.execute("""SELECT id,display_name FROM batches
        WHERE creation_request_id=%s""",(request_id,)).fetchone()

def name_taken(db,name,exclude_id=None):
    return db.execute("""SELECT 1 FROM batches
        WHERE delete_state <> 'deleted' AND lower(display_name)=lower(%s)
          AND id IS DISTINCT FROM %s LIMIT 1""",(name,exclude_id)).fetchone() is not None

def insert(db,batch_id,name,request_id=None):
    db.execute("INSERT INTO batches(id,display_name,creation_request_id) VALUES (%s,%s,%s)",
               (batch_id,name,request_id))

def count_photos_and_runs(db,batch_id):
    counter=db.execute("""SELECT count(*) FILTER (WHERE finalized AND ((media_action IS NULL AND original_media_type IS NULL)
         OR ((media_action='keep' OR media_output_path IS NOT NULL) AND
             coalesce(original_media_type,'') NOT LIKE 'video/%%'))) AS photos,
       count(*) FILTER (WHERE finalized AND original_media_type LIKE 'video/%%'
         AND (media_action='keep' OR media_output_path IS NOT NULL)) AS videos,
       count(*) FILTER (WHERE finalized AND ((media_action IS NULL AND original_media_type IS NOT NULL) OR media_error IS NOT NULL)) AS media_files,
       coalesce(sum(declared_size) FILTER (WHERE finalized),0) AS size_bytes,
       count(*) FILTER (WHERE NOT finalized) AS pending
       FROM uploads WHERE kind='fo' AND batch_id=%s""",(batch_id,)).fetchone()
    runs=db.execute("SELECT count(*) AS runs FROM jobs WHERE batch_id=%s",(batch_id,)).fetchone()
    return {**counter,**runs}

def list_rows(db,limit,offset):
    rows=db.execute("""SELECT b.*,c.progress AS deletion_progress FROM batches b
        LEFT JOIN cleanup_tasks c ON c.batch_id=b.id WHERE b.delete_state <> 'deleted'
        ORDER BY b.created_at DESC,b.id DESC LIMIT %s OFFSET %s""",
        (limit,offset)).fetchall()
    total=db.execute("""SELECT count(*) AS c FROM batches
        WHERE delete_state <> 'deleted'""").fetchone()["c"]
    return rows,total

def set_name(db,batch_id,name):
    db.execute("UPDATE batches SET display_name=%s WHERE id=%s",(name,batch_id))

def list_photos(db,batch_id,limit,offset):
    rows=db.execute("""SELECT id,filename,declared_size,checksum,finalized,created_at
        FROM uploads WHERE kind='fo' AND batch_id=%s ORDER BY created_at,id
        LIMIT %s OFFSET %s""",(batch_id,limit,offset)).fetchall()
    total=db.execute("SELECT count(*) AS c FROM uploads WHERE kind='fo' AND batch_id=%s",
                     (batch_id,)).fetchone()["c"]
    return rows,total

def has_runs(db,batch_id):
    return bool(db.execute("SELECT 1 FROM jobs WHERE batch_id=%s LIMIT 1",(batch_id,)).fetchone())

def has_operations(db,batch_id):
    return bool(db.execute("SELECT 1 FROM batch_operations WHERE batch_id=%s LIMIT 1",
                           (batch_id,)).fetchone())

def photo_row(db,batch_id,photo_id):
    return db.execute("""SELECT id,target_path,media_output_path FROM uploads
        WHERE id=%s AND batch_id=%s AND kind='fo' FOR UPDATE""",
        (photo_id,batch_id)).fetchone()

def path_is_shared(db,path,photo_id):
    return bool(db.execute("SELECT 1 FROM uploads WHERE target_path=%s AND id<>%s LIMIT 1",
                           (path,photo_id)).fetchone())

def delete_photo_row(db,photo_id):
    db.execute("DELETE FROM uploads WHERE id=%s",(photo_id,))

def refresh_upload_state(db,batch_id):
    """Derived from the actual uploads and jobs, never a UI-only flag."""
    db.execute("""UPDATE batches SET upload_state=CASE
       WHEN EXISTS (SELECT 1 FROM jobs WHERE batch_id=%s) THEN 'sealed'
       WHEN EXISTS (SELECT 1 FROM batches WHERE id=%s AND upload_manifest_state IS NOT NULL)
            THEN CASE WHEN EXISTS (SELECT 1 FROM batches WHERE id=%s
                  AND upload_manifest_state='complete') THEN 'ready' ELSE 'open' END
       WHEN EXISTS (SELECT 1 FROM uploads WHERE kind='fo' AND batch_id=%s
            AND NOT finalized) THEN 'open'
       WHEN EXISTS (SELECT 1 FROM uploads WHERE kind='fo' AND batch_id=%s
            AND finalized) THEN 'ready'
       ELSE 'open' END WHERE id=%s""",(batch_id,batch_id,batch_id,batch_id,batch_id,batch_id))
