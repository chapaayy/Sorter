"""List and register short region codes."""
from fastapi import APIRouter
from pydantic import BaseModel,Field
from ...services import regions

router=APIRouter(prefix="/api/regions",tags=["regions"])

class NewRegion(BaseModel):
    code:str=Field(min_length=2,max_length=5)

@router.get("")
def list_regions():
    return regions.list_all()

@router.post("",status_code=201)
def add_region(payload:NewRegion):
    return regions.register(payload.code)
