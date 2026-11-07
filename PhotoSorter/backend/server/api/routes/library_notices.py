"""Server-authoritative library version, upload notices and event history."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel,Field
from ...services import library_notices

router=APIRouter(prefix="/api/reference-library",tags=["reference-library"])

class Acknowledgement(BaseModel):
    version_id:int=Field(gt=0)

@router.get("/status")
def status():
    return library_notices.status()

@router.get("/events")
def events(limit:int=30,after_version:int|None=None):
    return library_notices.history(limit,after_version)

@router.post("/notices/ack")
def acknowledge(payload:Acknowledgement):
    return library_notices.acknowledge(payload.version_id)
