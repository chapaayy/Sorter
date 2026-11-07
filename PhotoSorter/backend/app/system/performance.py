"""Bounded CPU inference settings. No persistent tuning state or photo cache."""
from __future__ import annotations
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class CPUPerformance:
    threads: int
    batch_size: int
    prefetch_workers: int


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, '').strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


_runtime_threads: int | None = None

def set_runtime_threads(value: int) -> None:
    """Worker-owned override, applied when the next MegaLoc engine starts."""
    global _runtime_threads
    allowed = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 4)
    _runtime_threads = max(1, min(32, allowed, value))


def cpu_performance() -> CPUPerformance:
    """Read optional overrides once per engine load; keep sensible conservative limits.

    The CPU-only worker reads server-side thread settings before each FIFO task.
    Batch size and prefetch remain fixed, conservative deployment settings.
    """
    return CPUPerformance(
        threads=_runtime_threads or _bounded_int('PHOTOSORTER_CPU_THREADS', min(8, os.cpu_count() or 4), 1, 32),
        batch_size=_bounded_int('PHOTOSORTER_BATCH_SIZE', 4, 1, 16),
        prefetch_workers=_bounded_int('PHOTOSORTER_PREFETCH_WORKERS', 2, 0, 4),
    )
