"""Read-only actual data-mount storage statistics."""
from fastapi import APIRouter
from ...services.storage_usage import usage
from ...services.storage_breakdown import breakdown
from ...services import storage_inventory
from fastapi import Query
router=APIRouter(prefix="/api/storage",tags=["storage"])

@router.get("/usage")
def storage_usage():return usage()

@router.get("/breakdown")
def storage_breakdown():return breakdown()

@router.post("/inventory/scan")
def scan_inventory():
    return storage_inventory.scan()

@router.get("/inventory/files")
def inventory_files(
    snapshot_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    category: str = "",
    search: str = "",
):
    return storage_inventory.files(snapshot_id=snapshot_id, offset=offset, limit=limit,
                                   category=category, search=search)
