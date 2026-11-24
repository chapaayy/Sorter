"""Neutral, optional storage publication notification. No dependency on DB/API.
The installed server sink coalesces durable dirty keys, not individual syscalls.
The periodic reconciler is the recovery path if a process dies before notification.
"""
import logging
from pathlib import Path
_sink=None

def install_sink(callback):
    global _sink
    _sink=callback

def changed(*paths,subtree=False):
    if _sink is None:return
    try:_sink(tuple(Path(p) for p in paths),subtree=subtree)
    except Exception:
        # Accounting must not roll back an already published business file.
        logging.getLogger(__name__).warning("Storage notification failed; reconciliation required")
