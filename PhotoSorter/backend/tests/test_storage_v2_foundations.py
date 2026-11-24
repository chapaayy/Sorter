import os
import uuid
import pytest
from app.storage.categories import Category, CATEGORIES
from app.storage.paths import app_key, AppKey, relative_key
from app.storage.filesystem import atomic_write, safe_read, file_stat
from app.storage.temporary import temporary_operation

def test_typed_keys():
    batch, upload = uuid.uuid4(), uuid.uuid4()
    key = app_key(Category.FO_ORIGINAL, user_id=42, batch_uuid=batch, upload_uuid=upload, ext="jpg")
    assert str(key.relative) == f"users/42/batches/{batch}/originals/{upload}.jpg"
    for field, value in [("user_id", "../1"), ("batch_uuid", "bad"), ("ext", "x/y")]:
        fields = dict(user_id=42, batch_uuid=batch, upload_uuid=upload, ext="jpg")
        fields[field] = value
        with pytest.raises(ValueError):
            app_key(Category.FO_ORIGINAL, **fields)
    with pytest.raises(ValueError):
        app_key(Category.REFERENCE_EMBEDDING, model_signature="short", prefix="aa", sha256="a"*64)
    with pytest.raises(ValueError):
        app_key(Category.REFERENCE_OBJECT, prefix="bb", sha256="a"*64)
    with pytest.raises(ValueError):
        AppKey(Category.FO_ORIGINAL, relative_key("shared/references/secret"))
    assert len(CATEGORIES) == 51

@pytest.mark.parametrize("key", ["../x", "/etc/passwd", "a/../b", "a//b", "a/./b", "a\\b", "a/"])
def test_traversal(key):
    with pytest.raises(ValueError):
        relative_key(key)

def test_atomic_and_links(tmp_path):
    with atomic_write(tmp_path, "originals/a") as stream:
        stream.write(b"original")
    (tmp_path / "results").mkdir()
    os.link(tmp_path / "originals/a", tmp_path / "results/a")
    assert file_stat(tmp_path, "originals/a") == file_stat(tmp_path, "results/a")
    with pytest.raises(RuntimeError):
        with atomic_write(tmp_path, "originals/a") as stream:
            stream.write(b"bad")
            raise RuntimeError()
    assert (tmp_path / "originals/a").read_bytes() == b"original"
    with atomic_write(tmp_path, "originals/a") as stream:
        stream.write(b"new")
    assert (tmp_path / "results/a").read_bytes() == b"original"
    assert list((tmp_path / "originals").iterdir()) == [tmp_path / "originals/a"]

def test_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_bytes(b"secret")
    (root / "jump").symlink_to(outside, target_is_directory=True)
    (root / "file").symlink_to(outside / "secret")
    for path in ("jump/secret", "file"):
        with pytest.raises(OSError):
            with safe_read(root, path):
                pass
    with pytest.raises(OSError):
        with atomic_write(root, "jump/secret"):
            pass
    assert (outside / "secret").read_bytes() == b"secret"

def test_temporary_cleanup(tmp_path):
    with pytest.raises(RuntimeError):
        with temporary_operation(tmp_path, "worker") as path:
            (path / "file").write_bytes(b"x")
            raise RuntimeError()
    assert not path.exists()
