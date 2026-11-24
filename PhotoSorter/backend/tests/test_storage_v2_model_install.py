"""Failure-path tests for the publication protocol, not model-inference tests."""
import hashlib
import errno
import pytest
from fastapi import HTTPException
from app import config
from app.system import model_store,downloads,technical_cache
from app.storage.categories import Category
from app.storage.paths import managed_prefix
from server.services import archive_cache

@pytest.fixture
def bundle(tmp_path,monkeypatch):
    monkeypatch.setattr(config,"APP_STORAGE_ROOT",tmp_path)
    source={"LICENSE":b"fixture license","hubconf.py":b"fixture hub","megaloc_model.py":b"fixture source"}
    weight=b"fixture bytes -- not a model"
    monkeypatch.setattr(model_store,"SOURCE_BLOBS",{k:hashlib.sha1(f"blob {len(v)}".encode()+bytes([0])+v).hexdigest() for k,v in source.items()})
    monkeypatch.setattr(model_store,"WEIGHT_SHA256",hashlib.sha256(weight).hexdigest())
    monkeypatch.setattr(model_store,"MAX_WEIGHT_BYTES",len(weight)+10)
    monkeypatch.setattr(archive_cache.disk_guard,"stat",lambda _: (10**12,10**11))
    def fetch(url,target,**kwargs):
        name=url.split("/")[-1].split("?")[0]
        target.write_bytes(weight if name==model_store.WEIGHT_NAME else source[name])
    monkeypatch.setattr(downloads,"_fetch",fetch)
    return source,weight

def assert_clean():
    assert not list(managed_prefix(Category.MODEL_DOWNLOAD).iterdir())

def test_model_install_no_space_before_network(bundle,monkeypatch):
    monkeypatch.setattr(archive_cache.disk_guard,"stat",lambda _: (10**9,0))
    monkeypatch.setattr(downloads,"_fetch",lambda *a,**k:pytest.fail("network called"))
    with pytest.raises(HTTPException) as error:downloads.Downloads().install()
    assert error.value.status_code==507
    assert not model_store.verification_path().exists()
    assert_clean()

@pytest.mark.parametrize("mode",["interrupted","wrong-digest","verify-failure"])
def test_failed_model_install_cleans_staging_and_does_not_publish(bundle,monkeypatch,mode):
    original=downloads._fetch
    def fetch(url,target,**kwargs):
        if model_store.WEIGHT_NAME in url and mode=="interrupted":
            target.write_bytes(b"partial")
            raise OSError(errno.EIO,"interrupted")
        original(url,target,**kwargs)
        if model_store.WEIGHT_NAME in url and mode=="wrong-digest":target.write_bytes(b"corrupt")
    monkeypatch.setattr(downloads,"_fetch",fetch)
    def fail_verify(*args):
        assert mode=="verify-failure"
        raise RuntimeError("verification failed")
    monkeypatch.setattr(downloads.Downloads,"_verify",fail_verify)
    with pytest.raises((OSError,ValueError,RuntimeError)):downloads.Downloads().install()
    assert not model_store.verification_path().exists()
    assert not model_store.weight_target().exists()
    assert_clean()

def test_protocol_marker_noop_and_explicit_cache_guard(bundle,monkeypatch):
    # This only tests installation state transitions with tiny fixture bytes.
    # The mandatory docker-runtime job executes the actual official model.
    monkeypatch.setattr(downloads.Downloads,"_verify",lambda *args:None)
    downloads.Downloads().install()
    assert model_store.verified()
    before=model_store.weight_target().stat().st_ino
    monkeypatch.setattr(downloads,"_fetch",lambda *a,**k:pytest.fail("unexpected repeat download"))
    downloads.Downloads().install()
    assert model_store.weight_target().stat().st_ino==before
    with technical_cache.runtime_guard():
        with pytest.raises(RuntimeError,match="Stop all"):technical_cache.clear_disposable()
    for provider in technical_cache.PROVIDERS:
        path=managed_prefix(Category.TECHNICAL_CACHE,provider=provider)
        path.mkdir(parents=True,exist_ok=True)
        (path/"cache").write_bytes(b"disposable")
    assert technical_cache.clear_disposable()==technical_cache.PROVIDERS
    assert model_store.verified() and model_store.weight_target().stat().st_ino==before
    assert_clean()

def test_unverified_bundle_never_allows_cache_purge(bundle):
    cache=managed_prefix(Category.TECHNICAL_CACHE,provider="torch")
    cache.mkdir(parents=True)
    (cache/"data").write_bytes(b"keep")
    with pytest.raises(RuntimeError,match="No verified"):technical_cache.clear_disposable()
    assert (cache/"data").read_bytes()==b"keep"
