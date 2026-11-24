"""MegaLoc assets under the configured app storage root; no legacy host fallbacks."""
from __future__ import annotations
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from ..config import WEIGHTS_DIR, MODEL_CACHE_DIR
from ..storage.filesystem import atomic_write

REPO = 'gberton/MegaLoc'
SOURCE_FOLDER = 'gmberton_MegaLoc_main'
WEIGHT_NAME = 'model.safetensors'
MINIMUM_SIZE = 50_000_000
VERIFICATIONS = MODEL_CACHE_DIR / 'downloads' / 'verified_megaloc.json'

def torch_roots():
    return [MODEL_CACHE_DIR / 'torch' / 'hub']

def hf_roots():
    return [MODEL_CACHE_DIR / 'huggingface' / 'hub']

def configure_model_environment():
    (MODEL_CACHE_DIR / 'torch' / 'hub').mkdir(parents=True,exist_ok=True)
    (MODEL_CACHE_DIR / 'huggingface' / 'hub').mkdir(parents=True,exist_ok=True)
    os.environ.update({
        'HOME':str(MODEL_CACHE_DIR),
        'XDG_CACHE_HOME':str(MODEL_CACHE_DIR/'xdg'),
        'TORCH_HOME':str(MODEL_CACHE_DIR/'torch'),
        'HF_HOME':str(MODEL_CACHE_DIR/'huggingface'),
        'HF_HUB_CACHE':str(MODEL_CACHE_DIR/'huggingface'/'hub'),
        'HF_XET_CACHE':str(MODEL_CACHE_DIR/'huggingface'/'xet'),
        'HF_HUB_OFFLINE':'1',
        'HF_HUB_DISABLE_TELEMETRY':'1',
    })

def repo_folder():
    for root in torch_roots():
        folder = root / SOURCE_FOLDER
        if all((folder / file).is_file() for file in ('hubconf.py','megaloc_model.py')):
            return folder
    return MODEL_CACHE_DIR / 'torch' / 'hub' / SOURCE_FOLDER

def checkpoint():
    # Current managed weights and cache only; offline source separation is stage 5.
    candidates = [WEIGHTS_DIR / 'megaloc' / WEIGHT_NAME]
    candidates += [root / 'checkpoints' / WEIGHT_NAME for root in torch_roots()]
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size >= MINIMUM_SIZE:
            return candidate
    for root in hf_roots():
        snapshots = root / 'models--gberton--MegaLoc' / 'snapshots'
        if snapshots.is_dir():
            for folder in sorted(snapshots.iterdir()):
                candidate = folder / WEIGHT_NAME
                if candidate.is_file() and candidate.stat().st_size >= MINIMUM_SIZE:
                    return candidate
    return None

def files_present():
    folder = repo_folder()
    return bool(checkpoint() and (folder / 'hubconf.py').is_file() and (folder / 'megaloc_model.py').is_file())

@lru_cache(maxsize=8)
def _weight_digest(path,device,inode,size,mtime,ctime):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def signature():
    weight=checkpoint()
    if weight is None or not files_present():return None
    repo=repo_folder()
    info=weight.stat()
    digest=_weight_digest(str(weight),info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    hasher=hashlib.sha256()
    for source in sorted(repo.rglob('*.py')):
        hasher.update(source.relative_to(repo).as_posix().encode()+b"\0")
        hasher.update(hashlib.sha256(source.read_bytes()).digest())
    app_root=Path(__file__).resolve().parents[1]
    for rel in ('recognition/engines/megaloc/loader.py','recognition/engines/megaloc/extractor.py','photos/reader.py'):
        hasher.update(rel.encode()+b"\0")
        hasher.update(hashlib.sha256((app_root/rel).read_bytes()).digest())
    # Content identity independent of cache location, rename or unchanged redeploy.
    return hashlib.sha256(f'megaloc:{digest}:{hasher.hexdigest()}:loader-v2'.encode()).hexdigest()

def verified():
    sig = signature()
    if not sig:return False
    for location in (VERIFICATIONS,):
        try:
            data = json.loads(location.read_text('utf8'))
            if data.get('megaloc') == sig:return True
        except (OSError, ValueError, TypeError):pass
    return False

def remember_verified():
    sig = signature()
    if not sig:raise RuntimeError('Веса и исходники MegaLoc не обнаружены')
    with atomic_write(MODEL_CACHE_DIR, VERIFICATIONS.relative_to(MODEL_CACHE_DIR)) as stream:
        stream.write(json.dumps({'megaloc':sig},indent=2).encode('utf8'))
