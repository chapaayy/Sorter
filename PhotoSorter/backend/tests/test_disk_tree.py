"""Independent physical root and deleted-open evidence, with real on-disk files."""
import os
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch

MAINTENANCE=Path(__file__).resolve().parents[2]/"tools/maintenance"
with patch.object(sys,"path",[str(MAINTENANCE),*sys.path]):
    import disk_tree
    import storage_check_history

def test_root_tree_disjoint_categories_and_mount_boundary(tmp_path):
    root=tmp_path/"root"
    for name in ("map/storage","var/lib/docker","var/lib/containerd","var/log","other","hidden"):
        (root/name).mkdir(parents=True,exist_ok=True)
        (root/name/"data").write_bytes(b"x"*8192)
    result=disk_tree.measure_disk(root/"map/storage",{"available":True,"root":str(root/"var/lib/docker")},
        root=root,mount_reader=lambda:{root/"hidden":{"id":"3"}},
        deleted_sampler=lambda _device:{"allocated_bytes":0,"files":0,"partial":True})
    assert result["excluded_mounts"]==1
    for key in ("map_storage","docker_engine","containerd_default","system_logs"):
        row=result[key]
        assert row["file_bytes"]==8192
    expected=int(subprocess.check_output(["du","-x","-B1","-s",str(root)],text=True).split()[0])
    hidden=int(subprocess.check_output(["du","-x","-B1","-s",str(root/"hidden")],text=True).split()[0])
    assert result["allocated_bytes"]==expected-hidden
    assert result["residual_bytes"]==result["capacity_after"]["used_bytes"]-result["allocated_bytes"]

def test_deleted_open_is_deduplicated_and_never_treated_as_complete(tmp_path):
    file=tmp_path/"data"
    file.write_bytes(b"x"*8192)
    with file.open("rb") as stream:
        file.unlink()
        actual=os.fstat(stream.fileno())
        fd=tmp_path/"proc/123/fd"
        fd.mkdir(parents=True)
        for name in ("1","2"):
            (fd/name).symlink_to("/proc/self/fd/"+str(stream.fileno()))
        result=disk_tree.deleted_open(actual.st_dev,proc=tmp_path/"proc")
        assert result["files"]==1
        assert result["allocated_bytes"]==actual.st_blocks*512
        assert result["partial"]

def test_history_is_bounded_and_preserves_partial_unknown():
    old={"tree_history":[{"finished_at":str(i),"comparable":True} for i in range(336)]}
    sample={"finished_at":"new","comparable":False,"absolute_discrepancy_bytes":None}
    result=storage_check_history.tree_history(old,sample)
    assert len(result)==336
    assert result[-1]["absolute_discrepancy_bytes"] is None
    assert result[-1]["comparable"] is False
    assert storage_check_history.tree_history({"tree_history":result},sample)==result
