"""Strict reference imports and additive reuse; all files/database are disposable."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.photos.construction import parse_folder_name, parse_key
from server.database import connect
from server.services import construction_catalog, references
from .test_stage2_platform import thumbs, _jpg
from .test_stage1_lifecycle import sandbox, db


@pytest.mark.parametrize("name,key,address",[
    ("SAM 0004 — Гагарина 64", "SAM 0004", "Гагарина 64"),
    ("SAM 003 — Московское шоссе 15", "SAM 003", "Московское шоссе 15"),
    ("SAM 01 — Полевая 12", "SAM 01", "Полевая 12"),
    ("TLT 3245 — Южное шоссе 10", "TLT 3245", "Южное шоссе 10"),
])
def test_parse_construction_folders(name,key,address):
    parsed=parse_folder_name(name)
    assert (parsed.key,parsed.address,parsed.title)==(key,address,name)
    assert parse_key(key)==(key.split(" ")[0],key.split(" ")[1])


@pytest.mark.parametrize("invalid",[
    "SAM-0004", "SAM-0004 — Гагарина 64", "SAM 0004",
    "SAM 0004 - Гагарина 64", "sam 0004 — Гагарина 64",
    "SAM 0004 — ", "SAM 0004 — Пр-т/Ленина",
    "XYZ 0004 — Адрес", "SAM 0004 — Адрес.",
    "SAM 0004 —  Два пробела", "SAM 0004 — Адрес\\folder"
])
def test_strict_import_rejects_invalid_folder(invalid):
    with pytest.raises(ValueError):
        parse_folder_name(invalid)


def test_preview_reports_all_invalid_and_never_mutates_database(thumbs):
    result=construction_catalog.preview([
        "SAM 0004 — Гагарина 64", "SAM-0004", "XYZ 1234 — Адрес"
    ])
    assert len(result["errors"])==2
    assert len(result["entries"])==1
    assert result["entries"][0]["existing"] is False
    with connect() as db:
        assert db.execute(
            "SELECT 1 FROM reference_constructions WHERE sam='SAM 0004'"
        ).fetchone() is None


def test_existing_construction_is_extended_and_photo_duplicates_are_skipped(thumbs,monkeypatch):
    from server import uploads
    monkeypatch.setattr(references,"REFS",thumbs/"references")
    number=str(uuid.uuid4().int % 10**8).zfill(8)
    key="SAM "+number
    address="Гагарина 64"
    folder=key+" — "+address
    jpeg=_jpg()

    def finalize(raw,filename,include_address):
        ident=uuid.uuid4()
        uploads._create_upload(uploads.BeginUpload(kind="reference",
            sam=key,address=address if include_address else None,
            filename=filename,size=len(raw)),ident)
        (thumbs/"incoming"/f"{ident}.part").write_bytes(raw)
        return uploads._finalize_sync(str(ident))

    try:
        first=finalize(jpeg,"image_01.jpg",True)
        assert first["already_finalized"] is False
        preview=construction_catalog.preview([folder])
        assert preview["errors"]==[]
        assert preview["entries"][0]["existing"] is True
        assert preview["entries"][0]["photos"]==1
        duplicate=finalize(jpeg,"image_duplicated.jpg",True)
        assert duplicate["already_present"] is True
        second=finalize(_jpg(exif=True),"image_02.jpg",False)
        assert second["already_finalized"] is False
        with connect() as db:
            count=db.execute("SELECT count(*) AS n FROM uploads WHERE sam=%s AND finalized",(key,)).fetchone()["n"]
        assert count==2
        with pytest.raises(HTTPException) as exc:
            uploads._create_upload(uploads.BeginUpload(kind="reference",
                sam=key,address="Другой адрес",filename="bad.jpg",size=len(jpeg)),uuid.uuid4())
        assert exc.value.status_code==409
        assert construction_catalog.change_address(key,"Гагарина 64А")["address"]=="Гагарина 64А"
        assert len(construction_catalog.preview([folder])["errors"])==1
        assert construction_catalog.preview([key+" — Гагарина 64А"])["errors"]==[]
    finally:
        references.delete(key)
    with connect() as db:
        assert db.execute("SELECT 1 FROM reference_constructions WHERE sam=%s",(key,)).fetchone() is None


def test_new_construction_cannot_be_created_without_an_address(thumbs):
    from server import uploads
    number=str(uuid.uuid4().int % 10**8).zfill(8)
    with pytest.raises(HTTPException) as exc:
        uploads._create_upload(uploads.BeginUpload(
            kind="reference",sam="TLT "+number,filename="image.jpg",size=100),uuid.uuid4())
    assert exc.value.status_code==422
