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


def cpu_performance() -> CPUPerformance:
    """Read optional overrides once per engine load; keep sensible conservative limits.

    Batch size 1, prefetch workers 0 matches original single-image inference.
    For benchmarking, set PHOTOSORTER_CPU_THREADS/BATCH_SIZE/PREFETCH_WORKERS
    before starting the application; no settings UI is introduced.
    """
    return CPUPerformance(
        threads=_bounded_int('PHOTOSORTER_CPU_THREADS', min(8, os.cpu_count() or 4), 1, 32),
        batch_size=_bounded_int('PHOTOSORTER_BATCH_SIZE', 4, 1, 16),
        prefetch_workers=_bounded_int('PHOTOSORTER_PREFETCH_WORKERS', 2, 0, 4),
    )
