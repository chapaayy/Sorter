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
    if not row:
        return {"enabled":False}
    thresholds={"grouping_threshold":float(row["ad_grouping_threshold"]),
                "matching_threshold":float(row["ad_matching_threshold"])}
    if not row["ad_pipeline_enabled"]:
        return {"enabled":False,**thresholds}
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
    published=db.execute("""SELECT published_snapshot FROM ad_layouts
        WHERE active=true AND published_snapshot IS NOT NULL ORDER BY id""").fetchall()
    layouts=[r["published_snapshot"] for r in published
             if r["published_snapshot"]["dino_signature"]==dino.SIGNATURE
             and r["published_snapshot"]["ocr_signature"]==ocr_signature]
    if not layouts:
        raise RuntimeError("Распознавание включено, но нет активных макетов")
    revision=db.execute("SELECT revision FROM ad_layout_library_state WHERE id=1").fetchone()["revision"]
    return {"enabled":True,"status":"queued",
            **thresholds,
            "layout_library_revision":revision,
            "annotations":annotations,"layouts":layouts,
            "xfeat_signature":MODEL_ID,"dino_signature":dino.SIGNATURE,
            "ocr_version":ocr.VERSION,"ocr_signature":ocr_signature}
