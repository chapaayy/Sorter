"""CPU-only model threads are one persistent setting, bounded by Worker CPU allocation."""
from fastapi import HTTPException
import pytest
from server.database import connect
from server.services import compute_settings
from .test_unified_queue_stage3 import system

def test_cpu_preference_is_persisted_and_limited_by_worker_quota(system,monkeypatch):
    monkeypatch.setattr(compute_settings.os,"cpu_count",lambda:8)
    monkeypatch.setenv("PHOTOSORTER_WORKER_CPUS","4")
    monkeypatch.setenv("PHOTOSORTER_WORKER_CPUSET","0-3")
    assert compute_settings.read()["max_threads"]==4
    assert compute_settings.update(3)["threads"]==3
    with connect() as db:
        assert compute_settings.for_worker(db)==3
    with pytest.raises(HTTPException) as err:
        compute_settings.update(5)
    assert err.value.status_code==422
    assert compute_settings.read()["threads"]==3

def test_cpu_preference_never_exceeds_one_allowed_cpu(system,monkeypatch):
    monkeypatch.setattr(compute_settings.os,"cpu_count",lambda:8)
    monkeypatch.setenv("PHOTOSORTER_WORKER_CPUS","1")
    monkeypatch.setenv("PHOTOSORTER_WORKER_CPUSET","3")
    assert compute_settings.read()["max_threads"]==1
    assert compute_settings.update(1)["threads"]==1
