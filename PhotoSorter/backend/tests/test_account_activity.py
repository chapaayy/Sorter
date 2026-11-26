"""Regression: disk admission and ownership movement use different inodes."""
import fcntl
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from app import config
from server import database
from server.services import archive_cache
from server.services.account_activity import AccountActivity, lease


def test_model_space_reservation_does_not_block_api(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'APP_STORAGE_ROOT',tmp_path)
    monkeypatch.setattr(database,'DB_URL','')
    monkeypatch.setattr(archive_cache.disk_guard,'stat',lambda *_:(10**12,10**11))
    monkeypatch.setenv('PHOTOSORTER_MIN_FREE_BYTES','0')
    async def models(request):
        return JSONResponse({'models':[]})
    app=AccountActivity(Starlette(routes=[Route('/api/models',models)]))
    # Actual production build_space context, including its exclusive flock.
    # This is the lease held throughout Downloads.install().
    with archive_cache.build_space(tmp_path,4096,kind='model_download'):
        with TestClient(app) as client:
            assert client.get('/api/models').status_code==200
        with lease(exclusive=True) as allowed:
            assert allowed
            with TestClient(app) as client:
                response=client.get('/api/models')
                assert response.status_code==503
                assert 'Передача данных аккаунта' in response.json()['detail']
        with TestClient(app) as client:
            assert client.get('/api/models').status_code==200


def test_api_stream_holds_account_gate_but_not_disk_gate(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'APP_STORAGE_ROOT',tmp_path)
    async def stream(request):
        async def chunks():
            # The response body still owns the account lease.
            with lease(exclusive=True) as allowed:
                assert not allowed
            # An archive build must be able to acquire the distinct disk lock
            # while the API holds its shared account lease. Nonblocking probe
            # makes the old implementation fail instead of hanging this test.
            fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                yield b'first'
                yield b'second'
            finally:os.close(fd)
            with lease(exclusive=True) as allowed:
                assert not allowed
        return StreamingResponse(chunks())
    app=AccountActivity(Starlette(routes=[Route('/api/download/test',stream)]))
    with TestClient(app) as client:
        assert client.get('/api/download/test').content==b'firstsecond'
    with lease(exclusive=True) as allowed:
        assert allowed


def test_shared_account_leases_exclude_move_until_last_reader(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'APP_STORAGE_ROOT',tmp_path)
    with lease() as first:
        assert first
        with lease() as second:
            assert second
            with lease(exclusive=True) as move:
                assert not move
        with lease(exclusive=True) as move:
            assert not move
    with lease(exclusive=True) as move:
        assert move
        with lease() as reader:
            assert not reader
    with lease() as reader:
        assert reader
