"""Controls the next FIFO claim, and read-only per-run best-photo summary."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel,Field
from ...services import ad_pipeline_settings,ad_pipeline

router=APIRouter(prefix="/api/ad-pipeline",tags=["advertising-pipeline"])

class Settings(BaseModel):
    enabled:bool|None=None
    grouping_threshold:float|None=Field(default=None,ge=0,le=1,allow_inf_nan=False)
    matching_threshold:float|None=Field(default=None,ge=0,le=1,allow_inf_nan=False)

@router.get("/settings")
def settings():
    return ad_pipeline_settings.read()

@router.patch("/settings")
def update(settings:Settings):
    return ad_pipeline_settings.update(settings.enabled,settings.grouping_threshold,settings.matching_threshold)

@router.get("/runs/{run_id}/best")
def best(run_id:str):
    return ad_pipeline.summary(run_id)
