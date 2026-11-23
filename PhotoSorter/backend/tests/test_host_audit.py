"""Host-side audit tests with a disposable fake Docker tree, never real Docker."""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "maintenance" / "audit_host.py"
spec = importlib.util.spec_from_file_location("host_audit", SCRIPT)
host_audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = host_audit
spec.loader.exec_module(host_audit)


def test_host_audit_sees_app_postgres_caddy_overlay_images_and_host_tmp(tmp_path):
    project = tmp_path / "Sorter"
    data = project / "PhotoSorter" / "data"
    photo = data / "uploads" / "batch" / "photo.jpg"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"photo" * 2048)
    normalized = data / "uploads" / "batch" / ".normalized" / "photo.jpg"
    normalized.parent.mkdir()
    normalized.write_bytes(b"jpg" * 300)
    output = data / "outputs" / "run" / "megaloc" / "SAM 0004" / "photo.jpg"
    output.parent.mkdir(parents=True)
    os.link(photo, output)
    model = project / "Models" / "models" / "megaloc" / "model.safetensors"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    docker = tmp_path / "docker"
    postgres = docker / "volumes" / "outdoor-sorter_postgres_data" / "_data"
    wal = postgres / "pg_wal" / "000000010000000000000001"
    wal.parent.mkdir(parents=True)
    wal.write_bytes(b"wal" * 300)
    caddy = docker / "volumes" / "outdoor-sorter_caddy_data" / "_data"
    cert = caddy / "certificates" / "example.crt"
    cert.parent.mkdir(parents=True)
    cert.write_bytes(b"cert")
    upper = docker / "overlay2" / "upper-app" / "diff"
    cache = upper / "tmp" / "ffmpeg-index.part"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"frame")
    image_id = "sha256:" + "a" * 64
    layer_hash = "sha256:" + "1" * 64
    layerdb = docker / "image" / "overlay2" / "layerdb" / "sha256" / ("1" * 64) / "cache-id"
    layerdb.parent.mkdir(parents=True)
    layerdb.write_text("layer-app")
    image_file = docker / "overlay2" / "layer-app" / "diff" / "usr" / "bin" / "python3"
    image_file.parent.mkdir(parents=True)
    image_file.write_bytes(b"python")
    meta = docker / "containers" / ("b" * 64) / "config.v2.json"
    meta.parent.mkdir(parents=True)
    meta.write_bytes(b"{}")
    other = docker / "buildkit" / "cache.db"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"other-possible-shared")
    host_tmp = tmp_path / "host-tmp"
    host_tmp.mkdir()
    shared = host_tmp / "strange.part"
    shared.write_bytes(b"temp")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("DO_NOT_READ")
    (host_tmp / "link").symlink_to(outside, target_is_directory=True)
    proc = tmp_path / "proc"
    proc.mkdir()

    def fake(*args):
        key = tuple(args)
        if key == ("info", "--format", "{{json .}}"):
            return json.dumps({"DockerRootDir": str(docker), "Driver": "overlay2"})
        if args[:2] == ("ps", "-aq"):
            return "b" * 64 + "\n"
        if args[0] == "inspect":
            return json.dumps([{
                "Id": "b" * 64,
                "Name": "/outdoor-sorter-api-1",
                "Image": image_id,
                "GraphDriver": {"Data": {"UpperDir": str(upper)}},
                "State": {"Pid": 0},
                "Mounts": [
                    {"Type": "volume", "Name": "outdoor-sorter_postgres_data",
                     "Source": str(postgres)},
                    {"Type": "volume", "Name": "outdoor-sorter_caddy_data",
                     "Source": str(caddy)}
                ],
            }])
        if args[:3] == ("volume", "ls", "-q"):
            return "outdoor-sorter_postgres_data\noutdoor-sorter_caddy_data"
        if args[:2] == ("volume", "inspect"):
            return json.dumps([
                {"Name": "outdoor-sorter_postgres_data", "Mountpoint": str(postgres)},
                {"Name": "outdoor-sorter_caddy_data", "Mountpoint": str(caddy)}
            ])
        if args[:2] == ("image", "inspect"):
            return json.dumps([{"RootFS": {"Layers": [layer_hash]}}])
        if args[:2] == ("system", "df"):
            return json.dumps({"Type": "Build Cache", "Size": "5GB"}) + "\n"
        raise AssertionError("Unexpected Docker command: " + repr(key))

    before_photo = photo.stat().st_mtime_ns
    audit = host_audit.HostAudit(project, call=fake,
                                shared_roots=[host_tmp], proc_root=proc)
    audit.host_dependencies = lambda writer: None
    result = audit.execute()
    assert photo.stat().st_mtime_ns == before_photo
    assert result["files_scanned"] >= 10
    assert result["scopes"]["app"]["allocated_bytes"] > 0
    assert result["scopes"]["app_shared_layer"]["allocated_bytes"] > 0
    assert result["scopes"]["shared_unattributed"]["allocated_bytes"] > 0
    assert result["categories"]["docker_volume"]["files"] >= 2
    assert result["categories"]["container_writable_layer"]["files"] >= 1
    assert result["categories"]["model_weights"]["files"] >= 1
    assert result["categories"]["normalized"]["files"] == 1
    report_dir = data / "audits" / "host"
    rows = list(csv.DictReader((report_dir / "latest.csv").open(encoding="utf-8-sig"), delimiter=";"))
    assert any(r["path"] == str(wal) for r in rows)
    assert any(r["path"] == str(cert) for r in rows)
    assert any(r["path"] == str(image_file) and r["category"] == "docker_image_layer" for r in rows)
    assert not any("secret.txt" in r["path"] for r in rows)
    by_path = {r["path"]: r for r in rows}
    assert (int(by_path[str(photo)]["allocated_bytes"]) +
            int(by_path[str(output)]["allocated_bytes"])) == photo.stat().st_blocks * 512
    assert json.loads((report_dir / "latest.json").read_text())["schema"] == "map-host-audit-v1"
    assert result["limitations"], "A point-in-time scan cannot claim complete event history"


def test_missing_docker_is_reported_not_silently_dropped(tmp_path):
    project = tmp_path / "Sorter"
    (project / "PhotoSorter" / "data").mkdir(parents=True)
    proc = tmp_path / "proc"
    proc.mkdir()

    def broken(*args):
        raise RuntimeError("Docker socket unavailable")

    audit = host_audit.HostAudit(project, call=broken, shared_roots=[], proc_root=proc)
    audit.host_dependencies = lambda writer: None
    summary = audit.execute()
    assert summary["errors"]
    assert summary["docker"]["containers"] == 0
    assert summary["files_scanned"] > 0
