"""Preflight and resumable staging for reference imports."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field

from ...services import reference_imports,reference_uploads
from ...storage.reference_objects import CHUNK_LIMIT

router=APIRouter(prefix="/api/reference-imports",tags=["reference-imports"])

class NewSession(BaseModel):
    client_session_id:uuid.UUID

class ImportFile(BaseModel):
    upload_id:uuid.UUID
    sam:str=Field(min_length=1,max_length=80)
    address:str|None=Field(default=None,max_length=120)
    relative_path:str=Field(min_length=1,max_length=1024)
    filename:str=Field(min_length=1,max_length=200)
    size:int=Field(gt=0,le=60*1024*1024)
    sha256:str|None=None
    side:str|None=Field(default=None,max_length=60)

class Manifest(BaseModel):
    files:list[ImportFile]=Field(min_length=1,max_length=20000)

class DuplicateConfirmation(BaseModel):
    sha256:str

class ComparisonFile(BaseModel):
    sam:str=Field(min_length=1,max_length=80)
    sha256:str=Field(pattern=r"^[0-9a-f]{64}$")
    size:int=Field(gt=0,le=60*1024*1024)
    side:str|None=Field(default=None,max_length=60)

class Comparison(BaseModel):
    files:list[ComparisonFile]=Field(min_length=1,max_length=reference_imports.MAX_FILES)

@router.post("/compare")
def compare(data:Comparison):
    return reference_imports.compare(data.files)

@router.post("",status_code=201)
def create(data:NewSession):
    return reference_imports.create(data.client_session_id)

@router.put("/{session_id}/manifest")
def register(session_id:uuid.UUID,data:Manifest):
    return reference_imports.register_manifest(session_id,data.files)

@router.get("")
def list_sessions(limit:int=25,offset:int=0):
    return reference_imports.list_sessions(limit,offset)

@router.get("/{session_id}")
def get_session(session_id:uuid.UUID):
    return reference_imports.status(session_id)

@router.get("/{session_id}/files/{upload_id}")
def get_file(session_id:uuid.UUID,upload_id:uuid.UUID):
    return reference_imports.file_status(session_id,upload_id)

@router.patch("/{session_id}/files/{upload_id}")
async def chunk(session_id:uuid.UUID,upload_id:uuid.UUID,request:Request):
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
    return await asyncio.to_thread(reference_uploads.finish,session_id,upload_id)

@router.post("/{session_id}/files/{upload_id}/duplicate")
async def duplicate(session_id:uuid.UUID,upload_id:uuid.UUID,data:DuplicateConfirmation):
    return await asyncio.to_thread(reference_uploads.confirm_duplicate,
                                   session_id,upload_id,data.sha256)

@router.post("/{session_id}/complete")
async def complete(session_id:uuid.UUID):
    return await asyncio.to_thread(reference_imports.complete,session_id)
