"""Fresh and upgraded owner credentials, against isolated PostgreSQL schemas."""
from contextlib import contextmanager
import os
import uuid

from fastapi.testclient import TestClient
import psycopg
from psycopg.rows import dict_row
import pytest

from server import auth, database
from server.main import app
from server.security.login_throttle import LoginThrottle

OLD = "disposable_legacy_password"
CURRENT = "disposable_env_$admin_password"
ROTATED = "disposable_new_owner_password"
ORIGIN = "https://sorter.example.test"


@pytest.fixture(params=[False, True], ids=["fresh", "upgrade"])
def owner_db(request, monkeypatch):
    if not database.DB_URL:
        pytest.skip("No disposable PostgreSQL test instance")
    schema = "test_owner_" + uuid.uuid4().hex

    @contextmanager
    def connect():
        with psycopg.connect(database.DB_URL, options=f"-c search_path={schema}", row_factory=dict_row) as db:
            yield db

    with psycopg.connect(database.DB_URL, autocommit=True) as root:
        root.execute(f"CREATE SCHEMA {schema}")
        try:
            monkeypatch.setattr(auth, "connect", connect)
            monkeypatch.setattr(database, "connect", connect)
            monkeypatch.setattr(auth, "limiter", LoginThrottle())
            monkeypatch.setenv("ADMIN_PASSWORD", CURRENT)
            monkeypatch.setenv("DOMAIN", ORIGIN.removeprefix("https://"))
            legacy_id = None
            if request.param:
                salt = os.urandom(16)
                with connect() as db:
                    db.execute(database.SCHEMA)
                    legacy_id = db.execute(
                        "INSERT INTO users (username,password_salt,password_hash) VALUES ('admin',%s,%s) RETURNING id",
                        (salt.hex(), auth.hash_password(OLD, salt)),
                    ).fetchone()["id"]
                    db.execute(
                        "INSERT INTO sessions VALUES (%s,%s,now()+interval '1 day')",
                        ("old-token", legacy_id),
                    )
            database.initialize()
            auth.bootstrap_admin()
            yield connect, legacy_id
        finally:
            root.execute(f"DROP SCHEMA {schema} CASCADE")


def test_owner_password_comes_from_env_and_rotation_revokes_sessions(owner_db, monkeypatch):
    connect, legacy_id = owner_db
    with connect() as db:
        owner = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        assert owner["password_salt"] is None and owner["password_hash"] is None
        assert legacy_id is None or owner["id"] == legacy_id
        assert db.execute("SELECT count(*) AS n FROM sessions").fetchone()["n"] == 0

    def sign_in(client, password):
        return client.post("/api/auth/login", headers={"Origin": ORIGIN},
                           json={"username": "admin", "password": password})

    with TestClient(app, base_url=ORIGIN) as client:
        assert sign_in(client, OLD).status_code == 401
        assert sign_in(client, CURRENT).status_code == 200
        assert client.get("/api/auth/me").json() == {"username": "admin"}
        monkeypatch.setenv("ADMIN_PASSWORD", ROTATED)
        auth.bootstrap_admin()
        assert client.get("/api/auth/me").status_code == 401
        assert sign_in(client, CURRENT).status_code == 401
        assert sign_in(client, ROTATED).status_code == 200
        assert client.get("/api/auth/me").status_code == 200
