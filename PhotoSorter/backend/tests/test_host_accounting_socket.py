"""The live updater RPC endpoint is known, but other special nodes are not."""
import importlib.util
import json
from pathlib import Path
import socket

import pytest

ROOT=Path(__file__).resolve().parents[3]
SPEC=importlib.util.spec_from_file_location("host_accounting_socket_test",ROOT/"PhotoSorter/tools/maintenance/host_accounting.py")
host=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)
CONTRACT=json.loads((ROOT/"docs/storage-layout-v2.json").read_text())

@pytest.mark.parametrize("kind",["socket","file","symlink","fifo"])
def test_only_exact_live_rpc_socket_is_known(tmp_path,kind):
    import os
    # Short relative bind paths avoid AF_UNIX's 108-byte pathname limit in CI.
    for directory in ("app","logs","infrastructure","system/updater/rpc"):
        (tmp_path/directory).mkdir(parents=True)
    import contextlib
    rpc=tmp_path/"system/updater/rpc/control.sock"
    other=tmp_path/"system/updater/rpc/other.sock"
    with contextlib.ExitStack() as stack:
        # Bind relative to cwd, restoring cwd before sampling.
        cwd=os.getcwd()
        try:
            os.chdir(rpc.parent)
            s=stack.enter_context(socket.socket(socket.AF_UNIX,socket.SOCK_STREAM))
            s.bind("other.sock")
            if kind=="socket":
                live=stack.enter_context(socket.socket(socket.AF_UNIX,socket.SOCK_STREAM))
                live.bind("control.sock")
                live.listen(1)
            elif kind=="file":rpc.write_bytes(b"unexpected")
            elif kind=="symlink":rpc.symlink_to(other)
            else:os.mkfifo(rpc)
        finally:os.chdir(cwd)
        report=host.measure(tmp_path,CONTRACT,include_engine=False)
        assert not report["partial"]
        assert report["errors"]==0
        unknown={x["path"] for x in report["unknown_sample"]}
        assert "system/updater/rpc/other.sock" in unknown
        if kind=="socket":
            assert "system/updater/rpc/control.sock" not in unknown
            assert report["categories"]["updater_rpc_socket"]=={
                "files":1,"logical_bytes":rpc.lstat().st_size,
                "allocated_bytes":rpc.lstat().st_blocks*512,"hardlink_paths":0}
            assert report["devices"][str(rpc.lstat().st_dev)]["files"]==2
            # Sampling must not disturb the real RPC endpoint.
            assert rpc.exists()
        else:
            assert "system/updater/rpc/control.sock" in unknown
            assert "updater_rpc_socket" not in report["categories"]
