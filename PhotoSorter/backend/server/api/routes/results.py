"""Paginated results for the future UI; legacy full-result endpoints preserved."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException
from app.results.repository import load_model,load_run
from ...database import connect
from ...services import result_pages

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

@router.get("/{run_id}/sam")
def sam_groups(run_id:str):
    return result_pages.counts(run_id)["sam"]

@router.get("/{run_id}/groups")
def groups(run_id:str):
    return result_pages.counts(run_id)["groups"]

@router.get("/{run_id}/photos")
def photos(run_id:str,sam:str|None=None,group:str|None=None,
           cursor:str|None=None,limit:int=60):
    result=result_pages.page(run_id,sam=sam,group=group,cursor=cursor,limit=limit)
    queries=[r.get("query") for r in result["rows"] if r.get("query")]
    photo_ids={}
    if queries:
        with connect() as db:
            matched=db.execute("""SELECT target_path,id FROM uploads
              WHERE finalized AND kind='fo' AND target_path=ANY(%s)""",
              (queries,)).fetchall()
            photo_ids={r["target_path"]:str(r["id"]) for r in matched}
    items=[]
    for row in result["rows"]:
        upload_id=photo_ids.get(row.get("query"))
        items.append({"index":row["index"],"assigned_sam":row.get("assigned_sam"),
            "group_id":row.get("group_id"),"score":row.get("score"),
            "verdict":row.get("verdict"),"reason":row.get("reason"),
            "thumbnail_url":f"/api/thumbnails/{upload_id}" if upload_id else None,
            "image_url":f'/api/images/{run_id}/megaloc/{row["index"]}?kind=query'})
    return {"photos":items,"next_cursor":result["next_cursor"]}
