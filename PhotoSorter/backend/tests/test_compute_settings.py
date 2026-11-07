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


def test_cpu_budget_is_shared_by_fo_and_reference_fifo(system,monkeypatch):
    monkeypatch.setattr(compute_settings,"available_cpu_count",lambda:8)
    monkeypatch.setattr(compute_settings,"max_threads",lambda:7)
    budget=compute_settings.update_budget(6)
    assert (budget["total_cpus"],budget["model_cpus"],budget["system_cpus"])==(8,6,2)
    assert budget["max_model_cpus"]==7
    with connect() as db:
        assert compute_settings.for_worker(db,"fo_processing")==6
        assert compute_settings.for_worker(db,"reference_preparation")==6
    with pytest.raises(HTTPException) as invalid:
        compute_settings.update_budget(8)
    assert invalid.value.status_code==422
    assert compute_settings.workload_settings()["model_cpus"]==6


def test_worker_cpu_affinity_restricts_existing_threads(monkeypatch):
    from server.services import worker_cpu_affinity
    monkeypatch.setattr(worker_cpu_affinity,"_ORIGINAL",None)
    monkeypatch.setattr(worker_cpu_affinity.os,"sched_getaffinity",lambda tid:{0,1,2,3},raising=False)
    seen=[]
    monkeypatch.setattr(worker_cpu_affinity.os,"sched_setaffinity",lambda tid,cpus:seen.append((tid,set(cpus))),raising=False)
    assert worker_cpu_affinity.allocate(2)==(0,1)
    assert seen and all(affinity=={0,1} for _,affinity in seen)
    assert worker_cpu_affinity.allocate(3)==(0,1,2)
