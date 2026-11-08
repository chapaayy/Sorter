"""Authenticated read-only Stage 4 views over saved advertising-run artifacts."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse
from ...services import ad_result_views

router = APIRouter(prefix="/api/ad-results/runs", tags=["advertising-results"])


@router.get("/{run_id}/screens")
def screens(run_id: str, cursor: str | None = None, limit: int = 24):
    return ad_result_views.screen_page(run_id, cursor, limit)


@router.get("/{run_id}/layouts")
def layouts(run_id: str, limit: int = 50, offset: int = 0):
    return ad_result_views.layout_list(run_id, limit, offset)


@router.get("/{run_id}/layouts/{layout_id}/image")
def layout_image(run_id: str, layout_id: str):
    return FileResponse(ad_result_views.layout_image(run_id, layout_id),
                        headers={"Cache-Control": "no-store"})


@router.get("/{run_id}/layouts/{layout_id}/photos")
def layout_photos(run_id: str, layout_id: str, subgroup_id: str | None = None,
                  best_only: bool = False, limit: int = 32, offset: int = 0):
    return ad_result_views.layout_photos(
        run_id, layout_id, subgroup_id=subgroup_id, best_only=best_only,
        limit=limit, offset=offset)


@router.get("/{run_id}/ocr")
def ocr(run_id: str, cursor: str | None = None, limit: int = 24):
    return ad_result_views.ocr_page(run_id, cursor, limit)
