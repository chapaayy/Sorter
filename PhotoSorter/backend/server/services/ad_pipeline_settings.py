"""Persistent, claim-time-frozen DINOv2 thresholds and opt-in."""
from __future__ import annotations

from fastapi import HTTPException
from app.ad_recognition import dino,ocr
from app.screen_detection import xfeat_assets
from ..database import connect

def _values(row):
    return {"enabled":bool(row["ad_pipeline_enabled"]),
            "grouping_threshold":float(row["ad_grouping_threshold"]),
            "matching_threshold":float(row["ad_matching_threshold"]),
            "applies":"next_fifo_claim","default_safe":True}

def read():
    with connect() as db:
        row=db.execute("""SELECT ad_pipeline_enabled,ad_grouping_threshold,
            ad_matching_threshold FROM processing_settings WHERE id=1""").fetchone()
    return _values(row)

def _threshold(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not (
            0<=value<=1 and abs(value-round(value,2))<1e-8):
        raise HTTPException(422,"Порог должен быть от 0.00 до 1.00 с шагом 0.01")
    return round(value,2)

def update(enabled=None,grouping_threshold=None,matching_threshold=None):
    group=_threshold(grouping_threshold) if grouping_threshold is not None else None
    match=_threshold(matching_threshold) if matching_threshold is not None else None
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        row=db.execute("""SELECT ad_pipeline_enabled,ad_grouping_threshold,
            ad_matching_threshold FROM processing_settings WHERE id=1 FOR UPDATE""").fetchone()
        active=row["ad_pipeline_enabled"] if enabled is None else enabled
        if enabled is True and not row["ad_pipeline_enabled"]:
            missing=[name for name,ready in (
                ("XFeat",xfeat_assets.status()["available"]),
                ("DINOv2",dino.status()["available"]),
                ("PP-OCRv5",ocr.status()["available"])) if not ready]
            if missing:
                raise HTTPException(409,"Не установлены проверенные модели: "+", ".join(missing))
            signature=ocr.signature()
            counts=db.execute("""SELECT count(*) FILTER
                (WHERE published_snapshot->>'dino_signature'=%s
                    AND published_snapshot->>'ocr_signature'=%s) AS ready
                FROM ad_layouts WHERE active=true""",
                (dino.SIGNATURE,signature)).fetchone()
            if not counts["ready"]:
                raise HTTPException(409,"Дождитесь подготовки хотя бы одного активного макета рекламы")
        db.execute("""UPDATE processing_settings SET
            ad_pipeline_enabled=%s,
            ad_grouping_threshold=%s,ad_matching_threshold=%s,updated_at=now()
            WHERE id=1""",(active,group if group is not None else row["ad_grouping_threshold"],
                             match if match is not None else row["ad_matching_threshold"]))
        updated=db.execute("""SELECT ad_pipeline_enabled,ad_grouping_threshold,
            ad_matching_threshold FROM processing_settings WHERE id=1""").fetchone()
    return _values(updated)
