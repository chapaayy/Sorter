"""Shared image-upload validation for FO and staged reference manifests."""
from pathlib import Path
import re
from fastapi import HTTPException
from app.photos.reader import EXTS

MAX_FILE_BYTES=60*1024*1024

def safe_name(value:str)->str:
    name=Path(value.replace('\\','/')).name.strip()
    if (not name or name in ('.','..') or len(name)>200 or
        not re.fullmatch(r'[\w.()\- +]+',name,re.UNICODE)):
        raise HTTPException(422,'Недопустимое имя файла')
    if Path(name).suffix.lower() not in EXTS:
        raise HTTPException(422,'Поддерживаются только изображения')
    return name
