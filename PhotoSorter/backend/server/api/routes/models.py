"""Explicit asynchronous installation of pinned CPU models from Settings."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException
from app.system.model_store import files_present
from app.system.downloads import downloads,optional_available
from ...database import connect

router=APIRouter(prefix="/api/models",tags=["models"])
MODELS={
    'megaloc':('MegaLoc','Группировка ФО и сопоставление с Образцами'),
    'xfeat':('XFeat','Геометрический поиск своего LED-экрана'),
    'dinov2':('DINOv2','Сопоставление рекламы с макетами'),
    'paddleocr':('PaddleOCR PP-OCRv5','Проверка текста на рекламе'),
}

@router.get("")
def model_info():
    available={'megaloc':files_present()}
    for name in ('xfeat','dinov2','paddleocr'):
        available[name]=optional_available(name)
    return {"models":[{"id":name,"title":title,"description":description,
                       "available":available[name],"downloadable":True,
                       "reason":"" if available[name] else "Модель ещё не установлена"}
                      for name,(title,description) in MODELS.items()],
            "device":"cpu","downloads":downloads.status()}

@router.post("/{model_id}/download",status_code=202)
def download_model(model_id:str):
    if model_id not in MODELS:
        raise HTTPException(404,"Модель не найдена")
    with connect() as db:
        if model_id=='megaloc':
            blocked=db.execute("""SELECT 1 FROM jobs
                WHERE status IN ('queued','running','stopping') LIMIT 1""").fetchone()
            prep=db.execute("""SELECT 1 FROM reference_preparation_jobs
                WHERE state='running' LIMIT 1""").fetchone()
            if blocked or prep:
                raise HTTPException(409,"Дождитесь окончания обработки перед установкой MegaLoc")
        else:
            blocked=db.execute("""SELECT 1 FROM jobs WHERE status IN ('running','stopping')
                AND snapshot->'ad_pipeline'->>'enabled'='true' LIMIT 1""").fetchone()
            if blocked:
                raise HTTPException(409,"Дождитесь завершения распознавания рекламы")
    try:
        return downloads.start(model_id)
    except (RuntimeError,ValueError) as exc:
        raise HTTPException(409,str(exc)) from exc
