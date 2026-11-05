"""Existing per-run event API preserved (pagination will follow in stage 2)."""
from fastapi import APIRouter,HTTPException
from app.results.repository import load_run
from app.logging.events import read as read_events

router=APIRouter(prefix="/api/logs",tags=["logs"])

@router.get("/{run_id}")
def logs(run_id:str,model:str|None=None,level:str|None=None):
    try:
        load_run(run_id)
        return {"events":read_events(run_id,model=model,level=level)}
    except (FileNotFoundError,ValueError):raise HTTPException(404,"Запуск не найден")
