"""Default-deny access to explicitly granted, finished results."""
import re
from .roles import level,result_allowed
from fastapi import HTTPException

RUN = r"[0-9]{8}T[0-9]{6}-[a-f0-9]{12}"
VIEWER_READ_ROUTE = re.compile(
    rf"/api/(?:results/(?:catalog|{RUN}(?:/(?:sam|groups|photos))?)|images/{RUN}/megaloc/[0-9]+|download/{RUN})"
)
SESSION_ENDPOINTS = {("GET", "/api/auth/me"), ("POST", "/api/auth/logout")}


def is_owner(user):
    return user["username"] == "admin" and user["access_role"] == "owner"


def authorize(user, method, path):
    if is_owner(user) or (method, path) in SESSION_ENDPOINTS:
        return
    if user.get("blocked"):
        raise HTTPException(403,"Аккаунт заблокирован")
    if user["access_role"] == "viewer" and method in ("GET", "HEAD") and VIEWER_READ_ROUTE.fullmatch(path):
        action="results.zip" if path.startswith("/api/download/") else "results.media" if path.startswith("/api/images/") or path.endswith("/photos") else "results.view"
        if level(user,"results.view")!="none" and level(user,action)!="none":return
    if method=="GET" and path in ("/api/auth/storage","/api/auth/profile","/api/activity/own"):return
    from .route_permissions import authorize_route
    return authorize_route(user,method,path)


def is_viewer(request):
    user = current_user(request)
    return user is not None and user["access_role"] == "viewer"


def current_user(request):
    return getattr(request.state, "user", None) if request is not None else None


def require_published(db, run_id, user_id, user=None, action="results.view"):
    row = db.execute("""SELECT j.status,b.display_name,b.owner_id,b.id AS batch_id,
        EXISTS(SELECT 1 FROM result_access_grants g WHERE g.run_id=j.id AND g.user_id=%s) AS granted
        FROM jobs j JOIN batches b ON b.id=j.batch_id
        WHERE j.id=%s AND j.status IN ('completed','completed_with_errors') AND b.delete_state='active'""",
        (user_id,run_id)).fetchone()
    if row is None or not result_allowed(user or {"access_role":"viewer"},action,
                                          own=row["owner_id"]==user_id,granted=row["granted"]):
        raise HTTPException(404,"Результат не найден")
    # Only expose the source batch ID if the caller can actually read it.
    own=row['owner_id']==user_id
    source_scope=level(user,'photos.view')
    source={'batch_id':str(row['batch_id']),'owner_id':str(row['owner_id'])} if row.get('batch_id') and (source_scope=='all' or (source_scope=='own' and own)) else {}
    return {**source,"status":row["status"],"display_name":row["display_name"],
            "can_media":result_allowed(user or {"access_role":"viewer"},"results.media",own=row["owner_id"]==user_id,granted=row["granted"]),
            "can_zip":result_allowed(user or {"access_role":"viewer"},"results.zip",own=row["owner_id"]==user_id,granted=row["granted"])}


def check_published(request, run_id, action="results.view"):
    if not is_viewer(request):
        return None
    from ..database import connect
    user=current_user(request)
    with connect() as db:
        return require_published(db,run_id,user["id"],user,action)
