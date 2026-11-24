"""Downloading reference photos must use only the published immutable version."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.responses import FileResponse
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from server.services import reference_archives, references
from server.security.access_policy import authorize
from .test_unified_queue_stage3 import system, add_published_reference


def test_all_references_zip_preserves_original_bytes_and_names(system, tmp_path, monkeypatch):
    key, original = add_published_reference(system, address="Гагарина 64")
    plan = reference_archives.current_plan()
    assert plan.version == 2
    archive = reference_archives.prepare(plan)
    assert archive == reference_archives.prepare(plan)
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.namelist() == ["SAM 0001 — Гагарина 64/one.jpg"]
        assert zipped.read(zipped.namelist()[0]) == original.read_bytes()
    assert str(key) not in zipped.namelist()[0]

    app = Starlette(routes=[Route("/archive", lambda request: FileResponse(archive))])
    with TestClient(app) as client:
        whole = client.get("/archive")
        portion = client.get("/archive", headers={"Range": "bytes=0-15"})
        assert whole.status_code == 200
        assert portion.status_code == 206
        assert portion.content == whole.content[:16]


def test_archive_excludes_removed_reference_from_current_version(system, tmp_path, monkeypatch):
    key, original = add_published_reference(system)
    old = reference_archives.prepare(reference_archives.current_plan())
    references.delete_photo(str(key))
    assert original.is_file()  # Historical immutable source survives.
    assert old.is_file()
    with pytest.raises(HTTPException) as error:
        reference_archives.current_plan()
    assert error.value.status_code == 404


def test_portable_file_names_and_collisions(system, tmp_path):
    key, original = add_published_reference(system)
    from server.db.repositories import reference_versions
    from server.database import connect
    with connect() as db:
        version = reference_versions.current(db)
        member = dict(reference_versions.members(db, version["id"])[0])
    second = {**member, "reference_id": "different", "filename": "ONE.jpg"}
    third = {**member, "reference_id": "another", "filename": "../unsafe?.jpg"}
    plan = reference_archives.build_plan(version, [member, second, third],
        [{"sam": "SAM 0001", "kind": "standard", "address": "Гагарина / 64"}])
    names = [entry[1] for entry in plan.files]
    assert len(names) == len(set(x.casefold() for x in names)) == 3
    assert all(name.startswith("SAM 0001 — Гагарина _ 64/") for name in names)
    assert all(".." not in Path(name).parts for name in names)


def test_viewers_cannot_export_reference_library():
    with pytest.raises(HTTPException) as error:
        authorize({"username": "viewer", "access_role": "viewer"},
                  "GET", "/api/references/export")
    assert error.value.status_code == 403
