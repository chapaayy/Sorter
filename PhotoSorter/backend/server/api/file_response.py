"""Seekable files whose batch must stay alive until the HTTP transfer ends."""
from __future__ import annotations

import time

from anyio import CancelScope
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from ..services import operations


class LeasedFileResponse(FileResponse):
    """Own the operation lease for every FileResponse exit, not just success."""

    def __init__(self, path, *, lease, **kwargs):
        super().__init__(path, **kwargs)
        self.lease = lease

    async def __call__(self, scope, receive, send):
        last_heartbeat = time.monotonic()

        async def send_with_heartbeat(message):
            nonlocal last_heartbeat
            now = time.monotonic()
            if self.lease and now - last_heartbeat >= 5:
                await run_in_threadpool(operations.heartbeat, self.lease)
                last_heartbeat = now
            await send(message)

        try:
            await super().__call__(scope, receive, send_with_heartbeat)
        finally:
            # FileResponse can return early for 400/416 or stop on disconnect.
            # Don't defer the release to its success-only background callback.
            if self.lease:
                with CancelScope(shield=True):
                    await run_in_threadpool(operations.finish, self.lease)
