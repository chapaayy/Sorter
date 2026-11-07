"""Stage 3 SAM operations + SPA routing tested only with disposable fixtures."""
from __future__ import annotations
import hashlib
import uuid
from pathlib import Path
import pytest
from fastapi import HTTPException
from .test_stage1_lifecycle import sandbox,db,_batch,_job
from server.database import connect

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
