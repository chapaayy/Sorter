import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def test_service_budget_redaction_and_serial_rotation(tmp_path,monkeypatch):
    from app.logging.service import write_record
    monkeypatch.setenv("ADMIN_PASSWORD","SyntheticPasswordOnlyForTest")
    def write(n):
        write_record(tmp_path,"api",f"record {n} password=SyntheticPasswordOnlyForTest",
                     segment_bytes=512,segments=3)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(write,range(80)))
    files=list(tmp_path.glob("service.jsonl*"))
    assert len(files)==3
    assert sum(f.stat().st_size for f in files)<=1536
    for f in files:
        for line in f.read_text().splitlines():
            record=json.loads(line)
            assert "SyntheticPasswordOnlyForTest" not in record["message"]
            assert "[REDACTED]" in record["message"]

def test_processing_budget_preserves_active_and_prunes_terminal(tmp_path,monkeypatch):
    from app.logging import events
    monkeypatch.setattr(events,"RUNS_DIR",tmp_path)
    monkeypatch.setattr(events,"TOTAL_BYTES",100)
    active="20261124T000000-abcdef123456"
    terminal="20261124T000001-abcdef123456"
    for run in (active,terminal):
        path=tmp_path/run
        path.mkdir()
        (path/"events.jsonl").write_bytes(b"x"*120)
    events.prune_terminal([terminal])
    assert (tmp_path/active/"events.jsonl").exists()
    assert not (tmp_path/terminal/"events.jsonl").exists()
