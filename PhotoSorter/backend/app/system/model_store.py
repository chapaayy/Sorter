"""Pinned official MegaLoc bundle; runtime never falls back to technical cache."""
from __future__ import annotations
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_prefix
from app.storage.filesystem import atomic_write,directory_fd,safe_read

REPO="gberton/MegaLoc"
SOURCE_REVISION="5fe0dd697c4a70ba3e23607f6716ab3c606b16db"
WEIGHT_REVISION="a0f34722c4297ff787e022433799250180860af7"
WEIGHT_NAME="model.safetensors"
WEIGHT_SHA256="d4f9f2bcb60018f91eb6a8e061ed054fd55654e10c2569cf13841ea986ffb4f8"
SOURCE_BLOBS={
    "LICENSE":"24b55f1457a3d08404be5b33dbd99b9dfc64d469",
    "hubconf.py":"7c945bf8c94a24867ffc778ed06665d8d48354c8",
    "megaloc_model.py":"3559bc209f7194d90c6ee3e2350981328af8c743",
}
MAX_WEIGHT_BYTES=1_100_000_000

def repo_folder():
    return managed_prefix(Category.MODEL_SOURCE)/SOURCE_REVISION

def weight_target():
    return managed_prefix(Category.MODEL_WEIGHTS)/WEIGHT_SHA256/WEIGHT_NAME

def verification_path():
    return managed_prefix(Category.MODEL_METADATA)/"current.json"

def metadata():
    return {"format":1,"repo":REPO,"source_revision":SOURCE_REVISION,
            "weight_revision":WEIGHT_REVISION,"weight_sha256":WEIGHT_SHA256,
            "source_blobs":SOURCE_BLOBS}

def configure_model_environment():
    locations={name:managed_prefix(Category.TECHNICAL_CACHE,provider=name) for name in ("torch","huggingface","xdg")}
    # Some tools use HOME directly; point it at the typed XDG cache too.
    for path in locations.values():
        with directory_fd(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT),create=True):pass
    os.environ.update({
        "HOME":str(locations["xdg"]),"XDG_CACHE_HOME":str(locations["xdg"]),
        "TORCH_HOME":str(locations["torch"]),"HF_HOME":str(locations["huggingface"]),
        "HF_HUB_CACHE":str(locations["huggingface"]/"hub"),
        "HF_XET_CACHE":str(locations["huggingface"]/"xet"),
        "HF_HUB_OFFLINE":"1","HF_HUB_DISABLE_TELEMETRY":"1",
    })

@lru_cache(maxsize=8)
def _weight_digest(path,device,inode,size,mtime,ctime):
    with safe_read(config.APP_STORAGE_ROOT,Path(path).relative_to(config.APP_STORAGE_ROOT)) as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def content_digest(path):
    info=path.stat(follow_symlinks=False)
    return _weight_digest(str(path),info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

def verify_source(path):
    for name,expected in SOURCE_BLOBS.items():
        with safe_read(config.APP_STORAGE_ROOT,(path/name).relative_to(config.APP_STORAGE_ROOT)) as stream:
            data=stream.read(1_000_001)
        if len(data)>1_000_000 or hashlib.sha1(f"blob {len(data)}".encode()+bytes([0])+data).hexdigest()!=expected:
            raise ValueError("MegaLoc source integrity failure: "+name)

def verify_bundle(repo,weight):
    verify_source(repo)
    if content_digest(weight)!=WEIGHT_SHA256:
        raise ValueError("MegaLoc weight SHA-256 mismatch")

def files_present():
    try:
        with safe_read(config.APP_STORAGE_ROOT,verification_path().relative_to(config.APP_STORAGE_ROOT)) as stream:
            if json.load(stream)!=metadata():return False
        verify_bundle(repo_folder(),weight_target())
        return True
    except (OSError,ValueError,TypeError):return False

def checkpoint():
    return weight_target() if weight_target().is_file() else None

def signature():
    weight=checkpoint()
    if weight is None or not files_present():return None
    repo=repo_folder()
    digest=content_digest(weight)
    hasher=hashlib.sha256()
    for source in sorted(repo.glob("*.py")):
        hasher.update(source.relative_to(repo).as_posix().encode()+bytes([0]))
        hasher.update(hashlib.sha256(source.read_bytes()).digest())
    app_root=Path(__file__).resolve().parents[1]
    for rel in ("recognition/engines/megaloc/loader.py","recognition/engines/megaloc/extractor.py","photos/reader.py"):
        hasher.update(rel.encode()+bytes([0]))
        hasher.update(hashlib.sha256((app_root/rel).read_bytes()).digest())
    return hashlib.sha256(f"megaloc:{digest}:{hasher.hexdigest()}:loader-v2".encode()).hexdigest()

def verified():return files_present()

def remember_verified(*,already_reserved=False):
    verify_bundle(repo_folder(),weight_target())
    raw=json.dumps(metadata(),sort_keys=True).encode("utf8")
    with atomic_write(config.APP_STORAGE_ROOT,verification_path().relative_to(config.APP_STORAGE_ROOT),expected_size=None if already_reserved else len(raw)) as stream:
        stream.write(raw)
