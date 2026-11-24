"""SAM gallery cursor endpoints: refs are independent of batch ownership."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException
from ..file_response import LeasedFileResponse
from ...services import reference_archives,reference_sides,archive_cache
from ...storage.reference_lifecycle import ReadPin
from pydantic import BaseModel,Field
import uuid
from ...services import references as reference_service
from ...services import construction_catalog,construction_relabel
from app.photos.labels import check_label
from ...database import connect
from ...db.repositories.pagination import page

router=APIRouter(prefix="/api/references",tags=["references"])

@router.get("/export")
def export_all_references():
    pin=archive_cache.pin(reference_archives.EXPORTS)
    try:
        with ReadPin():
            plan=reference_archives.current_plan()
            archive=reference_archives.prepare(plan)
        return LeasedFileResponse(archive,archive_pin=pin,media_type="application/zip",
            filename=f"Образцы — версия {plan.version}.zip",
            headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
    except BaseException:
        pin.close()
        raise

class PreviewImport(BaseModel):
    folders:list[str]=Field(min_length=1,max_length=5000)

class NewConstruction(BaseModel):
    kind:str
    city_code:str|None=None
    number:str|None=None
    address:str|None=None
    name:str|None=None

@router.post('/constructions',status_code=201)
def create_construction(payload:NewConstruction):
    return construction_catalog.create(payload.kind,city_code=payload.city_code,
        number=payload.number,address=payload.address,name=payload.name)

@router.patch("/constructions/{sam}")
def edit_construction(sam:str,payload:NewConstruction):
    return construction_relabel.update(sam,payload.kind,city_code=payload.city_code,
        number=payload.number,address=payload.address,name=payload.name)

class ChangeAddress(BaseModel):
    address:str=Field(min_length=1,max_length=120)

@router.post("/import/preview")
def preview_import(payload:PreviewImport):
    return construction_catalog.preview(payload.folders)

@router.patch("/constructions/{sam}/address")
def change_address(sam:str,payload:ChangeAddress):
    return construction_catalog.change_address(sam,payload.address)

class AssignSides(BaseModel):
    photo_ids:list[uuid.UUID]=Field(min_length=1,max_length=500)
    side:str|None=Field(default=None,max_length=80)

@router.patch("/{sam}/sides")
def assign_sides(sam:str,payload:AssignSides):
    return reference_sides.assign(sam,payload.photo_ids,payload.side)

@router.get("/{sam}/photos")
def gallery(sam:str,cursor:str|None=None,limit:int=60):
    try:label=check_label(sam)
    except ValueError:raise HTTPException(422,"Неверный SAM")
    return _page(label,cursor,limit)

def _page(sam,cursor,limit):
    with connect() as db:
        result=page(db,"u.kind='reference' AND u.finalized AND u.sam=%s",
                    (sam,),cursor=cursor,limit=limit)
        sides=reference_sides.active_sides(db,[uuid.UUID(item['id']) for item in result['photos']])
        for item in result['photos']:
            item['side']=sides.get(item['id'])
        return result

@router.get("")
def list_references():
    """Gallery projection of the currently published reference library."""
    with connect() as db:
        rows=db.execute("""SELECT coalesce(c.sam,u.sam) AS sam,
            coalesce(u.photos,0) AS photos,c.city_code,c.construction_number,c.address,
            coalesce(c.kind,'standard') AS kind
            FROM reference_constructions c FULL OUTER JOIN (
                SELECT sam,count(*) AS photos FROM uploads
                WHERE kind='reference' AND finalized GROUP BY sam
            ) u ON c.sam=u.sam
            ORDER BY coalesce(c.sam,u.sam)""").fetchall()
    for row in rows:
        row["display_name"]=construction_catalog.construction_title(row["sam"],row["kind"],row["address"])
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
