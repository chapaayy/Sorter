"""Single application root; explicit injection for tests and host bootstrap."""
import os
from dataclasses import dataclass
from pathlib import Path
from .categories import FOUNDATION_PATHS, APP_BOOTSTRAP_DIRS
from .filesystem import directory_fd

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
        return self.app_root / FOUNDATION_PATHS["data"].removeprefix("app/")

    @property
    def models(self):
        return self.app_root / FOUNDATION_PATHS["models"].removeprefix("app/")

    @property
    def model_cache(self):
        return self.app_root / FOUNDATION_PATHS["model_cache"].removeprefix("app/")

    def ensure_dirs(self):
        self.app_root.mkdir(parents=True, exist_ok=True)
        for key in APP_BOOTSTRAP_DIRS:
            with directory_fd(self.app_root, key, create=True):
                pass
