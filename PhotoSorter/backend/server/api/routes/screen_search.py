"""Authenticated read-only stage-2 XFeat diagnostics (analysis via existing worker container CLI)."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter
from fastapi.responses import FileResponse
from ...services import screen_search

router=APIRouter(prefix="/api/screen-search",tags=["screen-search"])

@router.get("/model")
def model():
    from app.screen_detection.xfeat_assets import status
    return status()

@router.get("/runs/{run_id}/photos/{index}")
def photo(run_id:str,index:int):
    return screen_search.saved(run_id,index)

@router.get("/runs/{run_id}/photos/{index}/screens/{screen_id}/crop")
def crop(run_id:str,index:int,screen_id:UUID):
    return FileResponse(screen_search.crop(run_id,index,screen_id),
                        media_type="image/png",headers={"Cache-Control":"no-store"})
