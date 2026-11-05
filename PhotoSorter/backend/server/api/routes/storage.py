"""Read-only actual data-mount storage statistics."""
from fastapi import APIRouter
from ...services.storage_usage import usage
router=APIRouter(prefix="/api/storage",tags=["storage"])

@router.get("/usage")
def storage_usage():return usage()
