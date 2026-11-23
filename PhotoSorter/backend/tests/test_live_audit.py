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
