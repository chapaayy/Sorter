"""Opt-in integrated advertising analysis. Applies only when FIFO claims a FO run."""
from __future__ import annotations
from fastapi import HTTPException
from ..database import connect

def read():
    with connect() as db:
        row=db.execute("SELECT ad_pipeline_enabled FROM processing_settings WHERE id=1").fetchone()
    return {"enabled":bool(row and row["ad_pipeline_enabled"]),"applies":"next_fifo_claim",
            "default_safe":True}

def update(enabled:bool):
    if enabled:
        # Only the API container downloads/install models; Worker must run offline.
        from app.screen_detection import xfeat_assets
        from app.ad_recognition import dino,ocr
        missing=[name for name,ready in (
            ("XFeat",xfeat_assets.status()["available"]),
            ("DINOv2",dino.status()["available"]),
            ("PP-OCRv5",ocr.status()["available"])) if not ready]
        if missing:
            raise HTTPException(409,"Не установлены проверенные модели: "+", ".join(missing))
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        if enabled:
            n=db.execute("SELECT count(*) AS n FROM ad_layouts WHERE active=true").fetchone()["n"]
            if not n:raise HTTPException(409,"Сначала добавьте активные рекламные макеты")
        db.execute("UPDATE processing_settings SET ad_pipeline_enabled=%s,updated_at=now() WHERE id=1",(enabled,))
    return read()
