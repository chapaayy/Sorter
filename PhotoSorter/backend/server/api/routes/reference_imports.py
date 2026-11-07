"""Stage-2 staged imports; API is gated off until immutable FIFO worker is ready."""
from __future__ import annotations

import asyncio
import os
import uuid

from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field

from ...services import reference_imports,reference_uploads
from ...storage.reference_objects import CHUNK_LIMIT

router=APIRouter(prefix="/api/reference-imports",tags=["reference-imports"])

def _enabled():
    # Prevent accidentally populating a queue that stage-1 worker cannot claim.
    # Stage 3 activation is a separate, tested deployment decision.
    if (os.environ.get("REFERENCE_IMPORT_STAGING_ENABLED")!="1" or
        os.environ.get("PHOTOSORTER_UNIFIED_QUEUE")!="1"):
        raise HTTPException(503,"Новая загрузка образцов пока не включена")

class NewSession(BaseModel):
    client_session_id:uuid.UUID

class ImportFile(BaseModel):
    upload_id:uuid.UUID
    sam:str=Field(min_length=5,max_length=80)
    address:str|None=Field(default=None,max_length=120)
    relative_path:str=Field(min_length=1,max_length=1024)
    filename:str=Field(min_length=1,max_length=200)
    size:int=Field(gt=0,le=60*1024*1024)
    sha256:str|None=None

class Manifest(BaseModel):
    files:list[ImportFile]=Field(min_length=1,max_length=20000)

class DuplicateConfirmation(BaseModel):
    sha256:str

@router.post("",status_code=201)
def create(data:NewSession):
    _enabled()
    return reference_imports.create(data.client_session_id)

@router.put("/{session_id}/manifest")
def register(session_id:uuid.UUID,data:Manifest):
    _enabled()
    return reference_imports.register_manifest(session_id,data.files)

@router.get("/{session_id}")
def get_session(session_id:uuid.UUID):
    _enabled()
    return reference_imports.status(session_id)

@router.get("/{session_id}/files/{upload_id}")
def get_file(session_id:uuid.UUID,upload_id:uuid.UUID):
    _enabled()
    return reference_imports.file_status(session_id,upload_id)

@router.patch("/{session_id}/files/{upload_id}")
async def chunk(session_id:uuid.UUID,upload_id:uuid.UUID,request:Request):
    _enabled()
    try:
        offset=int(request.headers.get("upload-offset","-1"))
    except ValueError as exc:
        raise HTTPException(400,"Неверное смещение") from exc
    if offset<0:
        raise HTTPException(400,"Неверное смещение")
    pieces=[]
    length=0
    async for data in request.stream():
        length+=len(data)
        if length>CHUNK_LIMIT:
            raise HTTPException(413,"Превышен размер блока (16 МиБ)")
        if data:
            pieces.append(data)
    if not length:
        raise HTTPException(400,"Пустой блок")
    return await asyncio.to_thread(reference_uploads.append,session_id,upload_id,
                                   offset,b"".join(pieces))

@router.post("/{session_id}/files/{upload_id}/finish")
async def finish(session_id:uuid.UUID,upload_id:uuid.UUID):
    _enabled()
    return await asyncio.to_thread(reference_uploads.finish,session_id,upload_id)

@router.post("/{session_id}/files/{upload_id}/duplicate")
async def duplicate(session_id:uuid.UUID,upload_id:uuid.UUID,data:DuplicateConfirmation):
    _enabled()
    return await asyncio.to_thread(reference_uploads.confirm_duplicate,
                                   session_id,upload_id,data.sha256)

@router.post("/{session_id}/complete")
async def complete(session_id:uuid.UUID):
    _enabled()
    return await asyncio.to_thread(reference_imports.complete,session_id)
