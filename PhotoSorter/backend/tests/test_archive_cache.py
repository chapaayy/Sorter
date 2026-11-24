"""Expiry, safe deletion, concurrent transfers, disk admission."""
import os
import time
import zipfile
from fastapi import HTTPException
import pytest
from server.services import archive_cache,archives
from server.api.file_response import LeasedFileResponse

def test_expiry_does_not_remove_pinned_archive_or_other_files(tmp_path):
    folder=tmp_path/".archives"
    folder.mkdir()
    archive=folder/("a"*12+"-"+"b"*20+".zip")
    lock=archive.with_suffix(".lock")
    fragment=folder/".archive-dead.tmp"
    unknown=folder/"do-not-remove.zip"
    fresh=folder/("c"*12+"-"+"d"*20+".zip")
    for path in (archive,lock,fragment,unknown,fresh):
        path.write_bytes(b"data")
    symlink=folder/("e"*12+"-"+"f"*20+".zip")
    symlink.symlink_to(unknown)
    now=time.time()
    for path in (archive,lock,fragment,unknown):
        os.utime(path,(now-3700,)*2)
    with archive_cache.pin(folder):
        assert archive_cache.sweep_folder(folder,now=now)==0
        assert archive.exists()
    assert archive_cache.sweep_folder(folder,now=now)>=2
    archive_cache.sweep_folder(folder,now=now)
    assert not archive.exists() and not fragment.exists() and not lock.exists()
    assert fresh.exists() and unknown.exists() and symlink.is_symlink()

def test_reference_zip_expiry_and_active_transfer(tmp_path):
    folder=tmp_path/"reference_exports"
    folder.mkdir()
    target=folder/("a"*64+".zip")
    target.write_bytes(b"ZIP")
    now=time.time()
    os.utime(target,(now-3601,)*2)
    with archive_cache.pin(folder):
        assert archive_cache.sweep_folder(folder,reference=True,now=now)==0
    assert archive_cache.sweep_folder(folder,reference=True,now=now)==1

def test_response_pin_released_on_range_error(tmp_path):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    target=tmp_path/("a"*64+".zip")
    target.write_bytes(b"123456789")
    old=time.time()-3700
    os.utime(target,(old,old))
    def download(request):
        pin=archive_cache.pin(tmp_path)
        assert archive_cache.sweep_folder(tmp_path,reference=True)==0
        return LeasedFileResponse(target,archive_pin=pin)
    with TestClient(Starlette(routes=[Route("/zip",download)])) as client:
        assert client.get("/zip",headers={"Range":"bytes=100-200"}).status_code==416
    assert archive_cache.sweep_folder(tmp_path,reference=True)==1

def test_low_disk_space_rejects_zip_without_partial_file(tmp_path,monkeypatch):
    from .test_archives import mock_run_storage
    mock_run_storage(tmp_path,monkeypatch)
    monkeypatch.setattr(archive_cache.disk_guard,"stat",lambda _: (1000000000,1))
    run="20261107T120000-abcdef123456"
    source=archives.storage_paths.result_media_dir(run)/"one.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"test")
    with pytest.raises(HTTPException) as e:
        archives.prepare(run,None,[(source,"SAM/one.jpg")])
    assert e.value.status_code==507
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.tmp"))
