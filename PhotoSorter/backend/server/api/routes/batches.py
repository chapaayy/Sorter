"""Batch list/detail/update, safe deletion and explicit archive confirmation."""
from __future__ import annotations
import uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from ...services import batches,cleanup,retention,upload_manifest,auto_processing
from ...database import connect
from ...db.repositories.pagination import page

router=APIRouter(prefix="/api/batches",tags=["batches"])

class NewBatch(BaseModel):
    display_name:str|None=Field(default=None,max_length=120)
class RenameBatch(BaseModel):
    display_name:str=Field(min_length=1,max_length=120)
class ConfirmDownload(BaseModel):
    run_id:str

class ManifestFile(BaseModel):
    upload_id:uuid.UUID
    relative_path:str=Field(min_length=1,max_length=1024)
    filename:str=Field(min_length=1,max_length=200)
    size:int=Field(gt=0,le=60*1024*1024)

class BatchManifest(BaseModel):
    files:list[ManifestFile]=Field(min_length=1,max_length=20000)
    auto_process:bool=False
    grouping_threshold:float=Field(default=.50,ge=.50,le=.99,allow_inf_nan=False)

@router.post("")
def create(payload:NewBatch|None=None):
    return batches.create(payload.display_name if payload else None)

@router.get("")
def list_batches(limit:int=100,offset:int=0):
    if not 1<=limit<=200 or offset<0:raise HTTPException(422,"Неверная пагинация")
    return batches.list_all(limit,offset)

@router.put("/{batch_id}/upload-manifest")
def register_manifest(batch_id:str,payload:BatchManifest):
    return upload_manifest.register(batch_id,payload.files,
        auto_process=payload.auto_process,grouping_threshold=payload.grouping_threshold)

@router.get("/{batch_id}/upload-manifest")
def manifest(batch_id:str):
    return upload_manifest.status(batch_id)

@router.post("/{batch_id}/auto-processing/cancel")
def cancel_automatic(batch_id:str):
    return auto_processing.cancel(batch_id)

@router.get("/{batch_id}/pending")
def pending(batch_id:str):
    return batches.pending_uploads(batch_id)

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

@router.get("/{batch_id}/gallery")
def gallery(batch_id:str,cursor:str|None=None,limit:int=60):
    batch_id=batches.uid(batch_id)
    with connect() as db:
        if not db.execute("SELECT 1 FROM batches WHERE id=%s",(batch_id,)).fetchone():
            raise HTTPException(404,"Партия не найдена")
        return page(db,"u.kind='fo' AND u.finalized AND u.batch_id=%s",
                    (batch_id,),cursor=cursor,limit=limit)

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
