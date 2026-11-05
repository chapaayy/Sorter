"""Owner-checked preview cache cleanup and stale staging fragments."""
from .thumbnails import gc_unowned,gc_incomplete

def collect(limit=20):
    return gc_unowned(limit=limit)+gc_incomplete(limit=limit)
