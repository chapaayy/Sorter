"""Model status and download; keep MegaLoc-only contract."""
from fastapi import APIRouter,HTTPException
from app.system.model_store import files_present
from app.system.downloads import downloads
from ...database import connect

router=APIRouter(prefix="/api/models",tags=["models"])

@router.get("")
def model_info():
    present=files_present()
    return {"models":[{"id":"megaloc","title":"MegaLoc","available":present,
                       "reason":"" if present else "Модель ещё не загружена",
                       "downloadable":True}],"device":"cpu","downloads":downloads.status()}

@router.post("/megaloc/download",status_code=202)
def download_model():
    with connect() as db:
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone():
            raise HTTPException(409,"Дождитесь окончания сортировки")
    try:return downloads.start("megaloc")
    except RuntimeError as exc:raise HTTPException(409,str(exc))
