"""Prove MAP snapshot ownership from kernel mounts, not folder-name guesses."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "maintenance" / "audit_containerd.py"
spec = importlib.util.spec_from_file_location("map_containerd_test", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_mountinfo_maps_running_map_upper_and_shared_lower(tmp_path):
    snaps = tmp_path / "containerd" / "io.containerd.snapshotter.v1.overlayfs"
    upper = snaps / "snapshots" / "32" / "fs"
    lower = snaps / "snapshots" / "12" / "fs"
    for path in (upper, lower):
        path.mkdir(parents=True)
    proc = tmp_path / "proc"
    mountinfo = proc / "77" / "mountinfo"
    mountinfo.parent.mkdir(parents=True)
    mountinfo.write_text(
        "123 2 0:100 / / rw - overlay overlay rw,"
        f"lowerdir={lower},upperdir={upper},workdir={upper.parent/'work'}\n",
        encoding="utf-8",
    )
    image = {"Id": "sha256:" + "a"*64,
             "RootFS": {"Layers": ["sha256:"+"b"*64]}}
    out = module.collect(
        [{"Name": "/outdoor-sorter-worker-1", "Id":"c"*64,"State":{"Pid":77}}],
        [image], proc, snaps,
        ctr_available=True,
        ctr_runner=lambda namespace: (
            "KEY  PARENT  KIND\n" +
            "sha256:" + "b"*64 + "  -  Committed\n"
        ),
    )
    assert out["snapshots"]["32"]["category"] == "containerd_active_upper"
    assert out["snapshots"]["12"]["category"] == "containerd_shared_image_layer"
    assert "outdoor-sorter-worker-1" in out["snapshots"]["32"]["owners"]
    assert out["container_mount_references"] == 2
    assert out["image_chains_checked"] == 1
    assert out["image_chains_matched"] == 1
    assert out["ctr_snapshot_metadata_checked"] is True
    assert out["snapshot_keys_listed"] == 1
    assert "ctr_snapshot_mounts" not in out["snapshots"]["12"]["sources"]


def test_unmatched_blobs_and_missing_mounts_are_not_assigned_to_map(tmp_path):
    snaps = tmp_path / "snapshots_root"
    snaps.mkdir()
    result = module.collect(
        [{"Name":"/outdoor-sorter-api-1","State":{"Pid":101}}],
        [], tmp_path/"missing_proc", snaps, ctr_available=False,
    )
    assert result["snapshots"] == {}
    assert result["warnings"]
    assert module.snapshot_from_file(
        snaps/"snapshots"/"11"/"fs"/"one.dll",snaps
    ) == "11"
    assert module.snapshot_from_file(tmp_path/"other"/"11",snaps) is None


def test_ctr_metadata_failure_is_explicit_and_does_not_claim_zero_matches(tmp_path):
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    def unavailable(_namespace):
        raise RuntimeError("ctr service unavailable")
    result = module.collect(
        [], [{"Id":"sha256:"+"a"*64,
               "RootFS":{"Layers":["sha256:"+"b"*64]}}],
        tmp_path/"proc", snaps,
        ctr_available=True, ctr_runner=unavailable,
    )
    assert result["ctr_snapshot_metadata_checked"] is False
    assert result["image_chains_matched"] is None
    assert any("Cannot query ctr" in message for message in result["warnings"])
    assert result["snapshots"] == {}


def test_snapshot_key_parser_does_not_guess_numeric_filesystem_ids():
    keys = module.parse_snapshot_keys(
        "KEY PARENT KIND\n"
        "sha256:" + "1"*64 + " - Committed\n"
        "not-a-digest - Active\n"
    )
    assert keys == {"sha256:" + "1"*64}
