"""Pinned DINOv2 ViT-S/14 CPU embeddings. Network access only on explicit install."""
from __future__ import annotations
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen
import numpy as np
from PIL import Image,ImageOps
from app.config import WEIGHTS_DIR

NAME="vit_small_patch14_dinov2.lvd142m"
REVISION="bdc84086a163e3e7e6745d534c5f44c97dd493ef"
WEIGHT_SHA256="04d27f3400d059fc0cfd7d17dd1909a75bf3ea8fb3eeb48b97cb99e57ee20081"
URL="https://huggingface.co/timm/"+NAME+"/resolve/"+REVISION+"/model.safetensors"
FILE=WEIGHTS_DIR/"dinov2"/"model.safetensors"
SIZE=518
EMBED_DIM=384
PREPROCESS_VERSION="rgb-exif-letterbox518-imagenet-normalized-v1"
SIGNATURE=hashlib.sha256((WEIGHT_SHA256+PREPROCESS_VERSION+"-timm1.0.15").encode()).hexdigest()
MEAN=np.array([.485,.456,.406],dtype="float32")
STD=np.array([.229,.224,.225],dtype="float32")

def verify()->bool:
    if not FILE.is_file() or FILE.is_symlink() or not 80_000_000<FILE.stat().st_size<100_000_000:
        return False
    digest=hashlib.sha256()
    with FILE.open("rb") as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()==WEIGHT_SHA256

def install()->dict:
    if verify():return status()
    FILE.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix=".dinov2.",dir=FILE.parent)
    try:
        hasher=hashlib.sha256()
        total=0
        with os.fdopen(fd,"wb") as output, urlopen(URL,timeout=90) as source:
            while chunk:=source.read(1024*1024):
                total+=len(chunk)
                if total>100_000_000:raise RuntimeError("DINOv2 checkpoint too large")
                hasher.update(chunk);output.write(chunk)
        if hasher.hexdigest()!=WEIGHT_SHA256:raise RuntimeError("DINOv2 SHA256 mismatch")
        os.replace(temp,FILE)
        return status()
    finally:
        Path(temp).unlink(missing_ok=True)

def status()->dict:
    return {"available":verify(),"model":"DINOv2 ViT-S/14 (timm)",
            "signature":SIGNATURE,"revision":REVISION,
            "weights":str(FILE),"license_note":"Check the specific pretrained weight licence before commercial use"}

def load():
    if not verify():
        raise RuntimeError("DINOv2 weights are unavailable or damaged. Run --install-dino on the API container.")
    import timm
    import torch
    from safetensors.torch import load_file
    model=timm.create_model(NAME,pretrained=False,num_classes=0,img_size=SIZE).to("cpu")
    model.load_state_dict(load_file(str(FILE),device="cpu"),strict=True)
    return model.eval()

def preprocess(picture:Image.Image):
    """Do not centre-crop text; preserve all of the target on a black canvas."""
    import torch
    img=ImageOps.pad(picture.convert("RGB"),(SIZE,SIZE),
                     method=Image.Resampling.BICUBIC,color=(0,0,0))
    array=np.asarray(img,dtype="float32")/255.
    array=(array-MEAN)/STD
    return torch.from_numpy(np.ascontiguousarray(array)).permute(2,0,1).unsqueeze(0)

def embed(model,picture:Image.Image)->np.ndarray:
    import torch
    with torch.inference_mode():
        value=model(preprocess(picture)).detach().cpu().numpy().reshape(-1).astype("float32")
    if len(value)!=EMBED_DIM or not np.isfinite(value).all():
        raise ValueError("Invalid DINOv2 embedding")
    norm=float(np.linalg.norm(value))
    if norm<1e-8:raise ValueError("Zero DINOv2 embedding")
    return value/norm
