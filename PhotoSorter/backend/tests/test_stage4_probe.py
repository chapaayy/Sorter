"""Read-only workload probe against a local fake HTTP service."""
from __future__ import annotations
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import pytest
MODULE=Path(__file__).resolve().parents[2]/"tools"/"stage4"/"staging_probe.py"
spec=importlib.util.spec_from_file_location("staging_probe",MODULE)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

def test_probe_reads_health_only_and_records_real_samples():
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            payload=json.dumps({"status":"ok"}).encode("utf8")
            self.send_response(200 if self.path=="/api/health" else 404)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self,*args):pass
    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            origin="http://127.0.0.1:"+str(server.server_port)
            out=probe.collect(origin,15,3)
            assert out["status_codes"]=={200:15}
            assert out["latency_ms"]["p95"] is not None
            assert out["requests_per_second"]>0
            assert requests==["/api/health"]*15
        finally:
            server.shutdown()
            thread.join(timeout=5)

def test_external_host_requires_explicit_opt_in():
    with pytest.raises(ValueError):probe.normalize_url("https://live.example.com")
    assert probe.normalize_url("https://staging.example.com",True)=="https://staging.example.com"
    with pytest.raises(ValueError):probe.normalize_url("https://admin:pass@staging.example.com",True)
    with pytest.raises(ValueError):probe.normalize_url("https://staging.example.com/unsafe",True)
    with pytest.raises(ValueError):probe.collect("http://127.0.0.1",count=10000)
