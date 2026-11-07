"""Immutable reference library bootstrap: clean beta, no legacy paths."""
from __future__ import annotations
import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

from server import database,jobs
from server.db.repositories import reference_versions,work_queue
from server.services import reference_publication,references,construction_catalog
from .test_unified_queue_stage3 import system,add_published_reference,add_fo,finish_fo
from .test_stage2_platform import _jpg

def test_fresh_database_has_one_empty_v1_without_legacy_files(system):
    with database.connect() as db:
        version=reference_versions.current(db)
        assert version["baseline_state"]=="ready"
        assert version["version_number"]==1
        assert reference_versions.members(db,version["id"])==[]
    database.initialize()
    with database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM reference_library_versions").fetchone()["n"]==1

def test_only_published_staging_is_recognition_input(system):
    rid,source=add_published_reference(system)
    with database.connect() as db:
        version=reference_versions.current(db)
        refs=reference_publication.snapshot(db,version["id"])
    assert len(refs)==1
    assert refs[0]["path"]==str(source)
    assert "/reference_staging/" in str(source)
    assert refs[0]["sam"]=="SAM 0001"

def test_delete_photo_publishes_new_version_and_retains_immutable_history(system):
    photo,source=add_published_reference(system)
    with database.connect() as db:
        previous=reference_versions.current(db)["id"]
    result=references.delete_photo(photo)
    assert result["deleted"]
    assert result["version"]==3
    with database.connect() as db:
        current=reference_versions.current(db)
        assert reference_versions.members(db,current["id"])==[]
        assert len(reference_versions.members(db,previous))==1
        assert db.execute("SELECT count(*) AS n FROM uploads WHERE kind='reference'").fetchone()["n"]==0
    assert source.is_file()
    assert source.read_bytes()==_jpg()

def test_delete_construction_publishes_version_and_cleans_catalog(system):
    add_published_reference(system)
    result=references.delete("SAM 0001")
    assert result["photos"]==1
    with database.connect() as db:
        assert db.execute("SELECT 1 FROM reference_constructions WHERE sam='SAM 0001'").fetchone() is None

def test_published_removal_cannot_bypass_queued_fo(system):
    rid,_=add_published_reference(system)
    run=add_fo()
    with pytest.raises(HTTPException) as blocked:
        references.delete_photo(rid)
    assert blocked.value.status_code==409
    with database.connect() as db:
        task=work_queue.claim_next(db)
        assert task["id"]==run
    finish_fo(run)

def test_address_edit_during_fo_does_not_change_pinned_version(system):
    add_published_reference(system)
    run=add_fo()
    with database.connect() as db:
        task=work_queue.claim_next(db)
        version=task["info"]["reference_version_id"]
    changed=construction_catalog.change_address("SAM 0001","Победы 18")
    assert changed["address"]=="Победы 18"
    with database.connect() as db:
        assert reference_versions.current(db)["id"]==version
    finish_fo(run)
