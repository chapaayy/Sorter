"""Keep legacy '/' and '/static' while Stage 3 Vue is opt-in under '/v3/'."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse,RedirectResponse
from app.config import PROJECT_DIR

router=APIRouter()
FRONTEND=PROJECT_DIR/"frontend"/"static"
VUE_DIST=PROJECT_DIR/"frontend"/"dist"

@router.get("/",include_in_schema=False)
def index():
    return FileResponse(FRONTEND/"index.html")

@router.get("/static/{filename}",include_in_schema=False)
def asset(filename:str):
    if filename not in ("app.js","style.css"):raise HTTPException(404)
    return FileResponse(FRONTEND/filename)

@router.get("/v3",include_in_schema=False)
def new_ui():
    return RedirectResponse("/v3/",status_code=308)

@router.get("/v3/assets/{filename:path}",include_in_schema=False)
def vue_asset(filename:str):
    """Only Vite-built assets, reject paths or symlinks outside dist/assets."""
    root=(VUE_DIST/"assets").resolve()
    candidate=VUE_DIST/"assets"/filename
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root) or not candidate.is_file():
        raise HTTPException(404,"Resource not found")
    return FileResponse(candidate,headers={"Cache-Control":"public, max-age=31536000, immutable"})

@router.get("/v3/{path:path}",include_in_schema=False)
def vue_app(path:str):
    """History-mode fallback only for UI paths; never expose arbitrary files."""
    first=path.split("/",1)[0]
    if first not in ("","login","fo","references","processing","results","logs","settings"):
        raise HTTPException(404,"Unknown UI page")
    index_file=VUE_DIST/"index.html"
    if not index_file.is_file():
        raise HTTPException(503,"Vue build missing. Existing legacy UI remains at /")
    return FileResponse(index_file,headers={"Cache-Control":"no-store"})
