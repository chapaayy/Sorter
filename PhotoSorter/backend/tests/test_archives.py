"""Cached ZIP is deterministic and seekable; invalid paths cannot escape outputs."""
import zipfile
from pathlib import Path
import pytest
from fastapi import HTTPException
from server.services import archives

def test_cached_archive_is_reused(tmp_path,monkeypatch):
    monkeypatch.setattr(archives,"ROOT",tmp_path)
    run="20261107T120000-abcdef123456"
    source=tmp_path/run/"megaloc"/"SAM 0001"/"image.jpg"
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
    monkeypatch.setattr(archives,"ROOT",tmp_path)
    run="20261107T120000-abcdef123456"
    source=tmp_path/run/"megaloc"/"SAM 0001"/"image.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"first")
    selection=[(source,"SAM 0001/image.jpg")]
    first=archives.prepare(run,None,selection)
    source.write_bytes(b"changed")
    second=archives.prepare(run,None,selection)
    assert second!=first
