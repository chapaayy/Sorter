from fastapi import HTTPException
import pytest
from server.api.routes.reference_imports import PortableConstruction
from server.services import reference_portable_catalog,reference_import_sides
from server.database import connect
from .test_unified_queue_stage3 import system

def test_portable_catalog_preview_and_idempotent_restore(system):
    items=[PortableConstruction(sam="SAM 0004",kind="standard",city_code="SAM",number="0004",address="Гагарина 64"),
           PortableConstruction(sam="Custom",kind="custom")]
    result=reference_portable_catalog.inspect(items)
    assert not result["errors"] and not result["new_regions"]
    with connect() as db:
        assert db.execute("SELECT count(*) AS n FROM reference_constructions").fetchone()["n"]==0
    assert reference_portable_catalog.inspect(items,create=True)=={"created":2}
    assert reference_portable_catalog.inspect(items,create=True)=={"created":0}
    wrong=items[0].model_copy(update={"address":"Другой адрес"})
    extra=PortableConstruction(sam="Other",kind="custom")
    with pytest.raises(HTTPException):
        reference_portable_catalog.inspect([extra,wrong],create=True)
    with connect() as db:
        assert db.execute("SELECT count(*) AS n FROM reference_constructions").fetchone()["n"]==2

def test_legacy_side_allowed_only_for_portable():
    assert reference_import_sides.normalize_import_side("Старая/сторона",True)=="Старая/сторона"
    with pytest.raises(HTTPException):reference_import_sides.normalize_import_side("Старая/сторона")
    with pytest.raises(HTTPException):reference_import_sides.normalize_import_side("bad\x00side",True)
