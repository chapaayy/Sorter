#!/usr/bin/env python3
"""Read-only health acceptance on the disposable Stage 10 Ubuntu guest.

Docker-native health is mandatory where configured (PostgreSQL/API).
Caddy must serve real HTTPS; workers must have fresh, advancing database
heartbeats from new instances. Never equate missing Health with healthy.
No Docker/systemd start, restart, or repair commands are issued here.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

SERVICES = ("postgres", "api", "caddy", "worker", "thumbnail", "cleanup")
ROLES = {"worker": "megaloc", "thumbnail": "thumbnail", "cleanup": "cleanup"}
NATIVE = {"postgres", "api"}
UNITS = ("docker.service", "map-updater.service", "map-log-maintenance.timer")
PROJECT = "outdoor-sorter"
COOKIE = "/root/stage10-cookie"


def run(*args, timeout=12):
    return subprocess.check_output(
        args, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, timeout=timeout,
    ).strip()


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def container_status(container, service, boot_time):
    state = container["State"]
    native = (container["Config"].get("Healthcheck") or {}).get("Test", [])
    configured = bool(native and native[0] != "NONE")
    health = (state.get("Health") or {}).get("Status")
    result = {
        "id": container["Id"], "state": state.get("Status"),
        "native_configured": configured, "native_health": health,
        "started_at": state.get("StartedAt"), "restarts": container.get("RestartCount"),
    }
    errors = []
    if not state.get("Running") or state.get("Restarting") or state.get("Status") != "running":
        errors.append("not running")
    if service in NATIVE and not configured:
        errors.append("required native healthcheck missing")
    if configured and health != "healthy":
        errors.append("native health not healthy")
    if timestamp(result["started_at"]) < boot_time:
        errors.append("container start predates current boot")
    return result, errors


def https(path):
    return json.loads(run("curl", "-kfsS", "--max-time", "8", "-b", COOKIE,
                          "-H", "Origin: https://localhost", "https://localhost" + path))


def sample():
    errors = []
    snapshot = {"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                "containers": {}, "workers": {}, "units": {}}
    boot_time = int(next(line.split()[1] for line in Path("/proc/stat").read_text().splitlines()
                         if line.startswith("btime ")))
    for unit in UNITS:
        try:
            state = run("systemctl", "is-active", unit)
            enabled = run("systemctl", "is-enabled", unit)
            snapshot["units"][unit] = {"state": state, "enabled": enabled}
            if state != "active" or enabled != "enabled":
                errors.append(unit + " not active/enabled")
        except subprocess.SubprocessError:
            errors.append(unit + " not active/enabled")
    try:
        ids = run("docker", "ps", "-aq", "--filter",
                  "label=com.docker.compose.project=" + PROJECT).splitlines()
        containers = json.loads(run("docker", "inspect", "--type", "container", *ids)) if ids else []
    except (subprocess.SubprocessError, ValueError):
        containers = []
        errors.append("Docker inspect unavailable")
    for service in SERVICES:
        matches = [c for c in containers if
                   (c["Config"].get("Labels") or {}).get("com.docker.compose.service") == service]
        if len(matches) != 1:
            errors.append(service + ": expected exactly one container, found " + str(len(matches)))
            continue
        try:
            status, issues = container_status(matches[0], service, boot_time)
            snapshot["containers"][service] = status
            errors.extend(service + ": " + issue for issue in issues)
        except (KeyError, ValueError, TypeError):
            errors.append(service + ": invalid container state")
    # Independent real PostgreSQL query. Never print credentials or full inspect.
    try:
        pg = snapshot["containers"]["postgres"]["id"]
        sql = """SELECT json_build_object('now',clock_timestamp(),'workers',
            (SELECT json_object_agg(service,json_build_object('instance',instance_id,'seen',seen_at))
             FROM service_heartbeats WHERE service IN ('megaloc','thumbnail','cleanup')))"""
        db = json.loads(run("docker", "exec", pg, "psql", "-XAt", "-v", "ON_ERROR_STOP=1",
                            "-U", "sorter", "-d", "sorter", "-c", sql))
        now = timestamp(db["now"])
        snapshot["postgres_query"] = "ok"
        for service, role in ROLES.items():
            row = (db["workers"] or {}).get(role)
            if not row:
                errors.append(role + ": missing heartbeat")
                continue
            seen = timestamp(row["seen"])
            age = now - seen
            snapshot["workers"][role] = {"instance": row["instance"], "seen": row["seen"],
                                          "age_seconds": round(age, 3)}
            if not 0 <= age < 35:
                errors.append(role + ": stale heartbeat")
            started = snapshot["containers"].get(service, {}).get("started_at")
            if not started or seen < timestamp(started):
                errors.append(role + ": heartbeat predates container start")
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError):
        errors.append("PostgreSQL/heartbeat query unavailable")
    # Real proxy and authenticated API exercising DB-backed system status.
    try:
        require(https("/api/health").get("status") == "ok", "unhealthy HTTPS")
        snapshot["https_health"] = "ok"
        system = https("/api/system/status")
        for role in ROLES.values():
            if system["services"][role]["alive"] is not True:
                errors.append(role + ": API reports not alive")
        snapshot["system_api"] = "ok"
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError, RuntimeError):
        errors.append("HTTPS or authenticated system status failed")
    return snapshot, errors


def previous_errors(current, previous, mode):
    errors = []
    if previous is None:
        return errors
    if mode == "reboot" and current["boot_id"] == previous["boot_id"]:
        errors.append("boot ID did not change")
    if mode == "update" and current["boot_id"] != previous["boot_id"]:
        errors.append("unexpected reboot during update")
    for role in ROLES.values():
        old = previous["workers"].get(role, {}).get("instance")
        new = current["workers"].get(role, {}).get("instance")
        if not old or not new or old == new:
            errors.append(role + ": no new heartbeat instance")
    if mode == "reboot":
        for service in SERVICES:
            old = previous["containers"].get(service, {})
            new = current["containers"].get(service, {})
            if old.get("id") != new.get("id"):
                errors.append(service + ": reboot did not retain container identity")
    return errors


def advanced(current, earlier):
    return all(
        current["workers"][role]["instance"] == earlier["workers"][role]["instance"]
        and timestamp(current["workers"][role]["seen"]) > timestamp(earlier["workers"][role]["seen"])
        for role in ROLES.values()
    ) and all(current["containers"][name]["id"] == earlier["containers"][name]["id"]
              and current["containers"][name]["started_at"] == earlier["containers"][name]["started_at"]
              for name in SERVICES)


def self_test():
    base = {"Id": "fixture", "Config": {}, "State": {"Running": True, "Status": "running",
            "StartedAt": "2026-01-01T00:00:01Z"}, "RestartCount": 0}
    require(not container_status(base, "caddy", 0)[1], "unexpected native requirement")
    require(bool(container_status(base, "api", 0)[1]), "accepted missing native health")
    base["Config"]["Healthcheck"] = {"Test": ["CMD", "true"]}
    require(bool(container_status(base, "api", 0)[1]), "accepted missing health state")
    base["State"]["Health"] = {"Status": "starting"}
    require(bool(container_status(base, "api", 0)[1]), "accepted starting health")
    base["State"]["Health"]["Status"] = "healthy"
    require(not container_status(base, "api", 0)[1], "rejected healthy container")
    base["State"]["Running"] = False
    require(bool(container_status(base, "api", 0)[1]), "accepted stopped container")
    print("STAGE10_HEALTH_PROBE_SELF_TEST_OK", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--mode", choices=("baseline", "reboot", "update"), default="baseline")
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    require(os.geteuid() == 0 and Path("/root/stage10-ready").is_file()
            and Path("/sys/class/dmi/id/product_name").exists()
            and Path("/etc/hostname").read_text().strip() == "map-stage10",
            "disposable Ubuntu VM only")
    require(args.output is not None and (args.mode == "baseline" or args.previous is not None),
            "snapshot arguments required")
    previous = json.loads(args.previous.read_text()) if args.previous else None
    deadline = time.monotonic() + 240
    earlier = None
    while True:
        current, errors = sample()
        errors.extend(previous_errors(current, previous, args.mode))
        print("STAGE10_SERVICE_SAMPLE", args.mode, json.dumps(current, sort_keys=True),
              "errors=", json.dumps(errors), flush=True)
        if errors:
            earlier = None
        elif earlier is not None and advanced(current, earlier):
            args.output.write_text(json.dumps(current, indent=2))
            print("STAGE10_SERVICES_HEALTHY", args.mode,
                  "native=postgres,api https=caddy heartbeat=megaloc,thumbnail,cleanup",
                  flush=True)
            return
        elif earlier is None:
            earlier = current
        if time.monotonic() >= deadline:
            raise RuntimeError("Service health deadline exceeded; see all per-service samples")
        time.sleep(10)


if __name__ == "__main__":
    main()
