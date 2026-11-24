"""Single application root; explicit injection for tests and host bootstrap."""
import os
from dataclasses import dataclass
from pathlib import Path
from .categories import CONTAINER_APP_ROOT

PROJECT_ROOT = Path(__file__).resolve().parents[4]

def absolute_root(value):
    p = Path(value)
    if not p.is_absolute() or ".." in p.parts or p == Path("/"):
        raise ValueError("Storage root must be a non-root absolute path")
    if p.resolve() != p:
        raise ValueError("Storage root must not contain symlinks")
    return p

@dataclass(frozen=True)
class StorageConfig:
    app_root: Path

    def __post_init__(self):
        object.__setattr__(self, "app_root", absolute_root(self.app_root))

    @classmethod
    def from_environment(cls):
        return cls(Path(os.environ.get("MAP_APP_STORAGE_ROOT", PROJECT_ROOT / "storage/app")))

    @property
    def data(self):
        # Transitional internal routing for existing producers, replaced in stages 3–6.
        return self.app_root / "state"

    @property
    def models(self):
        return self.app_root / "models"

    @property
    def model_cache(self):
        return self.app_root / "cache"

    def ensure_dirs(self):
        for folder in (self.data, self.data / "runs", self.models / "megaloc",
                       self.model_cache, self.app_root / "users",
                       self.app_root / "shared/references", self.app_root / "temporary"):
            if folder.resolve() != folder:
                raise ValueError("Symlinked storage directory")
            folder.mkdir(parents=True, exist_ok=True)
