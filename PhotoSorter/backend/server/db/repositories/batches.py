"""PostgreSQL persistence of batch and photo metadata (no filesystem side effects)."""
from __future__ import annotations

def get(db, batch_id, *, for_update=False):
    suffix=" FOR UPDATE" if for_update else ""
    return db.execute("SELECT * FROM batches WHERE id=%s"+suffix,(batch_id,)).fetchone()

def insert(db,batch_id,name):
    db.execute("INSERT INTO batches(id,display_name) VALUES (%s,%s)",(batch_id,name))

def count_photos_and_runs(db,batch_id):
    counter=db.execute("""SELECT count(*) FILTER (WHERE finalized) AS photos,
       coalesce(sum(declared_size) FILTER (WHERE finalized),0) AS size_bytes,
       count(*) FILTER (WHERE NOT finalized) AS pending
       FROM uploads WHERE kind='fo' AND batch_id=%s""",(batch_id,)).fetchone()
    runs=db.execute("SELECT count(*) AS runs FROM jobs WHERE batch_id=%s",(batch_id,)).fetchone()
    return {**counter,**runs}

def list_rows(db,limit,offset):
    rows=db.execute("SELECT * FROM batches ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (limit,offset)).fetchall()
    total=db.execute("SELECT count(*) AS c FROM batches").fetchone()["c"]
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
    return db.execute("""SELECT id,target_path FROM uploads
        WHERE id=%s AND batch_id=%s AND kind='fo' FOR UPDATE""",
        (photo_id,batch_id)).fetchone()

def path_is_shared(db,path,photo_id):
    return bool(db.execute("SELECT 1 FROM uploads WHERE target_path=%s AND id<>%s LIMIT 1",
                           (path,photo_id)).fetchone())

def delete_photo_row(db,photo_id):
    db.execute("DELETE FROM uploads WHERE id=%s",(photo_id,))
