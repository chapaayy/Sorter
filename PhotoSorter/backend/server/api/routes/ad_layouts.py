"""Authenticated layout library CRUD. Images are never served from arbitrary URLs."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter,UploadFile,File,Form
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from ...services import ad_layouts as service

router=APIRouter(prefix="/api/ad-layouts",tags=["advertising-layouts"])

class EditLayout(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    expected_text:str=Field(default="",max_length=1000)
    active:bool
    version:int=Field(ge=1)

@router.get("")
def all_layouts():
    return service.list_layouts()

@router.post("",status_code=201)
async def upload(file:UploadFile=File(...),name:str=Form(...),expected_text:str=Form("")):
    from fastapi import HTTPException
    raw=await file.read(service.MAX_BYTES+1)
    if len(raw)>service.MAX_BYTES:raise HTTPException(413,"Размер файла больше 20 МиБ")
    return service.create(raw,file.filename or "layout",name,expected_text)

@router.patch("/{layout_id}")
def edit(layout_id:UUID,payload:EditLayout):
    return service.update(layout_id,payload.version,payload.name,payload.expected_text,payload.active)

@router.delete("/{layout_id}")
def remove(layout_id:UUID):
    return service.delete(layout_id)

@router.get("/{layout_id}/image")
def picture(layout_id:UUID):
    return FileResponse(service.image(layout_id),headers={"Cache-Control":"no-store"})
