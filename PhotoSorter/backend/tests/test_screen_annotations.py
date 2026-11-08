"""Screen annotation contracts: pixels, EXIF, construction scoping and optimistic writes."""
from __future__ import annotations

import uuid
from pathlib import Path
import pytest
from fastapi import HTTPException
from PIL import Image
from server.database import connect
from server.services import screen_annotations as screens
from server.services.screen_geometry import validate
from .test_unified_queue_stage3 import system,add_published_reference
from .test_stage2_platform import _jpg

CORNERS=[{"x":10,"y":5},{"x":70,"y":6},{"x":68,"y":35},{"x":11,"y":34}]

@pytest.mark.parametrize("corners",[
    CORNERS[:3],
    [CORNERS[0],CORNERS[2],CORNERS[1],CORNERS[3]],
    [{"x":-1,"y":1},*CORNERS[1:]],
    [{"x":10,"y":5}]*4,
])
def test_reject_invalid_polygon(corners):
    with pytest.raises(ValueError):
        validate(corners,2,80,40)

def test_reject_invalid_band():
    for band in (0,11,float("inf"),float("nan")):
        with pytest.raises(ValueError):
            validate(CORNERS,band,80,40)

def test_valid_perspective_quad_and_polygon_area():
    points=validate(CORNERS,2,80,40)
    assert points==CORNERS

def test_screen_annotations_persist_and_are_construction_scoped(system,monkeypatch):
    key,_=add_published_reference(system,sam="SAM 0001")
    monkeypatch.setattr(screens,"DATA_DIR",system)
    info=screens.metadata("SAM 0001",key)
    assert (info["width"],info["height"])==(80,40)
    created=screens.create("SAM 0001",key,None,"Левый LED",CORNERS,2)
    left=created["screen_id"]
    other=screens.create("SAM 0001",key,None,"Правый LED",CORNERS,3)
    assert left!=other["screen_id"]
    listing=screens.list_screens("SAM 0001")["screens"]
    assert len(listing)==2
    assert listing[0]["annotations"][0]["reference_id"]==str(key)
    assert listing[0]["annotations"][0]["source_sha256"]==info["source_sha256"]
    with pytest.raises(HTTPException) as wrong:
        screens.create("TLT 0001",key,uuid.UUID(left),None,CORNERS,2)
    assert wrong.value.status_code==404
    with pytest.raises(HTTPException) as duplicate:
        screens.create("SAM 0001",key,uuid.UUID(left),None,CORNERS,2)
    assert duplicate.value.status_code==409
    changed=screens.update("SAM 0001",uuid.UUID(created["id"]),1,CORNERS,4)
    assert changed["version"]==2
    with pytest.raises(HTTPException) as stale:
        screens.update("SAM 0001",uuid.UUID(created["id"]),1,CORNERS,5)
    assert stale.value.status_code==409
    listing=screens.list_screens("SAM 0001")["screens"]
    assert listing[0]["annotations"][0]["band_width_px"]==4
    assert screens.remove_annotation("SAM 0001",uuid.UUID(created["id"]))["deleted"]
    assert screens.remove_screen("SAM 0001",uuid.UUID(other["screen_id"]))["deleted"]
    assert screens.list_screens("SAM 0001")["screens"][0]["annotations"]==[]

def test_annotation_auto_removed_when_reference_is_deleted(system,monkeypatch):
    key,_=add_published_reference(system)
    monkeypatch.setattr(screens,"DATA_DIR",system)
    created=screens.create("SAM 0001",key,None,"LED",CORNERS,2)
    with connect() as db:
        db.execute("DELETE FROM uploads WHERE id=%s",(key,))
    assert screens.list_screens("SAM 0001")["screens"][0]["annotations"]==[]
    with pytest.raises(HTTPException) as err:
        screens.metadata("SAM 0001",key)
    assert err.value.status_code==404

def test_exif_oriented_dimensions_match_editor_canvas(system,monkeypatch):
    monkeypatch.setattr(screens,"DATA_DIR",system)
    root=system/"references"/"SAM 0001"
    root.mkdir(parents=True,exist_ok=True)
    path=root/"exif.jpg"
    path.write_bytes(_jpg(exif=True))
    info=screens._metadata({"id":uuid.uuid4(),"sam":"SAM 0001",
        "target_path":str(path),"checksum":"test"})
    assert (info["width"],info["height"])==(40,80)
