"""Read-only attribution of containerd overlayfs snapshots to MAP.

Filesystem attribution only when backed by kernel overlay mount metadata
from running MAP containers. An independent read-only ctr snapshot key list
verifies image chain metadata but does not guess a numeric disk snapshot ID. An image layer can be shared by other applications: never call it
exclusive. Compressed content-store blobs are NOT identified by snapshot IDs.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

_LAYER_RE = re.compile(r"/snapshots/([0-9]+)/(?:fs|work)(?:\b|/)")
_OPTIONS_RE = re.compile(r"(?:^|[,\s])(upperdir|lowerdir)=([^,\s]+)")


def overlay_paths(raw: str):
    """Parse the kernel overlay mount options or 'ctr snapshots mounts' text."""
    results = []
    for line in raw.splitlines():
        if " - " in line:  # /proc/PID/mountinfo: options after the separator
            before, after = line.split(" - ", 1)
            if not after.startswith("overlay "):
                continue
            options = after
        elif "upperdir=" in line or "lowerdir=" in line:  # ctr mount instructions
            options = line
        else:
            continue
        opts = dict(_OPTIONS_RE.findall(options))
        upper = opts.get("upperdir")
        if upper:
            results.append(("upper", upper.replace("\\040", " ")))
        for lower in opts.get("lowerdir", "").split(":"):
            if lower:
                results.append(("lower", lower.replace("\\040", " ")))
    return results


def snapshot_id(path: str, root: Path):
    """Accept only paths inside this configured containerd snapshotter."""
    root = root.resolve(strict=False)
    value = Path(path)
    try:
        relative = value.relative_to(root)
    except ValueError:
        return None
    if len(relative.parts) >= 3 and relative.parts[0] == "snapshots" and (
        relative.parts[1].isdigit() and relative.parts[2] in ("fs", "work")
    ):
        return relative.parts[1]
    return None


def image_chains(image: dict):
    previous = ""
    for diff in image.get("RootFS", {}).get("Layers", []) or []:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", diff):
            continue
        chain = diff if not previous else "sha256:" + hashlib.sha256(
            (previous + " " + diff).encode("ascii")
        ).hexdigest()
        previous = chain
        yield chain


def parse_snapshot_keys(text: str):
    """Read committed chain keys from the output of ctr snapshots ls."""
    found = set()
    for line in text.splitlines():
        columns = line.split()
        if columns and re.fullmatch(r"sha256:[0-9a-f]{64}", columns[0]):
            found.add(columns[0])
    return found


def _ctr_snapshot_keys(namespace: str):
    """One read-only metadata query. Never call ctr snapshots mounts here."""
    result = subprocess.run(
        ["ctr", "--namespace", namespace, "snapshots", "ls"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
    )
    if result.returncode:
        raise RuntimeError("ctr snapshots ls failed: " + result.stderr.strip()[:160])
    return result.stdout


def collect(containers: list, images: list, proc_root: Path, snapshot_root: Path,
            *, ctr_runner=None, ctr_available=None, namespace="moby"):
    """Return safe attribution metadata and explicit unresolved coverage.

    Does not open snapshot data or mount anything. image layer references can
    be shared and are never categorized as exclusive MAP storage.
    """
    if ctr_runner is None:
        ctr_runner = _ctr_snapshot_keys
    if ctr_available is None:
        ctr_available = shutil.which("ctr") is not None
    evidence = defaultdict(lambda: {"owners": set(), "roles": set(), "sources": set()})
    warnings = []
    container_mounts = 0
    image_chains_checked = 0
    image_chains_matched = None
    snapshot_keys_listed = 0
    ctr_snapshot_metadata_checked = False
    for container in containers:
        name = container.get("Name", "").lstrip("/") or container.get("Id", "")[:12]
        pid = int(container.get("State", {}).get("Pid") or 0)
        found = set()
        if pid > 0:
            try:
                raw = (proc_root / str(pid) / "mountinfo").read_text(encoding="utf-8")
                for role, path in overlay_paths(raw):
                    sid = snapshot_id(path, snapshot_root)
                    if sid:
                        found.add((sid, role))
            except OSError as exc:
                warnings.append("Unable to read mountinfo for " + name + ": " + str(exc)[:140])
        else:
            warnings.append("Container not running: " + name)
        # Legacy GraphDriver metadata is still useful if supplied.
        data = container.get("GraphDriver", {}).get("Data", {}) or {}
        if isinstance(data, dict):
            for key in ("UpperDir", "LowerDir"):
                for path in str(data.get(key) or "").split(":"):
                    sid = snapshot_id(path, snapshot_root)
                    if sid:
                        found.add((sid, "upper" if key == "UpperDir" else "lower"))
        for sid, role in found:
            entry = evidence[sid]
            entry["owners"].add(name)
            entry["roles"].add("active_upper" if role == "upper" else "referenced_lower")
            entry["sources"].add("kernel_mountinfo")
        container_mounts += len(found)
        if pid > 0 and not found:
            warnings.append("No containerd overlay mounts mapped for " + name)

    unique_images = {}
    for image in images:
        identity = image.get("Id") or (image.get("RepoTags") or [""])[0]
        if identity:
            unique_images[identity] = image
    chains = set()
    for image in unique_images.values():
        chains.update(image_chains(image))
    image_chains_checked = len(chains)

    if ctr_available and chains:
        try:
            # ctr snapshots mounts <target> <key> may activate mounts. We must
            # NOT invoke that command for a read-only filesystem audit.
            keys = parse_snapshot_keys(ctr_runner(namespace))
            ctr_snapshot_metadata_checked = True
            snapshot_keys_listed = len(keys)
            image_chains_matched = len(chains.intersection(keys))
            if image_chains_matched < image_chains_checked:
                warnings.append(
                    "Only " + str(image_chains_matched) + "/" +
                    str(image_chains_checked) +
                    " distinct MAP image chain keys found in ctr snapshot listing; "
                    "unmatched does not mean unused"
                )
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            warnings.append("Cannot query ctr snapshot metadata: " + str(exc)[:160])
    elif not ctr_available:
        warnings.append("ctr unavailable; image snapshot metadata not verified")
    result = {}
    for sid, detail in evidence.items():
        roles = sorted(detail["roles"])
        # Current running container writes have precedence over immutable layers.
        category = ("containerd_active_upper" if "active_upper" in roles else
                    "containerd_shared_image_layer")
        result[sid] = {
            "category": category,
            "owners": sorted(detail["owners"]),
            "roles": roles,
            "sources": sorted(detail["sources"]),
        }
    if not result:
        warnings.append("No containerd snapshot could be associated with MAP")
    return {
        "snapshots": result,
        "container_mount_references": container_mounts,
        "image_chains_checked": image_chains_checked,
        "image_chains_matched": image_chains_matched,
        "ctr_available": bool(ctr_available),
        "ctr_snapshot_metadata_checked": ctr_snapshot_metadata_checked,
        "snapshot_keys_listed": snapshot_keys_listed,
        "warnings": list(dict.fromkeys(warnings)),
        "limitations": [
            "Shared image snapshots may be used by other applications.",
            "Compressed content blobs and unreferenced snapshots remain unattributed.",
            "An active container's upper snapshot is attributed from kernel overlay mount options.",
            "Missing mount metadata is a coverage gap, not evidence that a file is unused.",
            "ctr snapshot keys do not identify numeric snapshot directories; kernel mounts establish that connection.",
            "No mount, prepare, view, or other mutable ctr commands are used.",
        ],
    }


def snapshot_from_file(path: Path, snapshot_root: Path):
    try:
        parts = path.relative_to(snapshot_root).parts
    except ValueError:
        return None
    if len(parts) >= 2 and parts[0] == "snapshots" and parts[1].isdigit():
        return parts[1]
    return None
