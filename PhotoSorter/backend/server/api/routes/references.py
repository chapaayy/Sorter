"""SAM gallery cursor endpoints: refs are independent of batch ownership."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from ...services import references as reference_service
from app.photos.labels import check_label
from ...database import connect
from ...db.repositories.pagination import page

router=APIRouter(prefix="/api/references",tags=["references"])

@router.get("/{sam}/photos")
def gallery(sam:str,cursor:str|None=None,limit:int=60):
    try:label=check_label(sam)
    except ValueError:raise HTTPException(422,"Неверный SAM")
    return _page(label,cursor,limit)

def _page(sam,cursor,limit):
    with connect() as db:
        return page(db,"u.kind='reference' AND u.finalized AND u.sam=%s",
                    (sam,),cursor=cursor,limit=limit)

class RenameSAM(BaseModel):
    new_sam:str=Field(min_length=8,max_length=80)

@router.get("/cache/status")
def cache_status():
    return reference_service.cache_status()

@router.patch("/sam/{sam}")
def rename_sam(sam:str,payload:RenameSAM):
    return reference_service.rename(sam,payload.new_sam)

@router.delete("/sam/{sam}")
def delete_sam(sam:str):
    return reference_service.delete(sam)
