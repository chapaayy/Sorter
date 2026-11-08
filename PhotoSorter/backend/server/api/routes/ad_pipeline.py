"""Controls the next FIFO claim, and read-only per-run best-photo summary."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from ...services import ad_pipeline_settings,ad_pipeline

router=APIRouter(prefix="/api/ad-pipeline",tags=["advertising-pipeline"])

class Settings(BaseModel):
    enabled:bool

@router.get("/settings")
def settings():
    return ad_pipeline_settings.read()

@router.patch("/settings")
def update(settings:Settings):
    return ad_pipeline_settings.update(settings.enabled)

@router.get("/runs/{run_id}/best")
def best(run_id:str):
    return ad_pipeline.summary(run_id)
