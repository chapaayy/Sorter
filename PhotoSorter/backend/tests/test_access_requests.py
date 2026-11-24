"""Moderation, unpublished data and owner permissions with real PostgreSQL."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from fastapi import HTTPException
from fastapi.testclient import TestClient
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from server import auth, database
from server.api.routes import access_requests, downloads, images, results
from server.main import app
from server.security.login_throttle import LoginThrottle
from server.services import access_requests as moderation, admin_users

ORIGIN = "https://sorter.example.test"
OWNER = "disposable_admin_password"
PASSWORD = "disposable_viewer_password"
EMAIL = "viewer@example.test"
RUN = "20261114T170000-0123456789ab"
HIDDEN = "20261114T170000-aaaaaaaaaaaa"


@pytest.fixture
def isolated(monkeypatch):
    if not database.DB_URL:
        pytest.skip("No disposable PostgreSQL test instance")
    schema = "access_" + uuid.uuid4().hex

    @contextmanager
    def connect():
        with psycopg.connect(database.DB_URL, options=f"-c search_path={schema}", row_factory=dict_row) as db:
            yield db

    with psycopg.connect(database.DB_URL, autocommit=True) as root:
        root.execute(f"CREATE SCHEMA {schema}")
        try:
            for module in (auth, database, moderation, admin_users, results, downloads, images):
                monkeypatch.setattr(module, "connect", connect)
            monkeypatch.setattr(auth, "limiter", LoginThrottle())
            monkeypatch.setattr(access_requests, "submissions", LoginThrottle())
            monkeypatch.setenv("DOMAIN", "sorter.example.test")
            monkeypatch.setenv("ADMIN_PASSWORD", OWNER)
            database.initialize()
            auth.bootstrap_admin()
            yield connect
        finally:
            root.execute(f"DROP SCHEMA {schema} CASCADE")


def client():
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def login(browser, username=EMAIL, password=PASSWORD):
    return browser.post("/api/auth/login", json={"username": username, "password": password})


def apply(browser, email=EMAIL, **overrides):
    return browser.post("/api/auth/register", json={
        "email": email, "password": PASSWORD, "confirmation": PASSWORD,
        "comment": "Я из отдела рекламы. Нужны готовые фотоотчёты.",
        **overrides,
    })


def add_run(connect, identifier, status):
    with connect() as db:
        batch = db.execute("INSERT INTO batches(id,display_name,owner_id) VALUES (%s,'Тестовый ФО',(SELECT id FROM users WHERE username='admin')) RETURNING id",
                           (uuid.uuid4(),)).fetchone()["id"]
        db.execute("INSERT INTO jobs(id,batch_id,status,snapshot) VALUES (%s,%s,%s,%s)",
                   (identifier,batch,status,Jsonb({"id":identifier})))


def test_approval_is_required_and_viewer_cannot_use_working_area(isolated, tmp_path, monkeypatch):
    public, owner = client(), client()
    assert public.get("/api/admin/access-requests").status_code == 401
    assert apply(public, "Viewer@EXAMPLE.TEST").status_code == 202
    assert apply(public).status_code == 202
    assert login(public).status_code == 401
    with isolated() as db:
        request = db.execute("SELECT * FROM access_requests").fetchone()
        assert request["password_hash"] not in (None, PASSWORD)
        assert db.execute("SELECT id FROM users WHERE username=%s", (EMAIL,)).fetchone() is None

    assert login(owner, "admin", OWNER).status_code == 200
    inbox = owner.get("/api/admin/access-requests").json()["items"]
    assert len(inbox) == 1 and inbox[0]["email"] == EMAIL
    assert "отдела рекламы" in inbox[0]["comment"]
    assert set(inbox[0]) == {"id","email","comment","status","created_at","decided_at"}
    decision = f"/api/admin/access-requests/{inbox[0]['id']}/decision"
    add_run(isolated, RUN, "running")
    assert owner.post(decision, json={"approved": True,"run_ids":[RUN]}).status_code == 409
    with isolated() as db:
        db.execute("UPDATE jobs SET status='completed' WHERE id=%s",(RUN,))
    add_run(isolated, HIDDEN, "completed")
    assert owner.post(decision, json={"approved": True,"run_ids":[RUN]}).json()["status"] == "approved"
    assert owner.post(decision, json={"approved": False}).status_code == 409
    assert login(public, "VIEWER@example.test").json() == {"username": EMAIL}
    assert public.get("/api/auth/me").json() == {"username": EMAIL}

    for path in ("/api/admin/access-requests", "/api/runs", "/api/batches",
                 "/api/references", "/api/system/status", "/api/processing-settings",
                 f"/api/photos/{uuid.uuid4()}/original", f"/api/thumbnails/{uuid.uuid4()}",
                 f"/api/results/{RUN}/megaloc"):
        assert public.get(path).status_code == 403, path
    assert public.post(decision, json={"approved": True}).status_code == 403
    assert public.post("/api/batches", json={}).status_code == 403
    for path in (f"/api/download/{HIDDEN}",f"/api/results/{HIDDEN}",
                 f"/api/results/{HIDDEN}/photos",f"/api/images/{HIDDEN}/megaloc/0?kind=copy"):
        assert public.get(path).status_code == 404, path
    with isolated() as db:
        assert db.execute("SELECT password_hash FROM access_requests").fetchone()["password_hash"] is None
        db.execute("UPDATE jobs SET status='running' WHERE id=%s",(RUN,))
    assert public.get(f"/api/results/{RUN}").status_code == 404
    assert public.get("/api/results/catalog").json()["items"] == []
    with isolated() as db:
        db.execute("UPDATE jobs SET status='completed' WHERE id=%s",(RUN,))
    assert [row["id"] for row in public.get("/api/results/catalog").json()["items"]] == [RUN]
    assert public.get(f"/api/results/{RUN}").json() == {"id":RUN,"status":"completed","display_name":"Тестовый ФО"}

    file = tmp_path/"outputs"/RUN/"megaloc"/"test.jpg"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"published-photo")
    monkeypatch.setattr(images,"DATA_DIR",tmp_path)
    monkeypatch.setattr(images,"safe_manifest",lambda _:[{"copy":str(file),"query":"/private/original.jpg"}])
    assert public.get(f"/api/images/{RUN}/megaloc/0?kind=reference").status_code == 403
    assert public.get(f"/api/images/{RUN}/megaloc/0").status_code == 403
    assert public.get(f"/api/images/{RUN}/megaloc/0?kind=copy").content == b"published-photo"
    grants = decision.removesuffix("/decision") + "/grants"
    assert public.put(grants,json={"run_ids":[HIDDEN]}).status_code == 403
    assert [row["id"] for row in owner.get(grants).json()["items"]] == [RUN]
    assert owner.put(grants,json={"run_ids":[]}).json() == {"items":[]}
    assert public.get(f"/api/images/{RUN}/megaloc/0?kind=copy").status_code == 404
    assert public.get("/api/results/catalog").json()["items"] == []
    assert [row["id"] for row in owner.put(grants,json={"run_ids":[HIDDEN]}).json()["items"]] == [HIDDEN]
    assert public.get(f"/api/results/{HIDDEN}").status_code == 200
    assert public.post("/api/auth/logout").status_code == 200
    assert public.get("/api/results/catalog").status_code == 401


def test_reject_validation_origin_and_rate_limit(isolated):
    public, owner = client(), client()
    assert apply(public, confirmation="not matching").status_code == 422
    invalid = apply(public, password="short-test")
    assert invalid.status_code == 422 and "short-test" not in invalid.text
    assert public.post("/api/auth/register",headers={"Origin":"https://other.test"},
                       json={"email":EMAIL,"password":PASSWORD,"confirmation":PASSWORD,"comment":"test"}).status_code == 403
    assert apply(public).status_code == 202
    assert login(owner,"admin",OWNER).status_code == 200
    entry = owner.get("/api/admin/access-requests").json()["items"][0]
    outcome = owner.post(f"/api/admin/access-requests/{entry['id']}/decision",json={"approved":False})
    assert outcome.json()["status"] == "rejected"
    assert login(public).status_code == 401
    for i in range(3):
        assert apply(public,f"more-{i}@example.test").status_code == 202
    assert apply(public,"blocked@example.test").status_code == 429


def test_concurrent_decisions_cannot_create_two_accounts(isolated):
    moderation.submit(EMAIL,PASSWORD,PASSWORD,"Тест")
    request_id = moderation.page("pending",30,0)["items"][0]["id"]

    def approve(_):
        try:
            moderation.decide(request_id,True)
        except HTTPException as error:
            return error.status_code
        return 200

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(approve, range(2))) == [200,409]
    with isolated() as db:
        assert db.execute("SELECT count(*) AS n FROM users WHERE username=%s",(EMAIL,)).fetchone()["n"] == 1


def test_owner_can_create_active_account_and_change_its_grants(isolated):
    owner, viewer, guest = client(), client(), client()
    add_run(isolated, RUN, "completed")
    add_run(isolated, HIDDEN, "completed")
    endpoint = "/api/admin/users"
    body = {"email":"  Viewer@EXAMPLE.TEST ","password":PASSWORD,
            "confirmation":PASSWORD,"run_ids":[RUN]}
    assert guest.post(endpoint,json=body).status_code == 401
    assert login(owner,"admin",OWNER).status_code == 200
    assert owner.post(endpoint,json=body,headers={"Origin":"https://other.test"}).status_code == 403
    assert owner.post(endpoint,json={**body,"run_ids":[RUN.replace("b","0")]}).status_code == 409
    assert login(viewer).status_code == 401
    invalid = owner.post(endpoint,json={**body,"password":"short-test"})
    assert invalid.status_code == 422 and "short-test" not in invalid.text
    assert owner.post(endpoint,json={**body,"confirmation":"wrong"}).status_code == 422

    response = owner.post(endpoint,json=body)
    assert response.status_code == 201
    record = response.json()
    assert set(record) == {"id","email","created_at"} and record["email"] == EMAIL
    assert owner.get(endpoint).json() == {"items":[record],"has_more":False}
    assert owner.post(endpoint,json=body).status_code == 409
    assert login(viewer).status_code == 200
    assert viewer.get(endpoint).status_code == 403
    assert viewer.post(endpoint,json=body).status_code == 403
    path = f"{endpoint}/{record['id']}/grants"
    assert viewer.put(path,json={"run_ids":[HIDDEN]}).status_code == 403
    assert [x["id"] for x in viewer.get("/api/results/catalog").json()["items"]] == [RUN]
    assert viewer.get(f"/api/results/{HIDDEN}").status_code == 404
    assert owner.put(path,json={"run_ids":[HIDDEN]}).status_code == 200
    assert [x["id"] for x in viewer.get("/api/results/catalog").json()["items"]] == [HIDDEN]
    assert owner.put(path,json={"run_ids":[]}).json() == {"items":[]}
    assert viewer.get("/api/results/catalog").json()["items"] == []
    with isolated() as db:
        user = db.execute("SELECT password_hash,access_role FROM users WHERE username=%s",(EMAIL,)).fetchone()
        assert user["password_hash"] != PASSWORD and user["access_role"] == "viewer"
        assert db.execute("SELECT count(*) AS n FROM access_requests").fetchone()["n"] == 0


def test_direct_account_creation_resolves_existing_request_without_using_its_password(isolated):
    owner, viewer = client(), client()
    assert apply(viewer).status_code == 202
    assert login(owner,"admin",OWNER).status_code == 200
    password = PASSWORD + "_set_by_owner"
    created = owner.post("/api/admin/users",json={
        "email": EMAIL,"password":password,"confirmation":password,"run_ids":[],
    })
    assert created.status_code == 201
    assert login(viewer).status_code == 401
    assert login(viewer,password=password).status_code == 200
    assert owner.get("/api/admin/access-requests?status=pending").json()["items"] == []
    with isolated() as db:
        request = db.execute("SELECT status,password_hash FROM access_requests").fetchone()
        assert request == {"status":"approved","password_hash":None}
