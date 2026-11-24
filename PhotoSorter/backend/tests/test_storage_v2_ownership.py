import uuid
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from server.database import connect
from server.services import batches
from server.api.routes.batches import create,NewBatch
from .test_stage1_lifecycle import db,owner_for_test

def test_creation_has_explicit_authenticated_owner(db):
    import psycopg
    with connect() as conn:
        owner_id=owner_for_test(conn)
        viewer=conn.execute("INSERT INTO users(username,access_role) VALUES (%s,'viewer') RETURNING id",
                            (uuid.uuid4().hex,)).fetchone()["id"]
    identifier=None
    try:
        with pytest.raises(HTTPException) as exc:
            batches.create("viewer",owner_id=viewer)
        assert exc.value.status_code==403
        request=Request({"type":"http","state":{"user":{"id":owner_id,"username":"admin","access_role":"owner"}}})
        identifier=uuid.UUID(create(request,NewBatch(display_name=uuid.uuid4().hex))["batch_id"])
        with connect() as conn:
            assert conn.execute("SELECT owner_id FROM batches WHERE id=%s",(identifier,)).fetchone()["owner_id"]==owner_id
            with pytest.raises(psycopg.errors.NotNullViolation):
                with conn.transaction():
                    conn.execute("INSERT INTO batches(id) VALUES (%s)",(uuid.uuid4(),))
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    conn.execute("UPDATE batches SET owner_id=%s WHERE id=%s",(2**63-1,identifier))
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    conn.execute("DELETE FROM users WHERE id=%s",(owner_id,))
    finally:
        with connect() as conn:
            if identifier: conn.execute("DELETE FROM batches WHERE id=%s",(identifier,))
            conn.execute("DELETE FROM users WHERE id=%s",(viewer,))
