"""Bounded compatible log tail plus forward cursor pages for large journals."""
from fastapi import APIRouter,HTTPException,Request
from ...database import connect
from ...security.route_permissions import owner_filter
from ...security.access_policy import current_user
from app.results.repository import load_run
from app.logging.events import read, page,tail,usage
router=APIRouter(prefix="/api/logs",tags=["logs"])

@router.get("/usage")
def logs_usage():return usage()

@router.get("/runs")
def available_runs(request:Request):
    owner=owner_filter(current_user(request),'logs.view')
    with connect() as db:
        rows=db.execute("""SELECT j.id,j.started_at FROM jobs j JOIN batches b ON b.id=j.batch_id
            WHERE b.delete_state='active' AND (%s::bigint IS NULL OR b.owner_id=%s)
            ORDER BY j.created_at DESC,j.id DESC LIMIT 200""",(owner,owner)).fetchall()
    return {'runs':rows}

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
          source:str|None=None,search:str|None=None,tail_mode:bool=False):
    try:
        load_run(run_id)
        if tail_mode:return tail(run_id,limit=limit,model=model,level=level,
                                 source=source,search=search)
        return page(run_id,cursor=cursor,limit=limit,model=model,level=level,
                    source=source,search=search)
    except FileNotFoundError:raise HTTPException(404,"Запуск не найден")
    except ValueError:raise HTTPException(422,"Неверный или устаревший курсор")
