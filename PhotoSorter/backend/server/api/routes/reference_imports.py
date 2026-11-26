"""Preflight and resumable staging for reference imports."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field

from ...services import reference_imports,reference_uploads,reference_import_sides,reference_portable_catalog
from ...storage.reference_objects import CHUNK_LIMIT
from ...security.access_policy import current_user

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
    portable:bool=False

class Manifest(BaseModel):
    files:list[ImportFile]=Field(min_length=1,max_length=20000)

class DuplicateConfirmation(BaseModel):
    sha256:str

class ComparisonFile(BaseModel):
    sam:str=Field(min_length=1,max_length=80)
    sha256:str=Field(pattern=r"^[0-9a-f]{64}$")
    size:int=Field(gt=0,le=60*1024*1024)
    side:str|None=Field(default=None,max_length=60)
    portable:bool=False

class Comparison(BaseModel):
    files:list[ComparisonFile]=Field(min_length=1,max_length=reference_imports.MAX_FILES)

class SideResolution(BaseModel):
    reference_id:uuid.UUID
    sam:str=Field(min_length=1,max_length=80)
    sha256:str=Field(pattern=r"^[0-9a-f]{64}$")
    size:int=Field(gt=0,le=60*1024*1024)
    existing_side:str|None=Field(max_length=60)
    requested_side:str=Field(min_length=1,max_length=60)
    portable:bool=False

class SideResolutions(BaseModel):
    changes:list[SideResolution]=Field(min_length=1,max_length=reference_imports.MAX_FILES)

class PortableConstruction(BaseModel):
    sam:str=Field(min_length=1,max_length=80)
    kind:str
    city_code:str|None=None
    number:str|None=None
    address:str|None=None

class PortableCatalog(BaseModel):
    constructions:list[PortableConstruction]=Field(min_length=1,max_length=5000)

@router.post("/portable-preview")
def portable_preview(data:PortableCatalog):
    return reference_portable_catalog.inspect(data.constructions)

@router.post("/portable-catalog")
def portable_catalog(data:PortableCatalog):
    return reference_portable_catalog.inspect(data.constructions,create=True)

@router.post("/resolve-sides")
def resolve_sides(data:SideResolutions):
    return reference_import_sides.resolve_conflicts(data.changes)

@router.post("/compare")
def compare(data:Comparison):
    return reference_imports.compare(data.files)

@router.post("",status_code=201)
def create(data:NewSession,request:Request=None):
    user=current_user(request)
    return reference_imports.create(data.client_session_id,requested_by=user["id"] if user else None,user=user)

@router.put("/{session_id}/manifest")
def register(session_id:uuid.UUID,data:Manifest,request:Request=None):
    return reference_imports.register_manifest(session_id,data.files,user=current_user(request))

@router.get("")
def list_sessions(limit:int=25,offset:int=0,request:Request=None):
    return reference_imports.list_sessions(limit,offset,user=current_user(request))

@router.get("/{session_id}")
def get_session(session_id:uuid.UUID,request:Request=None):
    return reference_imports.status(session_id,user=current_user(request))

@router.get("/{session_id}/files/{upload_id}")
def get_file(session_id:uuid.UUID,upload_id:uuid.UUID,request:Request=None):
    reference_imports.require_session_actor(session_id,current_user(request))
    return reference_imports.file_status(session_id,upload_id)

@router.patch("/{session_id}/files/{upload_id}")
async def chunk(session_id:uuid.UUID,upload_id:uuid.UUID,request:Request):
    await asyncio.to_thread(reference_imports.require_session_actor,session_id,current_user(request))
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
async def finish(session_id:uuid.UUID,upload_id:uuid.UUID,request:Request=None):
    await asyncio.to_thread(reference_imports.require_session_actor,session_id,current_user(request))
    return await asyncio.to_thread(reference_uploads.finish,session_id,upload_id)

@router.post("/{session_id}/files/{upload_id}/duplicate")
async def duplicate(session_id:uuid.UUID,upload_id:uuid.UUID,data:DuplicateConfirmation,request:Request=None):
    await asyncio.to_thread(reference_imports.require_session_actor,session_id,current_user(request))
    return await asyncio.to_thread(reference_uploads.confirm_duplicate,
                                   session_id,upload_id,data.sha256)

@router.post("/{session_id}/complete")
async def complete(session_id:uuid.UUID,request:Request=None):
    await asyncio.to_thread(reference_imports.require_session_actor,session_id,current_user(request))
    return await asyncio.to_thread(reference_imports.complete,session_id)
