"""SAM gallery cursor endpoints: refs are independent of batch ownership."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from ...services import references as reference_service
from ...services import construction_catalog
from app.photos.labels import check_label
from ...database import connect
from ...db.repositories.pagination import page

router=APIRouter(prefix="/api/references",tags=["references"])

class PreviewImport(BaseModel):
    folders:list[str]=Field(min_length=1,max_length=5000)

class ChangeAddress(BaseModel):
    address:str=Field(min_length=1,max_length=120)

@router.post("/import/preview")
def preview_import(payload:PreviewImport):
    return construction_catalog.preview(payload.folders)

@router.patch("/constructions/{sam}/address")
def change_address(sam:str,payload:ChangeAddress):
    return construction_catalog.change_address(sam,payload.address)

@router.get("/{sam}/photos")
def gallery(sam:str,cursor:str|None=None,limit:int=60):
    try:label=check_label(sam)
    except ValueError:raise HTTPException(422,"Неверный SAM")
    return _page(label,cursor,limit)

def _page(sam,cursor,limit):
    with connect() as db:
        return page(db,"u.kind='reference' AND u.finalized AND u.sam=%s",
                    (sam,),cursor=cursor,limit=limit)

@router.get("")
def list_references():
    """Gallery projection of the currently published reference library."""
    with connect() as db:
        rows=db.execute("""SELECT u.sam,count(*) AS photos,
            c.city_code,c.construction_number,c.address,
            CASE WHEN c.sam IS NOT NULL THEN u.sam || ' — ' || c.address
                 ELSE u.sam END AS display_name
            FROM uploads u LEFT JOIN reference_constructions c ON c.sam=u.sam
            WHERE u.kind='reference' AND u.finalized
            GROUP BY u.sam,c.sam,c.city_code,c.construction_number,c.address
            ORDER BY u.sam""").fetchall()
    return {"sam":rows,"total":sum(row["photos"] for row in rows)}

@router.get("/files")
def files():
    with connect() as db:
        rows=db.execute("""SELECT id,sam,filename,checksum,created_at
            FROM uploads WHERE kind='reference' AND finalized
            ORDER BY sam,created_at""").fetchall()
    return {"files":[{"id":str(row["id"]),"sam":row["sam"],
             "name":row["filename"],"sha256":row["checksum"]} for row in rows]}

@router.get("/cache/status")
def cache_status():
    return reference_service.cache_status()

@router.delete("/files/{reference_id}")
def delete_photo(reference_id:str):
    return reference_service.delete_photo(reference_id)

@router.delete("/sam/{sam}")
def delete_sam(sam:str):
    return reference_service.delete(sam)
