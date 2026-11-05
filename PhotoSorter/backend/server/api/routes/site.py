"""Legacy static site stays served until Vue frontend passes stage 3 regression."""
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from app.config import PROJECT_DIR

router=APIRouter()
FRONTEND=PROJECT_DIR/"frontend"/"static"
@router.get("/",include_in_schema=False)
def index():return FileResponse(FRONTEND/"index.html")
@router.get("/static/{filename}",include_in_schema=False)
def asset(filename:str):
    if filename not in ("app.js","style.css"):raise HTTPException(404)
    return FileResponse(FRONTEND/filename)
