"""Read-only actual data-mount storage statistics."""
from fastapi import APIRouter
from ...services.storage_usage import usage
from ...services.storage_breakdown import breakdown
router=APIRouter(prefix="/api/storage",tags=["storage"])

@router.get("/usage")
def storage_usage():return usage()

@router.get("/breakdown")
def storage_breakdown():return breakdown()
