import importlib.util
import os
from pathlib import Path
import pytest

script=Path(__file__).resolve().parents[2]/"tools/maintenance/bootstrap_storage.py"
spec=importlib.util.spec_from_file_location("bootstrap_storage_test",script)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def bootstrap(root):
    module.bootstrap(root, host_uid=os.getuid(),host_gid=os.getgid(),
                     app_uid=os.getuid(),app_gid=os.getgid())

def test_repeat_bootstrap_preserves_data(tmp_path):
    root=tmp_path/"storage"
    bootstrap(root)
    marker=root/"system/state/layout-version"
    assert marker.read_text()=="2\n"
    assert marker.stat().st_mode & 0o777==0o600
    secret=root/"system/backups/updater"
    assert secret.stat().st_mode & 0o777==0o700
    data=root/"app/users/example"
    data.write_bytes(b"keep")
    inode=data.stat().st_ino
    bootstrap(root)
    assert data.read_bytes()==b"keep" and data.stat().st_ino==inode
    marker.write_text("3\n")
    with pytest.raises(ValueError,match="Incompatible"):
        bootstrap(root)

def test_unmarked_nonempty_and_symlink_roots_rejected(tmp_path):
    root=tmp_path/"storage"
    root.mkdir(mode=0o750)
    (root/"unknown").write_bytes(b"preserve")
    with pytest.raises(ValueError,match="Nonempty"):
        bootstrap(root)
    link=tmp_path/"link"
    link.symlink_to(root,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"):
        bootstrap(link)
    assert (root/"unknown").read_bytes()==b"preserve"
