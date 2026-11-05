"""Restrict photo serving to trusted persisted storage locations."""
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from app.config import DATA_DIR
from app.photos.reader import EXTS
from .results import safe_manifest

router=APIRouter(prefix="/api/images",tags=["images"])

def file_allowed(file:Path):
    roots=[(DATA_DIR/name).resolve() for name in ("references","uploads","outputs")]
    resolved=file.resolve()
    if not any(resolved.is_relative_to(root) for root in roots):
        raise HTTPException(404,"Файл недоступен")
    if not file.is_file() or file.suffix.lower() not in EXTS:
        raise HTTPException(404,"Файл не найден")
    return file

@router.get("/{run_id}/megaloc/{index}")
def image(run_id:str,index:int,kind:str="query",candidate:int=0):
    rows=safe_manifest(run_id)
    if index<0 or index>=len(rows):raise HTTPException(404,"Фотография не найдена")
    row=rows[index]
    if kind=="query":filename=row["query"]
    elif kind=="copy":filename=row["copy"]
    elif kind=="reference":
        top=row.get("top",[])
        if not 0<=candidate<len(top):raise HTTPException(404,"Образец не найден")
        filename=top[candidate]["reference"]
    else:raise HTTPException(422,"Неверный тип изображения")
    return FileResponse(file_allowed(Path(filename)))
