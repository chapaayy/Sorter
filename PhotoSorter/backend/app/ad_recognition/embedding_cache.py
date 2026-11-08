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
            if value.shape==(dino.EMBED_DIM,) and np.isfinite(value).all() and
               abs(float(np.linalg.norm(value))-1)<.01:
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
