"""Owner-checked thumbnail garbage collection, invoked by the cleanup worker."""
from .thumbnails import gc_unowned
def collect(limit=20):
    return gc_unowned(limit=limit)
