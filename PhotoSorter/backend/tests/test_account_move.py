import os
import pytest
from server.services.account_move import move, fingerprint, rewrite
from app.storage.filesystem import parent_fd
from server.storage.paths import owned_directory

@pytest.mark.parametrize("kind",["file","directory"])
def test_replay_preserves_inode(tmp_path,kind):
    source=tmp_path/"old"/"data"
    source.parent.mkdir()
    if kind=="directory":
        source.mkdir()
        (source/"photo").write_bytes(b"photo")
        os.link(source/"photo",source/"result")
    else:
        source.write_bytes(b"photo")
    entry={"src":"old/data","dst":"new/data","inode":fingerprint(source.stat()),"kind":kind}
    move(tmp_path,entry,parent_fd,owned_directory)
    move(tmp_path,entry,parent_fd,owned_directory)
    assert fingerprint((tmp_path/"new/data").stat())==entry["inode"]
    assert not source.exists()
    if kind=="directory":
        assert (tmp_path/"new/data/photo").read_bytes()==b"photo"
        assert (tmp_path/"new/data/photo").stat().st_ino==(tmp_path/"new/data/result").stat().st_ino

def test_collision_preserves_both(tmp_path):
    source=tmp_path/"old";source.write_bytes(b"old")
    dest=tmp_path/"new";dest.write_bytes(b"new")
    entry={"src":"old","dst":"new","inode":fingerprint(source.stat()),"kind":"file"}
    with pytest.raises(ValueError):
        move(tmp_path,entry,parent_fd,owned_directory)
    assert source.read_bytes()==b"old" and dest.read_bytes()==b"new"

def test_changed_source_refused(tmp_path):
    source=tmp_path/"old";source.write_bytes(b"original")
    entry={"src":"old","dst":"new","inode":fingerprint(source.stat()),"kind":"file"}
    source.rename(tmp_path/"saved")
    source.write_bytes(b"replacement")
    with pytest.raises(ValueError):
        move(tmp_path,entry,parent_fd,owned_directory)
    assert source.read_bytes()==b"replacement"

def test_rewrite_prefix_only():
    assert rewrite(["/app/users/1/a","/app/users/10/a","relative"],"/app/users/1","/app/users/7")==["/app/users/7/a","/app/users/10/a","relative"]
