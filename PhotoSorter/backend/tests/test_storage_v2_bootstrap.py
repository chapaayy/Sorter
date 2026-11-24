import importlib.util
import os
from pathlib import Path
import pytest

script=Path(__file__).resolve().parents[2]/"tools/maintenance/bootstrap_storage.py"
spec=importlib.util.spec_from_file_location("bootstrap_storage_test",script)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def bootstrap(root,**kwargs):
    module.bootstrap(root, host_uid=os.getuid(),host_gid=os.getgid(),
                     app_uid=os.getuid(),app_gid=os.getgid(),**kwargs)

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
    bootstrap(root,check=True)
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


def test_root_bootstrap_refuses_symlinked_app_directory(tmp_path):
    root=tmp_path/"storage"
    bootstrap(root)
    outside=tmp_path/"outside"
    outside.mkdir()
    (root/"app/users").rmdir()
    (root/"app/users").symlink_to(outside,target_is_directory=True)
    with pytest.raises((OSError,ValueError)):
        bootstrap(root)
    assert list(outside.iterdir())==[]
    with pytest.raises((OSError,ValueError)):
        bootstrap(root,check=True)

def test_read_only_check_does_not_recreate_missing_dir(tmp_path):
    root=tmp_path/"storage"
    bootstrap(root)
    (root/"app/users").rmdir()
    with pytest.raises(FileNotFoundError):
        bootstrap(root,check=True)
    assert not (root/"app/users").exists()
    bootstrap(root)
    assert (root/"app/users").is_dir()


def test_secure_umask_does_not_make_shared_activity_lock_unreadable(tmp_path):
    root=tmp_path/"storage"
    before=os.umask(0o077)
    try:bootstrap(root)
    finally:os.umask(before)
    lock=root/"system/updater/control/activity.lock"
    inode=lock.stat().st_ino
    assert lock.stat().st_mode&0o777==0o644
    bootstrap(root,check=True)
    bootstrap(root)
    assert lock.stat().st_ino==inode
