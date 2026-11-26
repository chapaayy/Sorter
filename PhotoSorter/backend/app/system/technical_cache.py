"""Offline maintenance only; remove precisely the three typed provider caches."""
from contextlib import contextmanager
import fcntl
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_prefix
from app.storage.filesystem import directory_fd,safe_remove_tree

PROVIDERS=("torch","huggingface","xdg")

@contextmanager
def runtime_guard(*,exclusive=False):
    root=config.APP_STORAGE_ROOT
    path=managed_prefix(Category.TECHNICAL_CACHE,provider="torch").parent
    with directory_fd(root,path.relative_to(root),create=True) as fd:
        flags=fcntl.LOCK_EX|fcntl.LOCK_NB if exclusive else fcntl.LOCK_SH
        try:fcntl.flock(fd,flags)
        except BlockingIOError:raise RuntimeError("Stop all MAP application processes before technical cache cleanup")
        yield fd

def clear_disposable():
    """Explicit offline maintenance. Not a TTL, not a background cleanup."""
    from .model_store import verified
    root=config.APP_STORAGE_ROOT
    with runtime_guard(exclusive=True):
        if not verified():raise RuntimeError("No verified independent MegaLoc bundle; cache cleanup refused")
        for provider in PROVIDERS:
            folder=managed_prefix(Category.TECHNICAL_CACHE,provider=provider)
            safe_remove_tree(root,folder.relative_to(root),missing_ok=True)
        return PROVIDERS
