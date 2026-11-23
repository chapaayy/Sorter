"""Linux inotify observer records short-lived operations without app mutations."""
from __future__ import annotations
import importlib.util
import json
import os
import select
import struct
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "maintenance" / "audit_live.py"
spec = importlib.util.spec_from_file_location("map_live_audit_test", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_lifecycle_events_are_recorded_even_after_file_is_deleted(tmp_path):
    data = tmp_path/"PhotoSorter"/"data"
    data.mkdir(parents=True)
    observer=mod.LiveAudit(tmp_path,roots=[data],containers_fn=lambda _name: [])
    observer.init()
    try:
        observer.discover()
        path=data/"short-lived.part"
        with path.open("wb") as output:
            output.write(b"one"*1000)
        newpath=data/"short-lived-renamed.part"
        path.rename(newpath)
        newpath.unlink()
        assert select.select([observer.fd],[],[],2.0)[0]
        observer.process(os.read(observer.fd,65536))
        state=observer.state(running=True)
        assert state["events_by_type"]["create"]>=1
        assert state["events_by_type"]["close_write"]>=1
        assert state["events_by_type"]["move_from"]>=1
        assert state["events_by_type"]["move_to"]>=1
        assert state["events_by_type"]["delete"]>=1
        assert state["watched_directories"] >= 1
        assert state["queue_overflows"] == 0
        raw=(observer.report/"live-events.jsonl").read_text(encoding="utf-8")
        assert "short-lived.part" in raw and "short-lived-renamed.part" in raw
        assert all("audits/host/live-events" not in json.loads(line)["path"]
                   for line in raw.splitlines())
        assert "O_TMPFILE" in " ".join(state["limitations"])
    finally:
        if observer.stream:observer.stream.close()
        if observer.fd is not None:os.close(observer.fd)


def test_queue_overflow_is_visible_as_a_coverage_gap(tmp_path):
    (tmp_path/"PhotoSorter"/"data").mkdir(parents=True)
    observer=mod.LiveAudit(tmp_path,roots=[],containers_fn=lambda _name: [])
    observer.init()
    try:
        observer.process(struct.pack("iIII",-1,mod.IN_Q_OVERFLOW,0,0))
        state=observer.state()
        assert state["queue_overflows"] == 1
        assert state["events_by_type"]["queue_overflow"] == 1
    finally:
        observer.stream.close()
        os.close(observer.fd)


def test_postgres_shm_close_storm_is_summarized_without_losing_counts(tmp_path):
    data = tmp_path / "PhotoSorter" / "data"
    data.mkdir(parents=True)
    observer = mod.LiveAudit(tmp_path, roots=[], containers_fn=lambda _name: [])
    observer.init()
    try:
        shm = tmp_path / "proc" / "123" / "root" / "dev" / "shm" / "PostgreSQL.123456"
        shm.parent.mkdir(parents=True)
        shm.write_bytes(b"x" * 1024)
        observer.wd_paths[42] = (shm.parent, "map_container_tmp:outdoor-sorter-postgres-1")
        # Linux inotify pads event names to 4-byte boundaries.
        name = shm.name.encode()
        padded = name + b"\0" * ((4 - len(name) % 4) % 4)
        event = struct.pack("iIII", 42, mod.IN_CLOSE_WRITE, 0, len(padded)) + padded
        for _ in range(1000):
            observer.process(event)
        state = observer.state()
        assert state["postgres_shm_close_writes_aggregated"] == 1000
        assert state["postgres_shm_pending"] == 1000
        assert state["events_observed_including_aggregates"] >= 1000
        observer.flush_shm_batches()
        records = [json.loads(line) for line in
                   (observer.report / "live-events.jsonl").read_text().splitlines()]
        batch = [r for r in records if r["event"] == "postgres_shm_close_write_summary"]
        assert len(batch) == 1
        assert batch[0]["observed_close_writes"] == 1000
        assert batch[0]["logical_bytes"] == 1024
        assert not [r for r in records if r["event"] == "close_write"]
        assert observer.state()["postgres_shm_pending"] == 0
    finally:
        observer.stream.close()
        os.close(observer.fd)
