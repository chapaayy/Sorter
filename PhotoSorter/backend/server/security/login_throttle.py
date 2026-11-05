"""Bounded per-user + remote login throttling for the single-API-process deployment.

Never store passwords or client IPs. A restart resets the ephemeral counters.
The guard is *in addition to* existing scrypt + constant-time comparisons.
"""
from __future__ import annotations
import hashlib
import threading
import time
from collections import OrderedDict,deque
from fastapi import HTTPException

WINDOW=10*60
ATTEMPTS=5
MAX_BUCKETS=2048

class LoginThrottle:
    def __init__(self,clock=time.monotonic):
        self.clock=clock
        self._lock=threading.Lock()
        self._failed=OrderedDict()
    def _keys(self,username,client):
        username=str(username).casefold()[:64]
        remote=str(client or "unknown")[:128]
        # Limit both per client and account to thwart rotating usernames from one IP.
        return (hashlib.sha256(("user:"+username).encode()).digest(),
                hashlib.sha256(("client:"+remote).encode()).digest())
    def check(self,username,client):
        now=self.clock()
        with self._lock:
            for key in self._keys(username,client):
                stamps=self._failed.get(key)
                if stamps:
                    while stamps and now-stamps[0]>=WINDOW:stamps.popleft()
                    if len(stamps)>=ATTEMPTS:
                        raise HTTPException(429,"Слишком много попыток входа. Повторите позже.")
    def fail(self,username,client):
        now=self.clock()
        with self._lock:
            for key in self._keys(username,client):
                stamps=self._failed.setdefault(key,deque())
                while stamps and now-stamps[0]>=WINDOW:stamps.popleft()
                stamps.append(now)
                self._failed.move_to_end(key)
            while len(self._failed)>MAX_BUCKETS:self._failed.popitem(last=False)
    def succeed(self,username,client):
        with self._lock:
            # Do not allow resetting per-client attempts on success to another account.
            self._failed.pop(self._keys(username,client)[0],None)

limiter=LoginThrottle()
