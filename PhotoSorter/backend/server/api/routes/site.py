"""Serve the single production Vue app from '/' with safe static asset routing.

No legacy frontend is built or exposed. All /api routes are registered before
this catch-all router; unknown paths, including retired /v3 and /static, 404.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.config import PROJECT_DIR

router = APIRouter()
VUE_DIST = PROJECT_DIR / "frontend" / "dist"
UI_SECTIONS = frozenset({"login", "register", "fo", "references", "processing", "queue", "results", "logs", "settings"})


def _vue_index():
    index_file = VUE_DIST / "index.html"
    if not index_file.is_file():
        raise HTTPException(503, "Frontend build missing")
    return FileResponse(index_file, headers={"Cache-Control": "no-store"})


@router.get("/", include_in_schema=False)
def index():
    return _vue_index()


@router.get("/assets/{filename:path}", include_in_schema=False)
def asset(filename: str):
    """Serve built Vite assets only; reject path traversal and symlinks."""
    root = (VUE_DIST / "assets").resolve()
    candidate = VUE_DIST / "assets" / filename
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root) or not candidate.is_file():
        raise HTTPException(404, "Resource not found")
    return FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/{path:path}", include_in_schema=False)
def app_route(path: str):
    """Only known Vue history routes; never serve API/legacy/unexpected paths."""
    first = path.split("/", 1)[0]
    if first not in UI_SECTIONS:
        raise HTTPException(404, "Unknown page")
    return _vue_index()
