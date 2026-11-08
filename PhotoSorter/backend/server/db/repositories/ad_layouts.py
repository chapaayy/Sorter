"""SQL-only immutable layout registry; no image parsing or filesystem operations."""
from __future__ import annotations

def all_rows(db,active_only=False):
    return db.execute("""SELECT id,name,filename,checksum,target_path,byte_size,
        expected_text,active,version,created_at,updated_at
        FROM ad_layouts WHERE (%s=false OR active=true)
        ORDER BY created_at,id""",(active_only,)).fetchall()

def by_id(db,uid,lock=False):
    sql="""SELECT id,name,filename,checksum,target_path,byte_size,expected_text,
        active,version,created_at,updated_at FROM ad_layouts WHERE id=%s"""
    if lock:sql+=" FOR UPDATE"
    return db.execute(sql,(uid,)).fetchone()

def insert(db,uid,name,filename,checksum,target_path,byte_size,expected_text):
    return db.execute("""INSERT INTO ad_layouts
      (id,name,filename,checksum,target_path,byte_size,expected_text)
      VALUES (%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (checksum) DO NOTHING RETURNING id""",
      (uid,name,filename,checksum,str(target_path),byte_size,expected_text)).fetchone()

def edit(db,uid,version,name,expected_text,active):
    return db.execute("""UPDATE ad_layouts SET name=%s,expected_text=%s,
        active=%s,version=version+1,updated_at=now()
      WHERE id=%s AND version=%s RETURNING id""",
      (name,expected_text,active,uid,version)).fetchone()

def remove(db,uid):
    return db.execute("DELETE FROM ad_layouts WHERE id=%s RETURNING target_path",
                      (uid,)).fetchone()
