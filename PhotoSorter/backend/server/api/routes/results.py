"""Paginated results for the future UI; legacy full-result endpoints preserved."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException,Query,Request
from app.results.repository import load_model,load_run
from ...database import connect
from ...security.access_policy import check_published,current_user,is_owner
from ...security.roles import level,result_allowed
from ...security.scopes import allowed_for
from ...services import result_pages

router=APIRouter(prefix="/api/results",tags=["results"])

def safe_manifest(run_id):
    try:return load_model(run_id,"megaloc")
    except (FileNotFoundError,ValueError):raise HTTPException(404,"Результат не найден")

def catalog_card(row,user):
    """Project only approved display metadata; never serialize a job snapshot."""
    owner=user is None or is_owner(user)
    own=bool(user and row["owner_id"]==user["id"])
    granted=row["granted"]
    def scoped(key):
        return owner or allowed_for(level(user,key),own=own,granted=False)
    source=scoped("photos.view")
    active=row["delete_state"]=="active"
    media=active and (owner or result_allowed(user,"results.media",own=own,granted=granted))
    zip_allowed=active and (owner or result_allowed(user,"results.zip",own=own,granted=granted))
    card={key:row[key] for key in ("id","status","display_name","finished_at","started_at",
        "actual_started_at","actual_finished_at","groups","uncertain","overall_percent")}
    card["photo_count"]=row["processed"] if row["processed"] is not None else row["source_photos"] if source else None
    card.update(can_media=media,can_zip=zip_allowed,can_open=active,
        can_history=active and scoped("queue.view") and scoped("queue.detail"),
        thumbnail_url="/api/thumbnails/"+str(row["cover_id"])
            if media and source and scoped("photos.media") and row["cover_id"] else None)
    if source:
        card.update(batch_id=str(row["batch_id"]),delete_state=row["delete_state"],
                    deletion_progress=row["deletion_progress"])
    return card

@router.get("/catalog")
def catalog(request:Request, limit: int = Query(30,ge=1,le=100), offset: int = Query(0,ge=0),
            search:str=Query("",max_length=254)):
    user=current_user(request)
    owner=user is None or is_owner(user)
    user_id=user["id"] if user is not None else None
    scope="all" if owner else level(user,"results.view")
    source_scope="all" if owner else level(user,"photos.view")
    with connect() as db:
        rows=db.execute("""SELECT j.id,j.status,j.finished_at,j.started_at,b.display_name,
            b.id AS batch_id,b.owner_id,b.delete_state,
            j.snapshot->>'actual_started_at' AS actual_started_at,
            j.snapshot->>'actual_finished_at' AS actual_finished_at,
            j.snapshot->'models'->'megaloc'->'processed' AS processed,
            j.snapshot->'models'->'megaloc'->'groups' AS groups,
            j.snapshot->'models'->'megaloc'->'uncertain' AS uncertain,
            j.snapshot->'progress'->'overall_percent' AS overall_percent,
            g.granted,cover.id AS cover_id,counts.photos AS source_photos,
            CASE WHEN c.progress IS NOT NULL THEN jsonb_build_object(
                'phase',c.progress->'phase','done',c.progress->'done','total',c.progress->'total') END AS deletion_progress
            FROM jobs j JOIN batches b ON b.id=j.batch_id
            CROSS JOIN LATERAL (SELECT EXISTS(SELECT 1 FROM result_access_grants g
                 WHERE g.run_id=j.id AND g.user_id=%s) AS granted) g
            LEFT JOIN cleanup_tasks c ON c.batch_id=b.id
            LEFT JOIN LATERAL (SELECT u.id FROM uploads u JOIN thumbnail_tasks t ON t.upload_id=u.id
                WHERE u.batch_id=b.id AND u.kind='fo' AND u.finalized AND t.state='ready'
                ORDER BY u.created_at,u.id LIMIT 1) cover ON true
            LEFT JOIN LATERAL (SELECT count(*) AS photos FROM uploads u WHERE u.batch_id=b.id
                AND u.kind='fo' AND u.finalized AND
                ((u.media_action IS NULL AND u.original_media_type IS NULL) OR
                 (u.media_action='keep' AND coalesce(u.original_media_type,'') NOT LIKE 'video/%%') OR
                 (u.media_output_path IS NOT NULL AND coalesce(u.original_media_type,'') NOT LIKE 'video/%%'))) counts ON true
            WHERE j.status IN ('completed','completed_with_errors')
              AND (b.delete_state='active' OR (b.delete_state IN ('deleting','delete_failed')
                   AND (%s='all' OR (%s='own' AND b.owner_id=%s))))
              AND (%s='all' OR (%s='own' AND b.owner_id=%s) OR (%s='granted' AND g.granted))
              AND strpos(lower(b.display_name),lower(%s))>0
            ORDER BY j.finished_at DESC NULLS LAST,j.id DESC LIMIT %s OFFSET %s""",
            (user_id,source_scope,source_scope,user_id,scope,scope,user_id,scope,search.strip(),limit+1,offset)).fetchall()
    return {"items":[catalog_card(row,user) for row in rows[:limit]],"has_more":len(rows)>limit}

@router.get("/{run_id}")
def overview(run_id:str, request:Request=None):
    published = check_published(request, run_id)
    if published is not None:
        return {"id":run_id,"status":published["status"],"display_name":published["display_name"],**{k:published[k] for k in ('batch_id','owner_id') if k in published},**({"can_media":False} if not published["can_media"] else {}),**({"can_zip":False} if not published["can_zip"] else {})}
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
