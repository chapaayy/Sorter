"""Owner-scoped, versioned thumbnail keys using the shared storage contract."""
from pathlib import Path
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_path,managed_prefix,digest_key,user_key
from .paths import owned_file

VERSION=1
MAX_SIDE=480
QUALITY=78
PIXEL_LIMIT=30_000_000

def location(checksum:str,version:int=VERSION,*,owner_id=None)->Path:
    digest=digest_key(checksum)
    if version!=VERSION:raise ValueError("Invalid thumbnail version")
    if owner_id is None:
        return managed_path(Category.REFERENCE_THUMBNAIL,version=version,prefix=digest[:2],hash=digest)
    return managed_path(Category.FO_THUMBNAIL,user_id=owner_id,version=version,prefix=digest[:2],hash=digest)

def safe_location(path:Path)->Path:
    return owned_file(path,config.APP_STORAGE_ROOT)

def roots():
    """Yield (owner, version directory); no SAM/filename-derived paths."""
    yield None,managed_prefix(Category.REFERENCE_THUMBNAIL,version=VERSION)
    users=managed_prefix(Category.FO_THUMBNAIL)
    if not users.is_dir() or users.is_symlink():return
    for item in users.iterdir():
        if item.is_symlink() or not item.is_dir():continue
        try:owner=user_key(item.name)
        except ValueError:continue
        yield int(owner),managed_prefix(Category.FO_THUMBNAIL,user_id=owner,version=VERSION)
