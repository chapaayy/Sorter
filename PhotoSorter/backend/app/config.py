"""Application configuration facade; all data under the single app root."""
from pathlib import Path
from .storage.config import StorageConfig

PROJECT_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = PROJECT_DIR.parent
STORAGE = StorageConfig.from_environment()
APP_STORAGE_ROOT = STORAGE.app_root
MODELS_DIR = STORAGE.models
WEIGHTS_DIR = MODELS_DIR
MODEL_CACHE_DIR = STORAGE.model_cache
DATA_DIR = STORAGE.data
RUNS_DIR = DATA_DIR / "runs"

def ensure_dirs():
    STORAGE.ensure_dirs()
