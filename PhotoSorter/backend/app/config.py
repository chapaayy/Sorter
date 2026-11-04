"""Portable paths: weights are independent from the application."""
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = PROJECT_DIR.parent
MODELS_DIR = ROOT_DIR / 'Models'
WEIGHTS_DIR = MODELS_DIR / 'models'
MODEL_CACHE_DIR = MODELS_DIR / 'cache'
DATA_DIR = PROJECT_DIR / 'data'
RUNS_DIR = DATA_DIR / 'runs'

def ensure_dirs() -> None:
    for folder in (MODELS_DIR, WEIGHTS_DIR, WEIGHTS_DIR / 'megaloc', MODEL_CACHE_DIR, DATA_DIR, RUNS_DIR):
        folder.mkdir(parents=True, exist_ok=True)
