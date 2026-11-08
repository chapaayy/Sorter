"""SQL-only immutable layout registry; no image parsing or filesystem operations."""
from __future__ import annotations

def all_rows(db,active_only=False):
    return db.execute("""SELECT l.id,l.name,l.filename,l.checksum,l.target_path,l.byte_size,
        l.expected_text,l.active,l.version,l.created_at,l.updated_at,
        l.ocr_corrected_text,l.preparation_state,l.preparation_stage,
        l.preparation_progress,l.preparation_error,l.prepared_key,l.prepared_at,l.published_snapshot,
        c.ocr_lines,c.normalized_text,c.embedding_path,c.dino_signature,c.ocr_signature
        FROM ad_layouts l LEFT JOIN ad_layout_prepared_cache c ON c.cache_key=l.prepared_key WHERE (%s=false OR l.active=true)
        ORDER BY l.created_at,l.id""",(active_only,)).fetchall()

def by_id(db,uid,lock=False):
    sql="""SELECT l.id,l.name,l.filename,l.checksum,l.target_path,l.byte_size,l.expected_text,
        l.active,l.version,l.created_at,l.updated_at,l.ocr_corrected_text,
        l.preparation_state,l.preparation_stage,l.preparation_progress,
        l.preparation_error,l.prepared_key,l.prepared_at,
        c.ocr_lines,c.normalized_text,c.dino_signature,c.ocr_signature
        FROM ad_layouts l LEFT JOIN ad_layout_prepared_cache c ON c.cache_key=l.prepared_key
        WHERE l.id=%s"""
    if lock:sql+=" FOR UPDATE OF l"
    return db.execute(sql,(uid,)).fetchone()

def insert(db,uid,name,filename,checksum,target_path,byte_size,expected_text):
    return db.execute("""INSERT INTO ad_layouts
      (id,name,filename,checksum,target_path,byte_size,expected_text)
      VALUES (%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (checksum) DO NOTHING RETURNING id""",
      (uid,name,filename,checksum,str(target_path),byte_size,expected_text)).fetchone()

def edit(db,uid,version,name,expected_text,active):
    return db.execute("""UPDATE ad_layouts SET name=%s,expected_text=%s,
        active=%s,ocr_corrected_text=NULLIF(%s,''),version=version+1,updated_at=now()
      WHERE id=%s AND version=%s RETURNING id""",
      (name,expected_text,active,expected_text,uid,version)).fetchone()

def remove(db,uid):
    return db.execute("DELETE FROM ad_layouts WHERE id=%s RETURNING target_path",
                      (uid,)).fetchone()
