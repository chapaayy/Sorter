"""Stage 3 SAM operations + SPA routing tested only with disposable fixtures."""
from __future__ import annotations
import hashlib
import uuid
from pathlib import Path
import pytest
from fastapi import HTTPException
from .test_stage1_lifecycle import sandbox,db,_batch,_job
from server.database import connect
from server.services import references,cleanup

@pytest.fixture
def sam_store(sandbox,monkeypatch):
    monkeypatch.setattr(references,"REFS",sandbox/"references")
    return sandbox/"references"

def _reference(root,sam="SAM-1764"):
    folder=root/sam
    folder.mkdir(parents=True,exist_ok=True)
    ident=uuid.uuid4()
    src=folder/"picture.jpg"
    data=b"valid-image-bytes-for-ownership"
    src.write_bytes(data)
    with connect() as db:
        db.execute("""INSERT INTO uploads(id,kind,sam,filename,declared_size,
            received,checksum,finalized,target_path)
            VALUES (%s,'reference',%s,'picture.jpg',%s,%s,%s,true,%s)""",
            (ident,sam,len(data),len(data),hashlib.sha256(data).hexdigest(),str(src)))
    return ident,src

def test_rename_sam_moves_metadata_and_keeps_bytes(sam_store):
    ident,src=_reference(sam_store)
    digest=hashlib.sha256(src.read_bytes()).hexdigest()
    result=references.rename("SAM-1764","SAM-1765")
    assert result["renamed"] is True
    assert result["sam"]=="SAM-1765"
    with connect() as db:
        row=db.execute("SELECT sam,target_path FROM uploads WHERE id=%s",(ident,)).fetchone()
    dest=Path(row["target_path"])
    assert row["sam"]=="SAM-1765"
    assert dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()==digest
    assert dest.is_relative_to(sam_store/"SAM-1765")
    assert not src.exists()
    assert references.delete("SAM-1765")["deleted"]
    assert not dest.exists()
    with connect() as db:
        assert db.execute("SELECT 1 FROM uploads WHERE id=%s",(ident,)).fetchone() is None

def test_rename_does_not_overwrite_existing_sam(sam_store):
    a,source=_reference(sam_store,"SAM-1766")
    b,other=_reference(sam_store,"SAM-1767")
    with pytest.raises(HTTPException) as exc:
        references.rename("SAM-1766","SAM-1767")
    assert exc.value.status_code==409
    assert source.exists() and other.exists()
    references.delete("SAM-1766")
    references.delete("SAM-1767")

def test_sam_changes_reject_traversal_and_busy_jobs(sam_store,sandbox):
    uid,src=_reference(sam_store,"SAM-1768")
    with pytest.raises(HTTPException) as exc:
        references.rename("SAM-1768","../../Models")
    assert exc.value.status_code==422
    own=_batch(sandbox,with_photo=False)
    _job(sandbox,own,status="queued")
    with pytest.raises(HTTPException) as exc:
        references.delete("SAM-1768")
    assert exc.value.status_code==409 and src.exists()
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="completed"
    assert references.delete("SAM-1768")["deleted"]

def test_single_root_vue_site_and_assets_cannot_escape(tmp_path,monkeypatch):
    from server.api.routes import site
    root=tmp_path/"dist"
    assets=root/"assets"
    assets.mkdir(parents=True)
    (root/"index.html").write_text("<!doctype html><title>vue</title>",encoding="utf8")
    (assets/"main-1.js").write_text("export {}",encoding="utf8")
    monkeypatch.setattr(site,"VUE_DIST",root)
    assert site.index().path==root/"index.html"
    assert site.app_route("fo/example").path==root/"index.html"
    assert site.app_route("references").path==root/"index.html"
    assert site.asset("main-1.js").path==assets/"main-1.js"
    with pytest.raises(HTTPException) as exc:site.asset("../../index.html")
    assert exc.value.status_code==404
    with pytest.raises(HTTPException) as exc:site.app_route("not-a-valid-page")
    assert exc.value.status_code==404
    for old_path in ("v3/fo", "static/app.js", "api/something"):
        with pytest.raises(HTTPException) as exc:site.app_route(old_path)
        assert exc.value.status_code==404
