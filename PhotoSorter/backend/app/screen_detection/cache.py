"""Versioned XFeat reference descriptors under PhotoSorter/data, never MegaLoc cache."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path
import numpy as np
from app.config import DATA_DIR
from .xfeat_assets import MODEL_ID
from .features import oriented_image,extract,border_features

CACHE_ROOT=DATA_DIR/"cache"/"xfeat"/"references"
EXTRACTOR_VERSION="exif-rgb-max1280-top4096-border-v2"

def key(annotation:dict)->str:
    data={key:annotation[key] for key in
          ("id","source_sha256","version","corners","band_width_px")}
    data["id"]=str(data["id"])
    data.update({"model":MODEL_ID,"preprocessing":EXTRACTOR_VERSION})
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def prepare_reference(model,annotation:dict,path:Path)->dict:
    hashkey=key(annotation)
    destination=CACHE_ROOT/(hashkey+".npz")
    if destination.is_file() and not destination.is_symlink():
        try:
            with np.load(destination,allow_pickle=False) as saved:
                points=saved["xy"];descriptors=saved["descriptors"];sides=saved["sides"]
            if (points.ndim==2 and points.shape[1]==2 and
                descriptors.shape==(len(points),64) and
                sides.shape==(len(points),) and
                np.isfinite(points).all() and np.isfinite(descriptors).all()):
                return {"xy":points,"descriptors":descriptors,"sides":sides}
        except (ValueError,OSError,KeyError):
            pass
    rgb=oriented_image(path)
    if rgb.shape[1]!=annotation["image_width"] or rgb.shape[0]!=annotation["image_height"]:
        raise ValueError("Размеры Образца отличаются от сохранённой разметки")
    features=border_features(extract(model,rgb),annotation["corners"],
                             annotation["band_width_px"],rgb.shape[1],rgb.shape[0])
    CACHE_ROOT.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".xfeat.",suffix=".npz",dir=CACHE_ROOT)
    try:
        with os.fdopen(fd,"wb") as stream:
            np.savez_compressed(stream,**features)
        os.replace(name,destination)
    finally:
        Path(name).unlink(missing_ok=True)
    return features

def prune_inactive(active_keys:set[str],min_age_seconds:int=604800)->dict:
    """Explicit safe maintenance; no deletion of current or recently used keys.

    Only known 64-hex cache filenames are touched; symlinks and arbitrary
    files are deliberately ignored. Current snapshots must be inspected first.
    """
    import re
    import time
    removed=0
    now=time.time()
    if not CACHE_ROOT.exists() or CACHE_ROOT.is_symlink():
        return {"removed":0}
    for path in CACHE_ROOT.iterdir():
        if not re.fullmatch(r"[a-f0-9]{64}\.npz",path.name):
            continue
        if path.is_symlink() or not path.is_file() or path.stem in active_keys:
            continue
        if now-path.stat().st_mtime<min_age_seconds:
            continue
        path.unlink()
        removed+=1
    return {"removed":removed}
