"""Authenticated read-only stage-3 layout and OCR diagnostics."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter
from ...services import ad_recognition
from app.ad_recognition import dino,ocr

router=APIRouter(prefix="/api/ad-recognition",tags=["ad-recognition"])

@router.get("/models")
def models():
    return {"dino":dino.status(),"ocr":ocr.status()}

@router.get("/runs/{run_id}/photos/{index}/screens/{screen_id}")
def result(run_id:str,index:int,screen_id:UUID):
    return ad_recognition.result(run_id,index,screen_id)
