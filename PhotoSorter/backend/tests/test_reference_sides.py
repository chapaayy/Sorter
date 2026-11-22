"""Reference side metadata and delayed deletion are independent from MegaLoc math."""
from __future__ import annotations
import uuid
import pytest
from fastapi import HTTPException

from app.results.sides import attach_sides
from server import database
from server.db.repositories import reference_versions,work_queue
from server.services import reference_sides,reference_publication,references
from server.api.routes import references as api
from .test_unified_queue_stage3 import system,add_published_reference,add_fo,finish_fo


def test_winning_group_reference_side_is_only_an_export_label():
    members=[
        {"path":"/refs/A.jpg","sam":"SAM 0001","side":"А"},
        {"path":"/refs/B.jpg","sam":"SAM 0001","side":"Б"},
    ]
    rows=[
        {"group_id":"G0001","top":[{"label":"SAM 0001","reference":"/refs/A.jpg"}]},
        {"group_id":"G0001","top":[{"label":"SAM 0001","reference":"/refs/A.jpg"}]},
        {"group_id":"G0002","top":[{"label":"SAM 0001","reference":"/refs/B.jpg"}],"media_kind":"video"},
        {"group_id":"G0003","top":[]},
        {"group_id":"G0004","top":[{"label":"SAM 0002","reference":"/refs/A.jpg"}]},
    ]
    expected_tops=[r["top"] for r in rows]
    assert [r["side"] for r in attach_sides(rows,members)]==["А","А","Б",None,None]
    assert [r["top"] for r in rows]==expected_tops


def test_reference_side_assignment_freezes_at_fo_claim(system):
    ident,_=add_published_reference(system)
    with database.connect() as db:
        version=reference_versions.current(db)["id"]
    assert reference_sides.assign("SAM 0001",[ident],"A")=={"updated":1,"side":"A"}
    assert api.gallery("SAM 0001")["photos"][0]["side"]=="A"
    first=add_fo()
    with database.connect() as db:
        claimed=work_queue.claim_next(db)
        assert claimed["id"]==first
        assert claimed["info"]["reference_members"][0]["side"]=="A"
    assert reference_sides.assign("SAM 0001",[ident],"B3")["side"]=="B3"
    assert claimed["info"]["reference_members"][0]["side"]=="A"
    with database.connect() as db:
        assert reference_versions.current(db)["id"]==version
    finish_fo(first)
    second=add_fo()
    with database.connect() as db:
        claimed=work_queue.claim_next(db)
        assert claimed["id"]==second
        assert claimed["info"]["reference_members"][0]["side"]=="B3"
    finish_fo(second)
    reference_sides.assign("SAM 0001",[ident],None)
    assert api.gallery("SAM 0001")["photos"][0]["side"] is None


def test_side_validation_and_cross_construction_ids(system):
    ident,_=add_published_reference(system)
    for bad in ("..","A/B","А","Б","А1","B4","A0","P","P1","C",
                "x:evil","А.","Неназначена сторона",""):
        with pytest.raises(HTTPException) as error:
            reference_sides.assign("SAM 0001",[ident],bad)
        assert error.value.status_code==422
    for allowed in ("A", "A1", "A2", "A3", "B", "B1", "B2", "B3"):
        assert reference_sides.assign("SAM 0001",[ident],allowed)["side"]==allowed
    assert reference_sides.assign("SAM 0001",[ident],"b2")["side"]=="B2"
    with pytest.raises(HTTPException) as error:
        reference_sides.assign("SAM 0002",[ident],"A")
    assert error.value.status_code==409
    with pytest.raises(HTTPException) as error:
        reference_sides.assign("SAM 0001",[uuid.uuid4()],"A")
    assert error.value.status_code==409


def test_reference_deletion_queue_is_idempotent_and_crash_retriable(system):
    ident,_=add_published_reference(system)
    first=add_fo()
    requested=references.delete_photo(ident)
    assert requested["queued"]
    assert references.delete_photo(ident)["task_id"]==requested["task_id"]
    with database.connect() as db:
        claimed=work_queue.claim_next(db)
        assert claimed["id"]==first
    finish_fo(first)
    with database.connect() as db:
        deletion=work_queue.claim_next(db)
        assert deletion["kind"]=="reference_deletion"
        work_queue.mark_interrupted(db)
        retry=work_queue.claim_next(db)
        assert retry["id"]==deletion["id"]
    references.process_deferred(retry["id"])
    with database.connect() as db:
        state=db.execute("SELECT state FROM work_queue WHERE reference_deletion_id=%s",
                         (retry["id"],)).fetchone()
        assert state["state"]=="completed"
        assert reference_versions.members(db,reference_versions.current(db)["id"])==[]
