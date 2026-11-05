"""Bounded compatible log tail plus forward cursor pages for large journals."""
from fastapi import APIRouter,HTTPException
from app.results.repository import load_run
from app.logging.events import read, page,usage
router=APIRouter(prefix="/api/logs",tags=["logs"])

@router.get("/usage")
def logs_usage():return usage()

@router.get("/{run_id}")
def logs(run_id:str,model:str|None=None,level:str|None=None,
         source:str|None=None,search:str|None=None,limit:int=250):
    try:
        load_run(run_id)
        return {"events":read(run_id,model=model,level=level,source=source,search=search,limit=limit)}
    except (FileNotFoundError,ValueError):raise HTTPException(404,"Запуск или фильтр не найден")

@router.get("/{run_id}/page")
def paged(run_id:str,cursor:str|None=None,limit:int=200,
          model:str|None=None,level:str|None=None,
          source:str|None=None,search:str|None=None):
    try:
        load_run(run_id)
        return page(run_id,cursor=cursor,limit=limit,model=model,level=level,
                    source=source,search=search)
    except FileNotFoundError:raise HTTPException(404,"Запуск не найден")
    except ValueError:raise HTTPException(422,"Неверный или устаревший курсор")
