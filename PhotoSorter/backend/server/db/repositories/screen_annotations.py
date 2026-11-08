"""SQL-only persistence of screen identities and per-reference annotations."""
from __future__ import annotations
import json

def has_construction(db,sam):
    return bool(db.execute("SELECT 1 FROM reference_constructions WHERE sam=%s",(sam,)).fetchone())

def reference(db,sam,reference_id):
    return db.execute("""SELECT id,sam,checksum,target_path FROM uploads
        WHERE id=%s AND kind='reference' AND finalized AND sam=%s""",
        (reference_id,sam)).fetchone()

def list_screens(db,sam):
    return db.execute("""SELECT id,name FROM reference_screens
        WHERE sam=%s ORDER BY created_at,id""",(sam,)).fetchall()

def list_annotations(db,sam):
    return db.execute("""SELECT a.id,a.screen_id,a.reference_id,
        a.corners,a.band_width_px,a.source_sha256,a.image_width,a.image_height,
        a.version FROM reference_screen_annotations a
        JOIN reference_screens s ON s.id=a.screen_id WHERE s.sam=%s
        ORDER BY a.created_at,a.id""",(sam,)).fetchall()

def insert_screen(db,screen_id,sam,name):
    db.execute("INSERT INTO reference_screens(id,sam,name) VALUES (%s,%s,%s)",
               (screen_id,sam,name))

def has_screen(db,screen_id,sam):
    return bool(db.execute("SELECT 1 FROM reference_screens WHERE id=%s AND sam=%s",
                           (screen_id,sam)).fetchone())

def insert_annotation(db,annotation_id,screen_id,reference_id,corners,band,info):
    return db.execute("""INSERT INTO reference_screen_annotations
        (id,screen_id,reference_id,corners,band_width_px,source_sha256,image_width,image_height)
        VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
        ON CONFLICT(screen_id,reference_id) DO NOTHING
        RETURNING id,version""",
        (annotation_id,screen_id,reference_id,json.dumps(corners),
         band,info["source_sha256"],info["width"],info["height"])).fetchone()

def lock_annotation(db,annotation_id,sam):
    return db.execute("""SELECT a.*,s.sam FROM reference_screen_annotations a
        JOIN reference_screens s ON s.id=a.screen_id
        WHERE a.id=%s AND s.sam=%s FOR UPDATE OF a""",
        (annotation_id,sam)).fetchone()

def revise_annotation(db,annotation_id,corners,band):
    return db.execute("""UPDATE reference_screen_annotations
        SET corners=%s::jsonb,band_width_px=%s,version=version+1,updated_at=now()
        WHERE id=%s RETURNING id,version""",
        (json.dumps(corners),band,annotation_id)).fetchone()

def delete_annotation(db,annotation_id,sam):
    return db.execute("""DELETE FROM reference_screen_annotations a
        USING reference_screens s WHERE a.id=%s AND a.screen_id=s.id AND s.sam=%s
        RETURNING a.id""",(annotation_id,sam)).fetchone()

def delete_screen(db,screen_id,sam):
    return db.execute("DELETE FROM reference_screens WHERE id=%s AND sam=%s RETURNING id",
                      (screen_id,sam)).fetchone()

def detection_references(db,sam):
    """Current published annotations for precisely one MegaLoc construction."""
    return db.execute("""SELECT a.id,a.screen_id,a.reference_id,a.corners,
        a.band_width_px,a.source_sha256,a.image_width,a.image_height,a.version,
        s.name AS screen_name,u.target_path,u.checksum
      FROM reference_screen_annotations a
      JOIN reference_screens s ON s.id=a.screen_id
      JOIN uploads u ON u.id=a.reference_id
      WHERE s.sam=%s AND u.sam=%s AND u.kind='reference'
        AND u.finalized AND u.checksum=a.source_sha256
      ORDER BY s.created_at,a.created_at,a.id""",(sam,sam)).fetchall()
