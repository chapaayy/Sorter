"""Fresh-process ASGI smoke: verify actual FastAPI route handling, not route internals.

Recent FastAPI versions include routers lazily in _IncludedRouter objects,
which have no .path and must not be counted as flattened APIRoute entries.
"""
from __future__ import annotations

def test_fastapi_bootstrap_routes_in_clean_python_interpreter():
    import subprocess
    import sys
    script = """
from fastapi.testclient import TestClient
from server.main import app
client = TestClient(app,raise_server_exceptions=True)
assert client.get('/api/health').status_code==200
assert client.get('/').status_code in (200,503)
assert client.get('/static/style.css').status_code==404
assert client.get('/v3',follow_redirects=False).status_code==404
assert client.get('/fo').status_code in (200,503)
assert client.get('/references').status_code in (200,503)
assert client.get('/assets/not-found.js').status_code==404
assert client.get('/api/unknown-route').status_code==404
assert client.post('/api/auth/login',json={}).status_code==422
assert client.get('/nonexistent',follow_redirects=False).status_code==404
assert len(app.routes)>=15, len(app.routes)
"""
    result=subprocess.run([sys.executable,"-c",script],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
