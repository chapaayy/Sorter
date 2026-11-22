"""Region registry and scoped reference selection; MegaLoc math is unchanged."""
from __future__ import annotations
import uuid
import pytest
from fastapi import HTTPException

from server import database,jobs
from server.db.repositories import work_queue
from server.services import regions,construction_catalog,reference_imports
from server.api.routes.reference_imports import ImportFile
from .test_unified_queue_stage3 import system,add_published_reference,finish_fo


def test_region_registry_codes_and_catalog_creation(system):
    assert {"SAM","TLT"}.issubset({x["code"] for x in regions.list_all()["regions"]})
    with pytest.raises(HTTPException) as err:
        construction_catalog.create("standard",city_code="SZR",number="0045",address="Мира 9")
    assert err.value.status_code==422
    assert "SZR" in str(err.value.detail)
    with pytest.raises(HTTPException):
        regions.register("sZR")
    with pytest.raises(HTTPException):
        regions.register("S2")
    assert regions.register("SZR")=={"code":"SZR"}
    assert regions.register("SZR")=={"code":"SZR"}
    created=construction_catalog.create("standard",city_code="SZR",number="0045",address="Мира 9")
    assert created["sam"]=="SZR 0045"
    assert "SZR" in {x["code"] for x in regions.list_all()["regions"]}


def test_mixed_import_requires_explicit_new_region_confirmation(system):
    preview=construction_catalog.preview(["SAM 0102 — Гагарина 64",
                                          "SZR 0303 — Советская 15"])
    assert preview["new_regions"]==["SZR"]
    assert not preview["errors"]
    entry=ImportFile(upload_id=uuid.uuid4(),sam="SZR 0303",address="Советская 15",
                     relative_path="SZR 0303 — Советская 15/image.jpg",
                     filename="image.jpg",size=100)
    session=uuid.uuid4()
    reference_imports.create(session)
    with pytest.raises(HTTPException) as error:
        reference_imports.register_manifest(session,[entry])
    assert error.value.status_code==422
    assert "SZR" in str(error.value.detail)
    regions.register("SZR")
    assert construction_catalog.preview(["SZR 0303 — Советская 15"])["new_regions"]==[]
    assert reference_imports.register_manifest(session,[entry])["registered"]


def test_references_are_filtered_by_code_but_global_custom_is_unchanged(system):
    members=[
        {"sam":"SAM 0001","path":"one"},
        {"sam":"SZR 0020","path":"two"},
        {"sam":"TLT 0123","path":"three"},
        {"sam":"LED у склада","path":"global"},
    ]
    assert regions.filter_members(members,None)==members
    assert [x["path"] for x in regions.filter_members(members,["SAM","SZR"])]==[
        "one","two","global"]
    assert [x["path"] for x in regions.filter_members(members,["TLT"])]==[
        "three","global"]


def test_manual_run_pins_regions_without_changing_full_library(system):
    add_published_reference(system)
    # Create a batch without enqueueing it via the legacy helper.
    batch=uuid.uuid4()
    with database.connect() as db:
        db.execute("""INSERT INTO batches(id,display_name,upload_manifest_state)
            VALUES (%s,'Regional FO','complete')""",(batch,))
        db.execute("""INSERT INTO uploads(id,kind,batch_id,filename,declared_size,
            received,finalized) VALUES (%s,'fo',%s,'report.jpg',100,100,true)""",
            (uuid.uuid4(),batch))
    with pytest.raises(HTTPException) as err:
        jobs.enqueue(jobs.NewRun(batch_id=batch,regions=["SZR"]))
    assert err.value.status_code==422
    selected=jobs.enqueue(jobs.NewRun(batch_id=batch,regions=["SAM"],grouping_threshold=.50))
    assert selected["selected_regions"]==["SAM"]
    with database.connect() as db:
        task=work_queue.claim_next(db)
        assert task["kind"]=="fo_processing"
        assert task["info"]["selected_regions"]==["SAM"]
        assert len(task["info"]["reference_members"])==1
        assert task["info"]["reference_members"][0]["sam"]=="SAM 0001"
    finish_fo(selected["id"])


def test_region_selection_validated_before_queue_write(system):
    add_published_reference(system)
    with database.connect() as db:
        assert regions.selected(db,None) is None
        assert regions.selected(db,["SAM","SAM"])==["SAM"]
        for bad in ([],["sAM"],["P"],["SZR"],["SAM","SZR"]):
            with pytest.raises(HTTPException):
                regions.selected(db,bad)
