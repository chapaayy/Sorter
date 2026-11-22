"""Edit construction metadata without damaging historical versions or files."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

from server.database import connect
from server.api.routes import references as api, originals
from server.db.repositories import reference_versions
from server.services import construction_catalog, construction_relabel
from .test_unified_queue_stage3 import system, add_published_reference, add_fo


def test_rename_changes_current_version_and_keeps_historical_originals(system,monkeypatch):
    reference_id, source = add_published_reference(system)
    with connect() as db:
        before = reference_versions.current(db)
        old_members = reference_versions.members(db, before["id"])
    renamed = construction_relabel.update(
        "SAM 0001","standard",city_code="TLT",number="0042",address="Мира 9"
    )
    assert renamed["sam"] == "TLT 0042"
    assert renamed["version"] == before["version_number"] + 1
    with connect() as db:
        current = reference_versions.current(db)
        members = reference_versions.members(db,current["id"])
        old_still = reference_versions.members(db,before["id"])
        upload = db.execute(
            "SELECT sam,target_path FROM uploads WHERE id=%s", (reference_id,)
        ).fetchone()
    assert members[0]["sam"] == "TLT 0042"
    assert old_still[0]["sam"] == old_members[0]["sam"] == "SAM 0001"
    assert members[0]["reference_id"] == reference_id
    assert members[0]["target_path"] == str(source)
    assert upload["sam"] == "TLT 0042"
    assert Path(upload["target_path"]).is_file()
    assert api.list_references()["sam"][0]["display_name"] == "TLT 0042 — Мира 9"
    assert len(api.gallery("TLT 0042")["photos"]) == 1
    monkeypatch.setattr(originals, "DATA_DIR", system)
    response = originals.original(str(reference_id))
    assert Path(response.path).read_bytes() == source.read_bytes()
    assert "references/SAM 0001/" in str(response.path)


def test_only_address_changes_without_new_version_even_with_queued_fo(system):
    add_published_reference(system)
    with connect() as db:
        before = reference_versions.current(db)["id"]
    add_fo()
    result = construction_relabel.update(
        "SAM 0001","standard",city_code="SAM",number="0001",address="Победы 18"
    )
    assert result["sam"] == "SAM 0001"
    assert result["changed"]
    with connect() as db:
        assert reference_versions.current(db)["id"] == before


def test_rename_rejected_during_queued_fo(system):
    add_published_reference(system)
    add_fo()
    with pytest.raises(HTTPException) as error:
        construction_relabel.update("SAM 0001","standard",
            city_code="SAM",number="0050",address="Победы 12")
    assert error.value.status_code == 409
    assert api.list_references()["sam"][0]["sam"] == "SAM 0001"


def test_collision_rejected_without_any_mutation(system):
    add_published_reference(system)
    construction_catalog.create("standard",city_code="TLT",number="0002",address="Мира 9")
    with connect() as db:
        original = reference_versions.current(db)["id"]
    with pytest.raises(HTTPException) as error:
        construction_relabel.update("SAM 0001","standard",
            city_code="TLT",number="0002",address="Мира 9")
    assert error.value.status_code == 409
    with connect() as db:
        assert reference_versions.current(db)["id"] == original
        assert db.execute("SELECT 1 FROM reference_constructions WHERE sam='SAM 0001'").fetchone()


def test_rename_rejected_when_upload_manifest_active(system):
    from server.services import reference_imports
    from server.api.routes.reference_imports import ImportFile
    add_published_reference(system)
    sid=uuid.uuid4()
    reference_imports.create(sid)
    reference_imports.register_manifest(sid,[ImportFile(
        upload_id=uuid.uuid4(),sam="SAM 0001",relative_path="new.jpg",
        filename="new.jpg",size=100
    )])
    with pytest.raises(HTTPException) as error:
        construction_relabel.update("SAM 0001","standard",
            city_code="SAM",number="0099",address="Победы 12")
    assert error.value.status_code == 409


def test_switch_between_custom_and_standard_without_reupload(system):
    from server.services import regions
    regions.register("MSK")
    ref_id, _ = add_published_reference(system)
    first=construction_relabel.update("SAM 0001","custom",name="LED у склада")
    assert first["sam"]=="LED у склада"
    assert api.list_references()["sam"][0]["kind"]=="custom"
    second=construction_relabel.update("LED у склада","standard",
        city_code="MSK",number="0099",address="Ленина 1")
    assert second["sam"]=="MSK 0099"
    with connect() as db:
        row=db.execute("SELECT id,sam FROM uploads WHERE id=%s",(ref_id,)).fetchone()
        assert row["sam"]=="MSK 0099"


def test_empty_construction_can_be_renamed_without_new_model_version(system):
    construction_catalog.create("custom",name="Старое название")
    with connect() as db:
        version=reference_versions.current(db)["id"]
    updated=construction_relabel.update("Старое название","custom",name="Новое название")
    assert updated["sam"]=="Новое название"
    with connect() as db:
        assert reference_versions.current(db)["id"]==version
    assert construction_relabel.update("Новое название","custom",name="Новое название")["changed"] is False


@pytest.mark.parametrize("name",["../bad","SAM 0004","SAM-0004",""])
def test_invalid_custom_name_rejected(system,name):
    construction_catalog.create("custom",name="LED у склада")
    with pytest.raises(HTTPException) as error:
        construction_relabel.update("LED у склада","custom",name=name)
    assert error.value.status_code == 422


def test_viewer_cannot_patch_construction():
    from server.security.access_policy import authorize
    with pytest.raises(HTTPException) as error:
        authorize({"username":"viewer","access_role":"viewer"},
                  "PATCH","/api/references/constructions/SAM%200001")
    assert error.value.status_code == 403
