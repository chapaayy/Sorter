"""Immutable per-run configuration captured inside the ONE FIFO claim transaction.

Versioned SAM objects have already been verified by reference_publication.snapshot.
No filesystem mutation is performed while holding a PostgreSQL claim lock.
"""
from __future__ import annotations
import uuid
from app.ad_recognition import dino,ocr
from app.screen_detection.xfeat_assets import MODEL_ID

def capture(db,pinned:list[dict])->dict:
    row=db.execute("""SELECT ad_pipeline_enabled,ad_grouping_threshold,
        ad_matching_threshold FROM processing_settings WHERE id=1""").fetchone()
    if not row or not row["ad_pipeline_enabled"]:
        return {"enabled":False}
    members={(m["sam"],str(m["id"])):m for m in pinned}
    refs=[uuid.UUID(str(m["id"])) for m in pinned]
    annotations=[]
    if refs:
        rows=db.execute("""SELECT a.id,a.screen_id,a.reference_id,a.corners,
            a.band_width_px,a.source_sha256,a.image_width,a.image_height,a.version,
            s.sam,s.name AS screen_name FROM reference_screen_annotations a
            JOIN reference_screens s ON s.id=a.screen_id
            WHERE a.reference_id=ANY(%s) ORDER BY s.sam,s.id,a.id""",(refs,)).fetchall()
        for row in rows:
            member=members.get((row["sam"],str(row["reference_id"])))
            if not member or member["hash"]!=row["source_sha256"]:continue
            annotations.append({
                "id":str(row["id"]),"screen_id":str(row["screen_id"]),
                "reference_id":str(row["reference_id"]),
                "screen_name":row["screen_name"],"sam":row["sam"],
                "corners":row["corners"],"band_width_px":row["band_width_px"],
                "source_sha256":row["source_sha256"],"image_width":row["image_width"],
                "image_height":row["image_height"],"version":row["version"],
                "target_path":member["path"],"pinned":True
            })
    ocr_signature=ocr.signature()
    rows=db.execute("""SELECT l.id,l.name,l.filename,l.checksum,l.target_path,
        l.byte_size,l.expected_text,l.ocr_corrected_text,l.version,l.active,
        l.preparation_state,c.cache_key,c.embedding_path,c.normalized_text,
        c.dino_signature,c.ocr_signature
        FROM ad_layouts l LEFT JOIN ad_layout_prepared_cache c ON c.cache_key=l.prepared_key
        WHERE l.active=true ORDER BY l.id""").fetchall()
    if any(r["preparation_state"]!="completed" or r["dino_signature"]!=dino.SIGNATURE
           or r["ocr_signature"]!=ocr_signature for r in rows):
        raise RuntimeError("Активные рекламные макеты требуют подготовки в общей очереди")
    layouts=[{"id":str(r["id"]),"name":r["name"],"filename":r["filename"],
              "checksum":r["checksum"],"target_path":r["target_path"],
              "byte_size":r["byte_size"],"expected_text":r["expected_text"],
              "ocr_corrected_text":r["ocr_corrected_text"],
              "ocr_text":r["ocr_corrected_text"] if r["ocr_corrected_text"] is not None
                  else r["expected_text"] or r["normalized_text"],
              "prepared_key":r["cache_key"],"embedding_path":r["embedding_path"],
              "version":r["version"],"active":r["active"]} for r in rows]
    if not layouts:
        raise RuntimeError("Распознавание включено, но нет активных макетов")
    revision=db.execute("SELECT revision FROM ad_layout_library_state WHERE id=1").fetchone()["revision"]
    return {"enabled":True,"status":"queued",
            "grouping_threshold":float(row["ad_grouping_threshold"]),
            "matching_threshold":float(row["ad_matching_threshold"]),
            "layout_library_revision":revision,
            "annotations":annotations,"layouts":layouts,
            "xfeat_signature":MODEL_ID,"dino_signature":dino.SIGNATURE,
            "ocr_version":ocr.VERSION,"ocr_signature":ocr.signature()}
