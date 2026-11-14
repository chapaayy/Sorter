"""Default-deny access to explicitly granted, finished results."""
import re
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
    if user["access_role"] == "viewer" and method in ("GET", "HEAD") and VIEWER_READ_ROUTE.fullmatch(path):
        return
    raise HTTPException(403, "Недостаточно прав")


def is_viewer(request):
    user = current_user(request)
    return user is not None and user["access_role"] == "viewer"


def current_user(request):
    return getattr(request.state, "user", None) if request is not None else None


def require_published(db, run_id, user_id):
    row = db.execute("""SELECT j.status,b.display_name FROM jobs j
        JOIN batches b ON b.id=j.batch_id
        JOIN result_access_grants g ON g.run_id=j.id AND g.user_id=%s
        WHERE j.id=%s AND j.status IN ('completed','completed_with_errors') AND b.delete_state='active'""",
        (user_id, run_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Результат не найден")
    return row


def check_published(request, run_id):
    if not is_viewer(request):
        return None
    from ..database import connect
    with connect() as db:
        return require_published(db, run_id, current_user(request)["id"])
