"""Minimal feature engine contract for a future additional model."""
from pathlib import Path
from typing import Protocol
import numpy as np

class Engine(Protocol):
    name: str
    device: str
    def extract(self, path: Path) -> np.ndarray: ...
    def unload(self) -> None: ...
