"""Authenticated APIs for editable reference screen geometry."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter,Field
from pydantic import BaseModel
from ...services import screen_annotations as service

router=APIRouter(prefix="/api/references",tags=["screen-annotations"])

class Point(BaseModel):
    x:float
    y:float

class Geometry(BaseModel):
    corners:list[Point]=Field(min_length=4,max_length=4)
    band_width_px:float=Field(gt=0)

class NewAnnotation(Geometry):
    reference_id:UUID
    screen_id:UUID|None=None
    screen_name:str|None=None

class EditAnnotation(Geometry):
    version:int=Field(ge=1)

@router.get("/{sam}/screens")
def screens(sam:str):
    return service.list_screens(sam)

@router.get("/{sam}/photos/{reference_id}/screen-metadata")
def photo_metadata(sam:str,reference_id:UUID):
    return service.metadata(sam,reference_id)

@router.post("/{sam}/screen-annotations",status_code=201)
def create_annotation(sam:str,payload:NewAnnotation):
    return service.create(sam,payload.reference_id,payload.screen_id,payload.screen_name,
                          [point.model_dump() for point in payload.corners],payload.band_width_px)

@router.patch("/{sam}/screen-annotations/{annotation_id}")
def edit_annotation(sam:str,annotation_id:UUID,payload:EditAnnotation):
    return service.update(sam,annotation_id,payload.version,
                          [point.model_dump() for point in payload.corners],payload.band_width_px)

@router.delete("/{sam}/screen-annotations/{annotation_id}")
def delete_annotation(sam:str,annotation_id:UUID):
    return service.remove_annotation(sam,annotation_id)

@router.delete("/{sam}/screens/{screen_id}")
def delete_screen(sam:str,screen_id:UUID):
    return service.remove_screen(sam,screen_id)
