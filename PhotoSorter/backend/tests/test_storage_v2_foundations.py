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


def test_injected_config_and_category_bootstrap(tmp_path):
    from app.storage.config import StorageConfig
    from app.storage.categories import APP_BOOTSTRAP_DIRS
    root = tmp_path / "app"
    config = StorageConfig(root)
    config.ensure_dirs()
    assert config.data == root / "state"
    assert config.models == root / "models"
    assert all((root / key).is_dir() for key in APP_BOOTSTRAP_DIRS)
    assert not (tmp_path / "Models").exists()
    assert not (tmp_path / "PhotoSorter/data").exists()

def test_existing_owned_paths_reject_internal_symlinks(tmp_path):
    from server.storage.paths import owned_file, owned_directory
    (tmp_path / "real").mkdir()
    (tmp_path / "real/photo.jpg").write_bytes(b"keep")
    (tmp_path / "alias").symlink_to(tmp_path / "real", target_is_directory=True)
    for check in (owned_file, owned_directory):
        with pytest.raises(ValueError):
            check(tmp_path / "alias/photo.jpg", tmp_path)
        with pytest.raises(ValueError):
            check(tmp_path / "real/../real/photo.jpg", tmp_path)


def test_publish_and_unlink_refuse_nonregular_targets(tmp_path):
    from app.storage.filesystem import atomic_publish, safe_unlink
    with atomic_write(tmp_path, "staged/a") as stream:
        stream.write(b"payload")
    (tmp_path / "published").mkdir()
    sentinel=tmp_path / "sentinel"
    sentinel.write_bytes(b"keep")
    (tmp_path / "published/a").symlink_to(sentinel)
    with pytest.raises(ValueError):
        atomic_publish(tmp_path, "staged/a", "published/a")
    with pytest.raises(ValueError):
        safe_unlink(tmp_path, "published/a")
    with pytest.raises(ValueError):
        with atomic_write(tmp_path, "published/a") as stream:
            stream.write(b"bad")
    assert sentinel.read_bytes()==b"keep"
    assert (tmp_path / "staged/a").read_bytes()==b"payload"
    (tmp_path / "published/a").unlink()
    atomic_publish(tmp_path, "staged/a", "published/a")
    assert not (tmp_path / "staged/a").exists()
    assert (tmp_path / "published/a").read_bytes()==b"payload"
    safe_unlink(tmp_path, "published/a")
    assert not (tmp_path / "published/a").exists()


def test_model_roots_never_fall_back_to_operator_home(tmp_path,monkeypatch):
    from app.system import model_store
    cache=tmp_path/"cache"
    weights=tmp_path/"models"
    monkeypatch.setattr(model_store,"MODEL_CACHE_DIR",cache)
    monkeypatch.setattr(model_store,"WEIGHTS_DIR",weights)
    monkeypatch.setenv("PHOTOSORTER_LEGACY_DATA",str(tmp_path/"old"))
    monkeypatch.setenv("TORCH_HOME",str(tmp_path/"old/torch"))
    monkeypatch.setenv("HF_HUB_CACHE",str(tmp_path/"old/hf"))
    assert model_store.torch_roots()==[cache/"torch/hub"]
    assert model_store.hf_roots()==[cache/"huggingface/hub"]
    for name in ("HOME","XDG_CACHE_HOME","HF_HOME","HF_XET_CACHE","HF_HUB_OFFLINE","HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(name,"test-before")
    model_store.configure_model_environment()
    assert os.environ["TORCH_HOME"]==str(cache/"torch")
    assert os.environ["HF_HUB_CACHE"]==str(cache/"huggingface/hub")


def test_pipeline_stage_cleanup_and_retry(tmp_path,monkeypatch):
    from app import config
    from app.storage.temporary import pipeline_directory
    monkeypatch.setattr(config,"APP_STORAGE_ROOT",tmp_path)
    task=uuid.uuid4()
    key=app_key(Category.TRANSCODE_TEMP,task_id=task).relative
    abandoned=tmp_path/key
    abandoned.mkdir(parents=True)
    (abandoned/"old.part").write_bytes(b"stale")
    with pytest.raises(RuntimeError):
        with pipeline_directory(Category.TRANSCODE_TEMP,task_id=task) as stage:
            assert stage==abandoned
            assert not list(stage.iterdir())
            (stage/"new.part").write_bytes(b"partial")
            raise RuntimeError("failed conversion")
    assert not abandoned.exists()
    outside=tmp_path/"outside"
    outside.mkdir()
    (outside/"keep").write_bytes(b"keep")
    abandoned.symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):
        with pipeline_directory(Category.TRANSCODE_TEMP,task_id=task):
            pass
    assert (outside/"keep").read_bytes()==b"keep"


def test_owner_scoped_original_and_normalized_paths(tmp_path,monkeypatch):
    from app import config
    from server.storage.paths import original_path,normalized_path,part_path,batch_dir
    monkeypatch.setattr(config,"APP_STORAGE_ROOT",tmp_path)
    batch,upload=uuid.uuid4(),uuid.uuid4()
    first=original_path(batch,upload,"jpg",1)
    second=original_path(batch,upload,"jpg",2)
    assert first!=second
    assert first.parent==batch_dir(batch,1)
    assert first==tmp_path/f"users/1/batches/{batch}/originals/{upload}.jpg"
    assert normalized_path(batch,upload,"png",1)==tmp_path/f"users/1/batches/{batch}/normalized/{upload}.png"
    assert part_path(batch,upload)==tmp_path/f"temporary/uploads/fo/{batch}/{upload}.part"
    with pytest.raises(ValueError):
        original_path(batch,upload,"../jpg",1)
