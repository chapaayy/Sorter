"""Verified, pinned official XFeat sources and weights; no network in inference."""
from __future__ import annotations
import hashlib
import importlib
import os
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen
from app.config import WEIGHTS_DIR, MODEL_CACHE_DIR

REVISION = "e92685f57f8318b18725c5c8c0bd28c7fe188d9a"
# Official verlab/accelerated_features Git blob OIDs, including the pretrained
# model. Checking the Git blob digest prevents silent corruption and wrong weights.
BLOBS = {
    "weights/xfeat.pt": ("9da942e9c7406b8add3746bf98d4b1840233cd92", 6247949),
    "modules/xfeat.py": ("ce6c512d10d1e060e2264ba71725f81a3d31f0d4", 13472),
    "modules/model.py": ("57539fd35f881348b6bf9887738c7b56a6cbea4f", 4542),
    "modules/interpolator.py": ("699c1b88ffff56ccf364480282adeca8bc732a2a", 1175),
}
MODEL_ID = hashlib.sha256(("official-xfeat-sparse-v1:" + REVISION +
                           ":max1280-top4096-mask-border-v2").encode()).hexdigest()
BASE = "https://raw.githubusercontent.com/verlab/accelerated_features/" + REVISION + "/"

def destination(relative: str) -> Path:
    if relative.startswith("weights/"):
        return WEIGHTS_DIR / "xfeat" / Path(relative).name
    return MODEL_CACHE_DIR / "xfeat" / "official" / relative

def git_digest(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def check_file(relative: str) -> bool:
    path=destination(relative)
    expected,size=BLOBS[relative]
    if not path.is_file() or path.is_symlink() or path.stat().st_size!=size:
        return False
    return git_digest(path.read_bytes())==expected

def status() -> dict:
    return {"available":all(check_file(name) for name in BLOBS),
            "revision":REVISION,"model_signature":MODEL_ID,
            "files":{name:check_file(name) for name in BLOBS}}

def install() -> dict:
    """Explicit command; works from manual copied files when offline."""
    for relative,(expected,size) in BLOBS.items():
        if check_file(relative):
            continue
        target=destination(relative)
        target.parent.mkdir(parents=True,exist_ok=True)
        # Bounded download, never load a model from an unchecked remote object.
        with urlopen(BASE + relative,timeout=40) as response:
            data=response.read(size+1)
        if len(data)!=size or git_digest(data)!=expected:
            raise RuntimeError("Неверная контрольная сумма официального XFeat: "+relative)
        fd,name=tempfile.mkstemp(prefix=".xfeat.",dir=target.parent)
        try:
            with os.fdopen(fd,"wb") as output: output.write(data)
            os.replace(name,target)
        finally:
            Path(name).unlink(missing_ok=True)
    return status()

def load_model():
    """Use original upstream inference, explicitly held on CPU."""
    bad=[name for name in BLOBS if not check_file(name)]
    if bad:
        raise RuntimeError("XFeat не установлен или повреждён: "+", ".join(bad)+
                           ". Выполните python -m app.screen_detection.cli --install")
    import torch
    root=(MODEL_CACHE_DIR/"xfeat"/"official").resolve()
    if str(root) not in sys.path:sys.path.insert(0,str(root))
    official=importlib.import_module("modules.xfeat")
    network=official.XFeat(weights=None,top_k=4096,detection_threshold=.05)
    weights=torch.load(destination("weights/xfeat.pt"),map_location="cpu",weights_only=True)
    network.net.load_state_dict(weights,strict=True)
    network.net.to("cpu").eval()
    network.dev=torch.device("cpu")
    return network
