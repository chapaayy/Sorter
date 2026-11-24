"""Shared activity lease; only the host can enter maintenance."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from starlette.responses import JSONResponse

CONTROL=Path("/run/map-updater")
EXEMPT=frozenset(("/api/health","/api/system/update","/api/system/update/check",
                  "/api/system/update/start","/api/auth/me"))

@contextmanager
def activity():
    lock=CONTROL/"activity.lock"
    marker=CONTROL/"maintenance"
    if not lock.is_file():
        # Direct development/CI Compose without host updater.
        yield not marker.exists()
        return
    fd=os.open(lock,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        if marker.exists():
            yield False
            return
        try:
            fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield not marker.exists()
    finally:
        os.close(fd)

class UpdateGate:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        path=scope.get("path","")
        if scope["type"]!="http" or not path.startswith("/api/") or path in EXEMPT:
            await self.app(scope,receive,send)
            return
        # Pure ASGI: retain the lease until streaming responses finish.
        with activity() as allowed:
            if not allowed:
                await JSONResponse({"detail":"MAP обновляется. Повторите после завершения."},
                                   status_code=503,headers={"Retry-After":"30"})(scope,receive,send)
                return
            await self.app(scope,receive,send)
