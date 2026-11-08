"""Authenticated read-only stage-3 layout and OCR diagnostics."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, HTTPException
from ...services import ad_recognition, ad_visual_groups, ad_text_subgroups
from app.ad_recognition import dino,ocr

router=APIRouter(prefix="/api/ad-recognition",tags=["ad-recognition"])

@router.get("/models")
def models():
    return {"dino":dino.status(),"ocr":ocr.status()}

@router.get("/runs/{run_id}/photos/{index}/screens/{screen_id}")
def result(run_id:str,index:int,screen_id:UUID):
    return ad_recognition.result(run_id,index,screen_id)


@router.get("/runs/{run_id}/visual-groups")
def visual_groups(run_id: str, limit: int = 50, offset: int = 0):
    _page(limit, offset)
    return ad_visual_groups.overview(run_id, limit, offset)

def _group_id(value: str):
    import re
    if not re.fullmatch(r"R[0-9]{4,8}", value):
        raise HTTPException(422, "Некорректный ID группы рекламы")
    return value

def _page(limit: int, offset: int):
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(422, "Некорректная страница результатов")

@router.get("/runs/{run_id}/visual-groups/{group_id}")
def visual_group(run_id: str, group_id: str):
    return ad_visual_groups.detail(run_id, _group_id(group_id))

@router.get("/runs/{run_id}/visual-groups/{group_id}/rankings")
def layout_rankings(run_id: str, group_id: str, limit: int = 50, offset: int = 0,
                    index: int | None = None, screen_id: UUID | None = None):
    _page(limit, offset)
    return ad_visual_groups.rankings(
        run_id, _group_id(group_id), limit, offset, index, screen_id)

@router.get("/runs/{run_id}/visual-groups/{group_id}/layouts/{layout_id}/members")
def layout_member_scores(run_id: str, group_id: str, layout_id: UUID,
                         limit: int = 50, offset: int = 0):
    _page(limit, offset)
    return ad_visual_groups.layout_members(
        run_id, _group_id(group_id), str(layout_id), limit, offset)

@router.get("/runs/{run_id}/text-subgroups")
def text_subgroups(run_id: str, limit: int = 50, offset: int = 0,
                   visual_group_id: str | None = None, layout_id: str | None = None):
    _page(limit, offset)
    return ad_text_subgroups.saved(run_id, limit, offset, visual_group_id, layout_id)


@router.get("/runs/{run_id}/text-subgroups/{subgroup_id}")
def text_subgroup(run_id: str, subgroup_id: str):
    return ad_text_subgroups.detail(run_id, subgroup_id)
