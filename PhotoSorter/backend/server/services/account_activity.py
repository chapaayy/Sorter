"""Filesystem-inode shared/exclusive gate for account ownership moves.

All API requests hold a shared lease until streaming finishes. The existing
cleanup worker attempts an exclusive lease without waiting. No extra file,
service, or DB connection is created. The app root is a shared bind mount.
"""
import os,fcntl
from contextlib import contextmanager
from app import config
from starlette.responses import JSONResponse

@contextmanager
def lease(*,exclusive=False):
    try:fd=os.open(config.APP_STORAGE_ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    except FileNotFoundError:
        # A clean/test API without a data mount cannot move data.
        yield not exclusive
        return
    try:
        try:fcntl.flock(fd,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:os.close(fd)

class AccountActivity:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope["type"]!="http" or not scope.get("path","").startswith("/api/") or scope.get("path")=="/api/health":
            return await self.app(scope,receive,send)
        with lease() as allowed:
            if not allowed:
                return await JSONResponse({"detail":"Передача данных аккаунта. Повторите запрос."},status_code=503,headers={"Retry-After":"2"})(scope,receive,send)
            return await self.app(scope,receive,send)
