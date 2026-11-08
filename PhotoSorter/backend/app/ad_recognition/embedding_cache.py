"""Layout image embeddings isolated from XFeat and MegaLoc; immutable SHA keys."""
from __future__ import annotations
import hashlib
import os
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from app.config import DATA_DIR
from . import dino

ROOT=DATA_DIR/"cache"/"dinov2"/"layouts"

def key(checksum:str)->str:
    return hashlib.sha256((checksum+":"+dino.SIGNATURE).encode()).hexdigest()

def vector(model,row:dict,file:Path)->np.ndarray:
    path=ROOT/(key(row["checksum"])+".npy")
    if path.is_file() and not path.is_symlink():
        try:
            value=np.load(path,allow_pickle=False)
            if (value.shape==(dino.EMBED_DIM,) and np.isfinite(value).all()
                    and abs(float(np.linalg.norm(value))-1)<.01):
                return value
        except (ValueError,OSError,EOFError):
            pass
    with Image.open(file) as raw:
        picture=ImageOps.exif_transpose(raw).convert("RGB")
    value=dino.embed(model,picture)
    ROOT.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix=".layout.",suffix=".npy",dir=ROOT)
    try:
        with os.fdopen(fd,"wb") as output:np.save(output,value)
        os.replace(temp,path)
    finally:Path(temp).unlink(missing_ok=True)
    return value

def prune_inactive(live_keys:set[str],min_age_seconds:int=604800)->dict:
    """Manual clean-up of obsolete embeddings, never touches model weights or layouts."""
    import re
    import time
    if ROOT.is_symlink() or not ROOT.is_dir():return {"removed":0}
    now=time.time()
    removed=0
    for file in ROOT.iterdir():
        if (file.is_symlink() or not file.is_file() or
            not re.fullmatch(r"[a-f0-9]{64}[.]npy",file.name) or
            file.stem in live_keys or now-file.stat().st_mtime<min_age_seconds):
            continue
        file.unlink()
        removed+=1
    return {"removed":removed}

def prepared(row:dict)->np.ndarray:
    """Read only published preparation; never infer while serving FO."""
    if not row.get("prepared_key") or not row.get("embedding_path"):
        raise ValueError("Рекламный макет ещё не подготовлен")
    path=ROOT/(key(row["checksum"])+".npy")
    if path.is_symlink() or str(path)!=str(row["embedding_path"]) or not path.is_file():
        raise ValueError("Кэш DINOv2 устарел или отсутствует")
    try:
        value=np.load(path,allow_pickle=False)
        if (value.shape==(dino.EMBED_DIM,) and np.isfinite(value).all()
                and abs(float(np.linalg.norm(value))-1)<.01):
            return value
    except (OSError,ValueError,EOFError) as exc:
        raise ValueError("Повреждённый кэш DINOv2") from exc
    raise ValueError("Некорректный вектор DINOv2")
