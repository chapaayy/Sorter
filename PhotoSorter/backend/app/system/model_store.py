"""Official MegaLoc assets in new layout, with read-only legacy compatibility.

New downloads live under Models/models/megaloc. Existing gigabyte weights
remain usable from Models/megaloc, Torch Hub checkpoints or Hugging Face
snapshots; nothing is moved, deleted, or duplicated automatically.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from ..config import MODELS_DIR, WEIGHTS_DIR, MODEL_CACHE_DIR, DATA_DIR

REPO = 'gberton/MegaLoc'
SOURCE_FOLDER = 'gmberton_MegaLoc_main'
WEIGHT_NAME = 'model.safetensors'
MINIMUM_SIZE = 50_000_000
VERIFICATIONS = MODEL_CACHE_DIR / 'downloads' / 'verified_megaloc.json'
LEGACY_VERIFICATIONS = MODEL_CACHE_DIR / 'downloads' / 'verified_hub.json'

def unique(paths):
    result, seen = [], set()
    for path in paths:
        value = Path(path).expanduser()
        key = os.path.normcase(os.path.abspath(value))
        if key not in seen:
            seen.add(key);result.append(value)
    return result

def torch_roots():
    roots = [MODEL_CACHE_DIR / 'torch' / 'hub', DATA_DIR / 'torch' / 'hub']
    if os.environ.get('TORCH_HOME'):
        roots.insert(0, Path(os.environ['TORCH_HOME']) / 'hub')
    if os.environ.get('PHOTOSORTER_LEGACY_DATA'):
        roots.append(Path(os.environ['PHOTOSORTER_LEGACY_DATA']) / 'torch' / 'hub')
    roots.append(Path.home() / '.cache' / 'torch' / 'hub')
    return unique(roots)

def hf_roots():
    roots = []
    if os.environ.get('HF_HUB_CACHE'): roots.append(os.environ['HF_HUB_CACHE'])
    if os.environ.get('HF_HOME'): roots.append(Path(os.environ['HF_HOME']) / 'hub')
    roots += [MODEL_CACHE_DIR / 'huggingface' / 'hub', Path.home() / '.cache' / 'huggingface' / 'hub']
    return unique(roots)

def configure_model_environment():
    (MODEL_CACHE_DIR / 'torch' / 'hub').mkdir(parents=True,exist_ok=True)
    (MODEL_CACHE_DIR / 'huggingface' / 'hub').mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('TORCH_HOME', str(MODEL_CACHE_DIR / 'torch'))
    os.environ.setdefault('HF_HUB_CACHE', str(MODEL_CACHE_DIR / 'huggingface' / 'hub'))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'

def repo_folder():
    for root in torch_roots():
        folder = root / SOURCE_FOLDER
        if all((folder / file).is_file() for file in ('hubconf.py','megaloc_model.py')):
            return folder
    return MODEL_CACHE_DIR / 'torch' / 'hub' / SOURCE_FOLDER

def checkpoint():
    # Prefer stable new weight location; legacy paths remain read-only.
    candidates = [WEIGHTS_DIR / 'megaloc' / WEIGHT_NAME, MODELS_DIR / 'megaloc' / WEIGHT_NAME]
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

def signature():
    weight = checkpoint()
    if weight is None or not files_present(): return None
    repo = repo_folder()
    stat = weight.stat()
    hasher = hashlib.sha256()
    for source in sorted(repo.rglob('*.py')):
        hasher.update(source.relative_to(repo).as_posix().encode())
        hasher.update(source.read_bytes())
    return hashlib.sha256(f'megaloc:{weight.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{hasher.hexdigest()}:loader-v2'.encode()).hexdigest()

def verified():
    sig = signature()
    if not sig:return False
    for location in (VERIFICATIONS, LEGACY_VERIFICATIONS):
        try:
            data = json.loads(location.read_text('utf8'))
            if data.get('megaloc') == sig:return True
        except (OSError, ValueError, TypeError):pass
    return False

def remember_verified():
    sig = signature()
    if not sig:raise RuntimeError('Веса и исходники MegaLoc не обнаружены')
    VERIFICATIONS.parent.mkdir(parents=True,exist_ok=True)
    tmp = VERIFICATIONS.with_suffix('.tmp')
    tmp.write_text(json.dumps({'megaloc':sig},indent=2),encoding='utf8')
    tmp.replace(VERIFICATIONS)
