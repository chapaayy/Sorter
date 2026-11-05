"""Worker heartbeat must reflect process presence, not merely an empty queue."""
from __future__ import annotations
import uuid
import pytest
from .test_stage1_lifecycle import db,sandbox
from server.database import connect
from server.services import heartbeat

def test_worker_presence_transitions_to_stale(db):
    marker=uuid.uuid4()
    with connect() as database:
        database.execute("DELETE FROM service_heartbeats")
        empty=heartbeat.status(database)
        assert all(not r["alive"] for r in empty.values())
    heartbeat.touch("megaloc",marker)
    with connect() as database:
        fresh=heartbeat.status(database)
        assert fresh["megaloc"]["alive"] is True
        assert fresh["thumbnail"]["alive"] is False
        assert fresh["cleanup"]["alive"] is False
        database.execute("""UPDATE service_heartbeats SET seen_at=now()-interval '2 minutes'
            WHERE service='megaloc'""")
    with connect() as database:
        stale=heartbeat.status(database)
        assert stale["megaloc"]["alive"] is False
        assert stale["megaloc"]["last_seen"] is not None
    heartbeat.touch("megaloc",uuid.uuid4())
    with connect() as database:
        assert heartbeat.status(database)["megaloc"]["alive"] is True
        database.execute("DELETE FROM service_heartbeats")

def test_heartbeat_rejects_unknown_worker_role(db):
    with pytest.raises(ValueError):heartbeat.touch("invented",uuid.uuid4())
    with pytest.raises(ValueError):heartbeat.start("invented")
