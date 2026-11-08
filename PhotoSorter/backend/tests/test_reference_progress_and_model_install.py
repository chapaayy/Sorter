"""Progress streams per photo; installers are fixed and never block API threads."""
from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import pytest
from fastapi import HTTPException
from app.system import downloads as downloader
from server.api.routes import models
from server import reference_cache


@contextmanager
def fake_database():
    class Database:
        def execute(self,*args,**kwargs):
            return None
    yield Database()


def test_reference_embeddings_stream_before_final_batch(tmp_path,monkeypatch):
    root=tmp_path/"reference_staging"
    root.mkdir()
    photos=[root/("fo"+str(i)+".jpg") for i in range(3)]
    for index,p in enumerate(photos):p.write_bytes(bytes([index])*200)
    monkeypatch.setattr(reference_cache,"REFERENCE_ROOT",root)
    monkeypatch.setattr(reference_cache,"CACHE_DIR",tmp_path/"cache")
    (tmp_path/"cache").mkdir()
    monkeypatch.setattr(reference_cache,"connect",fake_database)
    monkeypatch.setattr(reference_cache,"cached_feature",lambda *args:None)
    events=[]
    class Engine:
        def extract_many(self,paths,stop=None):
            for index,path in enumerate(paths):
                events.append("inferred-"+path.name)
                yield path,np.asarray([index+1,0],dtype="float32"),None
    cache=reference_cache.ReferenceCachedMegaLoc.__new__(
        reference_cache.ReferenceCachedMegaLoc)
    cache.engine=Engine()
    cache.fingerprint="a"*64
    generator=cache.extract_many(photos)
    first=next(generator)
    assert first[0]==photos[0]
    assert events==["inferred-fo0.jpg"]  # not held until all 3 are finished
    assert [item[0] for item in generator]==photos[1:]
    assert len(list((tmp_path/"cache").glob("*.npy")))==3


def test_model_catalog_has_all_four_and_real_statuses(monkeypatch):
    monkeypatch.setattr(models,"files_present",lambda:True)
    monkeypatch.setattr(models,"optional_available",
                        lambda name:name=="xfeat")
    result=models.model_info()
    assert [item["id"] for item in result["models"]]==[
        "megaloc","xfeat","dinov2","paddleocr"]
    assert [item["available"] for item in result["models"]]==[
        True,True,False,False]
    assert result["device"]=="cpu"


def test_download_route_uses_fixed_model_id_and_does_not_require_ssh(monkeypatch):
    monkeypatch.setattr(models,"connect",fake_database)
    called=[]
    monkeypatch.setattr(models.downloads,"start",
                        lambda name:called.append(name) or {"status":"downloading"})
    assert models.download_model("xfeat")=={"status":"downloading"}
    assert called==["xfeat"]
    with pytest.raises(HTTPException) as err:
        models.download_model("not-a-model")
    assert err.value.status_code==404


def test_optional_installer_serializes_and_verifies_success(tmp_path,monkeypatch):
    monkeypatch.setattr(downloader,"LOG_DIR",tmp_path)
    monkeypatch.setattr(downloader,"optional_size",lambda name:0)
    checks=iter([False,True])
    monkeypatch.setattr(downloader,"optional_available",lambda name:next(checks))
    commands=[]
    class Process:
        def poll(self):return 0
        def wait(self):return 0
        def terminate(self):raise AssertionError("Installer succeeded")
    monkeypatch.setattr(downloader.subprocess,"Popen",
                        lambda command,**kwargs:commands.append(command) or Process())
    class Immediate:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):self.target()
    monkeypatch.setattr(downloader.threading,"Thread",Immediate)
    manager=downloader.Downloads()
    state=manager.start("dinov2")
    assert state["status"]=="installed"
    assert commands==[[downloader.sys.executable,"-m",
                       "app.ad_recognition.cli","--install-dino"]]
    assert manager.active is False


def test_optional_installer_failure_is_reported_and_can_be_retried(tmp_path,monkeypatch):
    monkeypatch.setattr(downloader,"LOG_DIR",tmp_path)
    monkeypatch.setattr(downloader,"optional_size",lambda name:0)
    class Process:
        def poll(self):return 1
        def wait(self):return 1
        def terminate(self):pass
    monkeypatch.setattr(downloader.subprocess,"Popen",
                        lambda command,**kwargs:Process())
    manager=downloader.Downloads()
    manager._run_optional("paddleocr")
    state=manager.status()["paddleocr"]
    assert state["status"]=="error"
    assert manager.active is False
