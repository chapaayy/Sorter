"""Pin the single CPU worker to N permitted CPUs before each FIFO task.

The worker container has its own cpuset. System services remain unrestricted;
unused cores are always available to them. We never modify Docker from API.
"""
from __future__ import annotations
import os
from pathlib import Path

# Original cgroup-allowed CPUs, captured before per-job affinity is changed.
_ORIGINAL:tuple[int,...]|None=None


def allocate(count:int)->tuple[int,...]:
    global _ORIGINAL
    if not hasattr(os,'sched_setaffinity') or not hasattr(os,'sched_getaffinity'):
        return ()
    if _ORIGINAL is None:
        _ORIGINAL=tuple(sorted(os.sched_getaffinity(0)))
    chosen=set(_ORIGINAL[:max(1,min(len(_ORIGINAL),int(count)))])
    # Already-existing OpenMP threads may not inherit the new main-thread mask.
    # Pin all currently existing threads; new ones inherit affinity at creation.
    try:
        tids=[int(item.name) for item in Path('/proc/self/task').iterdir() if item.name.isdigit()]
    except OSError:
        tids=[0]
    for tid in tids:
        try:
            os.sched_setaffinity(tid,chosen)
        except ProcessLookupError:
            continue
    return tuple(sorted(chosen))
