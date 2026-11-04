"""Original LAB 3.7 normalized feature math (unchanged)."""
import numpy as np

def l2(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(x)
    return x / norm if norm > 1e-12 else x
