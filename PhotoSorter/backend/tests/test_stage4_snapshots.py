"""Backup/restore tested with fake pg clients and synthetic hardlinks, no real data."""
from __future__ import annotations
import importlib.util
import json
import hashlib
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace
import pytest

MODULE=Path(__file__).resolve().parents[2]/"tools"/"stage4"/"snapshot.py"
spec=importlib.util.spec_from_file_location("stage4_snapshot",MODULE)
snapshot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)
TEST_DB="postgresql://test_user:private_test_password@127.0.0.1:5432/sorter_test"
RESTORE_DB="postgresql://test_user:private_test_password@127.0.0.1:5432/sorter_restore_disposable"

@pytest.fixture
def project(tmp_path,monkeypatch):
    root=tmp_path/"project"
    (root/"PhotoSorter"/"data"/"references"/"SAM-0001").mkdir(parents=True)
    (root/"PhotoSorter"/"data"/"uploads"/"test-batch").mkdir(parents=True)
    (root/"Models"/"models"/"megaloc").mkdir(parents=True)
    (root/"Models"/"cache"/"torch"/"hub").mkdir(parents=True)
    (root/".env.generated").write_text("ADMIN_PASSWORD=synthetic\nPOSTGRES_PASSWORD=synthetic\n")
    (root/".env").write_text("DOMAIN=staging.invalid\n")
    (root/"compose.yaml").write_text("name: synthetic\n")
    source=root/"PhotoSorter"/"data"/"uploads"/"test-batch"/"photo.jpg"
    source.write_bytes(b"unchanged synthetic original")
    target=root/"PhotoSorter"/"data"/"references"/"SAM-0001"/"linked.jpg"
    os.link(source,target)
    # Deliberately simulate pg_dump/psql/pg_restore without connecting to production.
    commands=[]
    def fake_pg(args,url,*,capture=False):
        commands.append((args[0],url))
        if args[0]=="pg_dump":
            Path(args[args.index("--file")+1]).write_bytes(b"disposable PostgreSQL dump placeholder")
        if args[0]=="psql":return SimpleNamespace(stdout=b"0\n")
        return SimpleNamespace(stdout=b"")
    monkeypatch.setattr(snapshot,"pg_run",fake_pg)
    return root,source,target,commands

def test_backup_restore_verifies_checksum_and_inode(project,tmp_path):
    root,source,target,commands=project
    archive=tmp_path/"safe-backup"
    with pytest.raises(ValueError):snapshot.capture(root,archive,TEST_DB)
    assert not archive.exists()
    result=snapshot.capture(root,archive,TEST_DB,quiesced=True)
    assert result["files"]>=5
    assert snapshot.verify(archive)["verified"]
    with pytest.raises(ValueError):snapshot.restore_test(archive,tmp_path/"restore",RESTORE_DB)
    marker=tmp_path/".photosorter-staging-only"
    marker.write_text("STAGING_ONLY")
    restored=tmp_path/"restore"
    assert snapshot.restore_test(archive,restored,RESTORE_DB,confirmed=True)["restored"]
    a=restored/source.relative_to(root)
    b=restored/target.relative_to(root)
    assert a.read_bytes()==source.read_bytes()
    assert b.read_bytes()==target.read_bytes()
    assert a.stat().st_ino==b.stat().st_ino
    assert ("pg_dump",TEST_DB) in commands and ("pg_restore",RESTORE_DB) in commands

def test_backup_refuses_symlinks_and_project_internal_destination(project,tmp_path):
    root,source,target,commands=project
    with pytest.raises(ValueError):
        snapshot.capture(root,root/"data-backup",TEST_DB,quiesced=True)
    evil=source.parent/"symlink.jpg"
    evil.symlink_to(tmp_path/"outside")
    with pytest.raises(ValueError):
        snapshot.capture(root,tmp_path/"snapshot",TEST_DB,quiesced=True)
    assert not (tmp_path/"snapshot").exists()

def test_corrupted_backup_detected_before_restore(project,tmp_path):
    root,source,target,commands=project
    backup=tmp_path/"backup"
    snapshot.capture(root,backup,TEST_DB,quiesced=True)
    with (backup/"database.dump").open("ab") as f:f.write(b"corrupt")
    with pytest.raises(ValueError,match="checksum"):
        snapshot.verify(backup)
    assert not (tmp_path/"restore").exists()

def test_restore_rejects_unmarked_parent_and_original_database(project,tmp_path):
    root,source,target,commands=project
    archive=tmp_path/"snapshot"
    snapshot.capture(root,archive,TEST_DB,quiesced=True)
    with pytest.raises(ValueError):snapshot.restore_test(archive,tmp_path/"other",RESTORE_DB,confirmed=True)
    (tmp_path/".photosorter-staging-only").write_text("STAGING_ONLY")
    with pytest.raises(ValueError):snapshot.restore_test(archive,tmp_path/"other",TEST_DB,confirmed=True)
    with pytest.raises(ValueError):snapshot.restore_test(archive,root/"PhotoSorter"/"data"/"secret",RESTORE_DB,confirmed=True)

def test_huggingface_internal_symlink_round_trip_and_external_symlink_rejected(project,tmp_path):
    root,source,target,commands=project
    cache=root/"Models"/"cache"/"huggingface"/"hub"/"models--gberton--MegaLoc"
    blob=cache/"blobs"/"0123456789abcdef"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"fake-model-weight")
    pointer=cache/"snapshots"/"fake-revision"/"model.safetensors"
    pointer.parent.mkdir(parents=True)
    pointer.symlink_to("../../blobs/0123456789abcdef")
    archive=tmp_path/"hf-backup"
    snapshot.capture(root,archive,TEST_DB,quiesced=True)
    assert snapshot.verify(archive)["verified"]
    (tmp_path/".photosorter-staging-only").write_text("STAGING_ONLY")
    restored=tmp_path/"hf-restored"
    snapshot.restore_test(archive,restored,RESTORE_DB,confirmed=True)
    copied=restored/pointer.relative_to(root)
    assert copied.is_symlink() and copied.read_bytes()==b"fake-model-weight"
    assert copied.readlink().as_posix()=="../../blobs/0123456789abcdef"

    unsafe=cache/"snapshots"/"fake-revision"/"escape"
    unsafe.symlink_to("../../../../../../../outside-secret")
    with pytest.raises(ValueError):
        snapshot.capture(root,tmp_path/"unsafe-archive",TEST_DB,quiesced=True)
