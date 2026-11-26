"""Kernel gate for account ownership changes, independent of disk admission.

The root of the personal-data namespace is a stable, bootstrapped directory.
Use its inode, NOT APP_STORAGE_ROOT: archive_cache.build_space holds an
exclusive flock on the app root for ZIP builds and MegaLoc installation.
No lock files or additional storage categories are needed.
"""
import fcntl
from contextlib import contextmanager, ExitStack
from app import config
from app.storage.categories import Category
from app.storage.paths import category_prefix
from app.storage.filesystem import directory_fd
from starlette.responses import JSONResponse


@contextmanager
def lease(*, exclusive=False):
    # Every API process and the cleanup/thumbnail workers share this mount.
    # Bootstrap already creates users/; lazily ensure it for test/dev roots.
    # Never remove this namespace root, even when the last account is deleted.
    with ExitStack() as stack:
        try:
            fd = stack.enter_context(directory_fd(
                config.APP_STORAGE_ROOT, category_prefix(Category.FO_ORIGINAL),
                create=True))
        except FileNotFoundError:
            # Preserve the clean/test API without a data mount; it cannot move.
            yield not exclusive
            return
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


class AccountActivity:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope["type"]!="http" or not scope.get("path","").startswith("/api/") or scope.get("path")=="/api/health":
            return await self.app(scope,receive,send)
        with lease() as allowed:
            if not allowed:
                return await JSONResponse({"detail":"Передача данных аккаунта. Повторите запрос."},status_code=503,headers={"Retry-After":"2"})(scope,receive,send)
            return await self.app(scope,receive,send)
