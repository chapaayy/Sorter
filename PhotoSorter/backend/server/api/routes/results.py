"""Read-only run and result views; no modifications to MegaLoc scores."""
from fastapi import APIRouter,HTTPException
from app.results.repository import load_model,load_run

router=APIRouter(prefix="/api/results",tags=["results"])

def safe_manifest(run_id):
    try:return load_model(run_id,"megaloc")
    except (FileNotFoundError,ValueError):raise HTTPException(404,"Результат не найден")

@router.get("/{run_id}")
def overview(run_id:str):
    try:return load_run(run_id)
    except (FileNotFoundError,ValueError):raise HTTPException(404,"Запуск не найден")

@router.get("/{run_id}/megaloc")
def results(run_id:str):
    rows=safe_manifest(run_id)
    counts={}
    for item in rows:
        label=item["assigned_sam"]
        counts[label]=counts.get(label,0)+1
    return {"model":"megaloc","rows":rows,"sam_counts":counts}
