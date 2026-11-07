"""Strict reference imports and additive reuse; all files/database are disposable."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.photos.construction import parse_folder_name, parse_key
from server.database import connect
from server.services import construction_catalog, references
from .test_stage2_platform import thumbs, _jpg
from .test_unified_queue_stage3 import system
from .test_stage1_lifecycle import sandbox, db


@pytest.mark.parametrize("name,key,address",[
    ("SAM 0004 — Гагарина 64", "SAM 0004", "Гагарина 64"),
    ("SAM 003 — Московское шоссе 15", "SAM 003", "Московское шоссе 15"),
    ("SAM 01 — Полевая 12", "SAM 01", "Полевая 12"),
    ("TLT 3245 — Южное шоссе 10", "TLT 3245", "Южное шоссе 10"),
    ("MSK 0042 — Ленина 1", "MSK 0042", "Ленина 1"),
    ("KZN 8 — Победы 3", "KZN 8", "Победы 3"),
    ("ABCDE 123 — Садовая 2", "ABCDE 123", "Садовая 2"),
])
def test_parse_construction_folders(name,key,address):
    parsed=parse_folder_name(name)
    assert (parsed.key,parsed.address,parsed.title)==(key,address,name)
    assert parse_key(key)==(key.split(" ")[0],key.split(" ")[1])


@pytest.mark.parametrize("invalid",[
    "SAM-0004", "SAM-0004 — Гагарина 64", "SAM 0004",
    "SAM 0004 - Гагарина 64", "sam 0004 — Гагарина 64",
    "SAM 0004 — ", "SAM 0004 — Пр-т/Ленина",
    "X1Z 0004 — Адрес", "SAM 0004 — Адрес.",
    "SAM 0004 —  Два пробела", "SAM 0004 — Адрес\\folder"
])
def test_strict_import_rejects_invalid_folder(invalid):
    with pytest.raises(ValueError):
        parse_folder_name(invalid)


def test_preview_reports_all_invalid_and_never_mutates_database(thumbs):
    result=construction_catalog.preview([
        "SAM 0004 — Гагарина 64", "SAM-0004", "X1Z 1234 — Адрес"
    ])
    assert len(result["errors"])==2
    assert len(result["entries"])==1
    assert result["entries"][0]["existing"] is False
    with connect() as db:
        assert db.execute(
            "SELECT 1 FROM reference_constructions WHERE sam='SAM 0004'"
        ).fetchone() is None



def test_existing_construction_is_extended_by_a_new_staging_session(system):
    from server.services import reference_imports,reference_uploads
    from server.api.routes.reference_imports import ImportFile
    from .test_unified_queue_stage3 import add_published_reference
    key,path=add_published_reference(system,sam="SAM 0004",address="Гагарина 64")
    before=construction_catalog.preview(["SAM 0004 — Гагарина 64"])
    assert before["entries"][0]["photos"]==1
    assert before["entries"][0]["existing"]
    raw=_jpg(exif=True)
    sid=uuid.uuid4()
    fid=uuid.uuid4()
    reference_imports.create(sid)
    reference_imports.register_manifest(sid,[ImportFile(
        upload_id=fid,sam="SAM 0004",relative_path="new.jpg",filename="new.jpg",
        size=len(raw))])
    reference_uploads.append(sid,fid,0,raw)
    result=reference_uploads.finish(sid,fid)
    assert not result["already_present"]
    assert reference_imports.status(sid)["state"]=="complete"
    assert construction_catalog.preview(["SAM 0004 — Гагарина 64"])["entries"][0]["photos"]==1, (
        "Staging is invisible until the CPU preparation publishes the whole version")


def test_new_construction_requires_address_before_any_upload(system):
    from server.services import reference_imports
    from server.api.routes.reference_imports import ImportFile
    fid=uuid.uuid4()
    sid=uuid.uuid4()
    reference_imports.create(sid)
    with pytest.raises(HTTPException) as exc:
        reference_imports.register_manifest(sid,[ImportFile(
            upload_id=fid,sam="TLT 3245",relative_path="photo.jpg",
            filename="photo.jpg",size=len(_jpg()))])
    assert exc.value.status_code==422


def test_city_code_labels_can_be_exported_from_immutable_snapshot(system,tmp_path):
    from .test_unified_queue_stage3 import add_published_reference
    from server.services import reference_publication
    from server.db.repositories import reference_versions
    from app.results.copier import copy_photo
    from server.api.routes.downloads import archive_member
    add_published_reference(system,sam="TLT 3245",address="Южное шоссе 10")
    with connect() as db:
        current=reference_versions.current(db)
        pinned=reference_publication.snapshot(db,current["id"])
    assert pinned[0]["sam"]=="TLT 3245"
    result=copy_photo(__import__("pathlib").Path(pinned[0]["path"]),
                      tmp_path/"results","TLT 3245")
    assert result.is_file()
    assert archive_member("TLT 3245",result.name).startswith("TLT 3245/")


def test_manual_standard_construction_is_visible_before_photos_and_can_be_deleted(system):
    from server.api.routes import references as api
    from server.db.repositories import reference_versions
    with connect() as conn:
        previous=reference_versions.current(conn)["id"]
    item=construction_catalog.create("standard",city_code="SAM",number="0004",address="Гагарина 64")
    assert item["sam"]=="SAM 0004"
    listed=api.list_references()["sam"]
    entry=next(row for row in listed if row["sam"]=="SAM 0004")
    assert entry["photos"]==0
    assert entry["display_name"]=="SAM 0004 — Гагарина 64"
    assert construction_catalog.preview(["SAM 0004 — Гагарина 64"])["entries"][0]["existing"]
    with pytest.raises(HTTPException) as error:
        construction_catalog.create("standard",city_code="SAM",number="0004",address="Гагарина 64")
    assert error.value.status_code==409
    with connect() as conn:
        assert reference_versions.current(conn)["id"]==previous
    assert references.delete("SAM 0004")["photos"]==0
    assert not any(row["sam"]=="SAM 0004" for row in api.list_references()["sam"])


def test_custom_construction_accepts_only_explicit_staged_imports(system):
    from server.services import reference_imports
    from server.api.routes import references as api
    from server.api.routes.reference_imports import ImportFile
    name="LED у склада"
    created=construction_catalog.create("custom",name=name)
    assert created["sam"]==name
    assert created["kind"]=="custom"
    assert any(row["sam"]==name and row["photos"]==0 for row in api.list_references()["sam"])
    session=uuid.uuid4()
    reference_imports.create(session)
    registered=reference_imports.register_manifest(session,[ImportFile(
        upload_id=uuid.uuid4(),sam=name,relative_path="photo.jpg",
        filename="photo.jpg",size=len(_jpg()))])
    assert registered["expected"]==1
    with pytest.raises(HTTPException) as duplicate:
        construction_catalog.create("custom",name=name)
    assert duplicate.value.status_code==409
    for invalid in ("SAM-0004","Bad/Path","SAM 0004"):
        with pytest.raises(HTTPException):
            construction_catalog.create("custom",name=invalid)


def test_unknown_custom_construction_does_not_bypass_manifest_catalog(system):
    from server.services import reference_imports
    from server.api.routes.reference_imports import ImportFile
    session=uuid.uuid4()
    reference_imports.create(session)
    with pytest.raises(HTTPException) as err:
        reference_imports.register_manifest(session,[ImportFile(
            upload_id=uuid.uuid4(),sam="LED без регистрации",relative_path="photo.jpg",
            filename="photo.jpg",size=len(_jpg()))])
    assert err.value.status_code==422



def test_manually_entered_city_code_is_accepted_for_catalog_and_bulk_import(system):
    from server.api.routes import references as api
    from server.services import reference_imports
    from server.api.routes.reference_imports import ImportFile

    # No city-registration or allowlist step: validate the format only.
    created=construction_catalog.create("standard",city_code="MSK",number="0042",
                                        address="Ленина 1")
    assert created["sam"]=="MSK 0042"
    assert created["city_code"]=="MSK"
    assert next(row for row in api.list_references()["sam"]
                if row["sam"]=="MSK 0042")["display_name"]=="MSK 0042 — Ленина 1"
    plan=construction_catalog.preview(["MSK 0042 — Ленина 1",
                                       "KZN 0008 — Победы 3"])
    assert plan["errors"]==[]
    assert len(plan["entries"])==2
    assert plan["entries"][0]["existing"]
    assert not plan["entries"][1]["existing"]

    session=uuid.uuid4()
    reference_imports.create(session)
    registered=reference_imports.register_manifest(session,[ImportFile(
        upload_id=uuid.uuid4(),sam="MSK 0042",relative_path="photo.jpg",
        filename="photo.jpg",size=len(_jpg()))])
    assert registered["expected"]==1


@pytest.mark.parametrize("invalid",[
    "M 0004", "ABCDEF 0004", "M1K 0004", "msk 0004",
    "MSK-0004", "MSK 00A4"
])
def test_manual_city_format_stays_strict(invalid):
    with pytest.raises(ValueError):
        parse_key(invalid)
