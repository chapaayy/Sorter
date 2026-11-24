"""Owner-checked preview cache cleanup; scratch recovery is centralized."""
from .thumbnails import gc_unowned

def collect(limit=20):
    return gc_unowned(limit=limit)
