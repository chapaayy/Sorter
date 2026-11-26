"""Cached ZIP is deterministic and seekable; invalid paths cannot escape outputs."""
import zipfile
from pathlib import Path
import pytest
from fastapi import HTTPException
from server.services import archives

def mock_run_storage(tmp_path,monkeypatch):
    from app import config
    import uuid
    batch=uuid.uuid4()
    monkeypatch.setattr(config,"APP_STORAGE_ROOT",tmp_path)
    monkeypatch.setattr(archives.storage_paths,"run_identity",lambda run_id,db=None:(batch,1))

def test_cached_archive_is_reused(tmp_path,monkeypatch):
    mock_run_storage(tmp_path,monkeypatch)
    run="20261107T120000-abcdef123456"
    source=archives.storage_paths.result_media_dir(run)/"SAM 0001"/"image.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"test-photo")
    name=archives.archive_member("SAM 0001",source.name)
    first=archives.prepare(run,None,[(source,name)])
    first_stat=first.stat()
    assert first.is_file()
    assert archives.prepare(run,None,[(source,name)])==first
    assert first.stat().st_mtime_ns==first_stat.st_mtime_ns
    with zipfile.ZipFile(first) as zipped:
        assert zipped.namelist()==["SAM 0001/image.jpg"]
        assert zipped.read(name)==b"test-photo"

@pytest.mark.parametrize("bad",["..","../escape","a/b","",r"a\\b"])
def test_archive_member_rejects_unsafe_label(bad):
    with pytest.raises(HTTPException):
        archives.archive_member(bad,"a.jpg")

def test_new_source_content_invalidates_archive(tmp_path,monkeypatch):
    mock_run_storage(tmp_path,monkeypatch)
    run="20261107T120000-abcdef123456"
    source=archives.storage_paths.result_media_dir(run)/"SAM 0001"/"image.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"first")
    selection=[(source,"SAM 0001/image.jpg")]
    first=archives.prepare(run,None,selection)
    source.write_bytes(b"changed")
    second=archives.prepare(run,None,selection)
    assert second!=first

def test_zip_file_response_supports_http_byte_ranges(tmp_path,monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import FileResponse
    from starlette.testclient import TestClient
    mock_run_storage(tmp_path,monkeypatch)
    run="20261107T120000-abcdef123456"
    image=archives.storage_paths.result_media_dir(run)/"SAM 0001"/"image.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"x"*2048)
    archive=archives.prepare(run,None,[(image,"SAM 0001/image.jpg")])
    app=Starlette(routes=[Route("/zip",lambda request:FileResponse(archive))])
    with TestClient(app) as client:
        full=client.get("/zip")
        assert full.status_code==200
        assert full.headers["content-length"]==str(archive.stat().st_size)
        assert full.headers["accept-ranges"]=="bytes"
        partial=client.get("/zip",headers={"Range":"bytes=10-29"})
        assert partial.status_code==206
        assert partial.headers["content-range"]==f"bytes 10-29/{archive.stat().st_size}"
        assert len(partial.content)==20
        assert partial.content==full.content[10:30]

def test_archive_reports_byte_progress_and_skips_rebuild(tmp_path,monkeypatch):
    mock_run_storage(tmp_path,monkeypatch)
    run="20261107T120000-abcdef123456"
    photo=archives.storage_paths.result_media_dir(run)/"SAM 0001"/"one.jpg"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"jpeg-bytes"*100)
    updates=[]
    archive=archives.prepare(run,None,[(photo,"SAM 0001/one.jpg")],
        progress=lambda done,total:updates.append((done,total)))
    assert updates[-1]==(photo.stat().st_size,photo.stat().st_size)
    assert archives.existing(run,None,[(photo,"SAM 0001/one.jpg")])==archive

def test_portable_zip_names_and_duplicates():
    from server.services.archive_layout import portable_name,_unique
    assert portable_name("IMG_0015 — копия.JPG","Фото",file=True)=="IMG_0015 — копия.JPG"
    assert portable_name("..","Фотоотчёт")=="Фотоотчёт"
    assert portable_name(r"Выезд / Самара: 1","Фотоотчёт")=="Выезд _ Самара_ 1"
    assert portable_name("CON.jpg","Фото",file=True)=="_CON.jpg"
    assert list(_unique(["IMG.JPG","img.jpg","img (2).jpg"],file=True))==[
        "IMG.JPG","img (3).jpg","img (2).jpg"]
    long=portable_name("Я"*150+".JPG","Фото",file=True)
    assert len(long.encode("utf-8"))<=250
    assert long.endswith(".JPG")
