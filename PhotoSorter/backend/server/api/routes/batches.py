"""Batch list/detail/update, safe deletion and explicit archive confirmation."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from ...services import batches,cleanup,retention

router=APIRouter(prefix="/api/batches",tags=["batches"])

class NewBatch(BaseModel):
    display_name:str|None=Field(default=None,max_length=120)
class RenameBatch(BaseModel):
    display_name:str=Field(min_length=1,max_length=120)
class ConfirmDownload(BaseModel):
    run_id:str

@router.post("")
def create(payload:NewBatch|None=None):
    return batches.create(payload.display_name if payload else None)

@router.get("")
def list_batches(limit:int=100,offset:int=0):
    if not 1<=limit<=200 or offset<0:raise HTTPException(422,"Неверная пагинация")
    return batches.list_all(limit,offset)

@router.get("/{batch_id}")
def detail(batch_id:str):
    return batches.get(batch_id)

@router.patch("/{batch_id}")
def rename(batch_id:str,payload:RenameBatch):
    return batches.rename(batch_id,payload.display_name)

@router.get("/{batch_id}/photos")
def photos(batch_id:str,limit:int=100,offset:int=0):
    if not 1<=limit<=200 or offset<0:raise HTTPException(422,"Неверная пагинация")
    return batches.photos(batch_id,limit,offset)

@router.delete("/{batch_id}/photos/{photo_id}")
def delete_photo(batch_id:str,photo_id:str):
    return batches.remove_unprocessed_photo(batch_id,photo_id)

@router.delete("/{batch_id}",status_code=202)
def delete(batch_id:str):
    return cleanup.request(batch_id)

@router.get("/{batch_id}/deletion")
def deletion(batch_id:str):
    return cleanup.get_status(batch_id)

@router.post("/{batch_id}/downloads/confirm")
def confirm(batch_id:str,payload:ConfirmDownload):
    return retention.confirm(batch_id,payload.run_id)

@router.post("/{batch_id}/retention/extend")
def extend(batch_id:str):
    return retention.extend(batch_id)

@router.get("/{batch_id}/retention")
def retention_status(batch_id:str):
    return retention.status(batch_id)
