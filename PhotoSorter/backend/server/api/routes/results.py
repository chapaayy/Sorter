"""Paginated results for the future UI; legacy full-result endpoints preserved."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException,Query,Request
from app.results.repository import load_model,load_run
from ...database import connect
from ...security.access_policy import check_published,current_user,is_viewer
from ...security.roles import level
from ...services import result_pages

router=APIRouter(prefix="/api/results",tags=["results"])

def safe_manifest(run_id):
    try:return load_model(run_id,"megaloc")
    except (FileNotFoundError,ValueError):raise HTTPException(404,"Результат не найден")

@router.get("/catalog")
def catalog(request:Request, limit: int = Query(30,ge=1,le=100), offset: int = Query(0,ge=0)):
    user=current_user(request)
    user_id=user["id"] if is_viewer(request) else None
    scope=level(user,"results.view") if user_id is not None else "all"
    with connect() as db:
        rows = db.execute("""SELECT j.id,j.status,j.finished_at,b.display_name FROM jobs j
            JOIN batches b ON b.id=j.batch_id
            WHERE j.status IN ('completed','completed_with_errors') AND b.delete_state='active'
            AND (%s='all' OR (%s='own' AND b.owner_id=%s) OR (%s='granted' AND EXISTS(SELECT 1 FROM result_access_grants g
                WHERE g.run_id=j.id AND g.user_id=%s)))
            ORDER BY j.finished_at DESC NULLS LAST,j.id DESC LIMIT %s OFFSET %s""",
            (scope,scope,user_id,scope,user_id,limit+1,offset)).fetchall()
    return {"items":rows[:limit],"has_more":len(rows)>limit}

@router.get("/{run_id}")
def overview(run_id:str, request:Request=None):
    published = check_published(request, run_id)
    if published is not None:
        return {"id":run_id,"status":published["status"],"display_name":published["display_name"],**({"can_media":False} if not published["can_media"] else {}),**({"can_zip":False} if not published["can_zip"] else {})}
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
def sam_groups(run_id:str, request:Request=None):
    check_published(request,run_id)
    return result_pages.counts(run_id)["sam"]

@router.get("/{run_id}/groups")
def groups(run_id:str, request:Request=None):
    check_published(request,run_id)
    return result_pages.counts(run_id)["groups"]

@router.get("/{run_id}/photos")
def photos(run_id:str,sam:str|None=None,group:str|None=None,
           cursor:str|None=None,limit:int=60,request:Request=None):
    published = check_published(request,run_id,"results.media")
    result=result_pages.page(run_id,sam=sam,group=group,cursor=cursor,limit=limit)
    queries=[r.get("query") for r in result["rows"] if r.get("query")]
    photo_ids={}
    if queries and published is None:
        with connect() as db:
            matched=db.execute("""SELECT target_path,id FROM uploads
              WHERE finalized AND kind='fo' AND target_path=ANY(%s)""",
              (queries,)).fetchall()
            photo_ids={r["target_path"]:str(r["id"]) for r in matched}
    items=[]
    for row in result["rows"]:
        upload_id=photo_ids.get(row.get("query"))
        items.append({"index":row["index"],"assigned_sam":row.get("assigned_sam"),
            "group_id":row.get("group_id"),"side":row.get("side"),"score":row.get("score"),
            "verdict":row.get("verdict"),"reason":row.get("reason"),
            "filename":row.get("export_name"),"media_kind":row.get("media_kind"),
            "duration":row.get("duration"),
            "thumbnail_url":(f'/api/images/{run_id}/megaloc/{row["index"]}?kind=poster' if row.get("media_kind")=="video"
                             else f"/api/thumbnails/{upload_id or row.get('upload_id')}" if
                             (published is None and (upload_id or row.get("upload_id"))) else None),
            "image_url":f'/api/images/{run_id}/megaloc/{row["index"]}?kind={"copy" if published is not None or row.get("media_kind") else "query"}'})
    return {"photos":items,"next_cursor":result["next_cursor"]}
