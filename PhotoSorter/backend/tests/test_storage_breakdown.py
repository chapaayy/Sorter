"""Registry-backed diagnostics on typed paths and real PostgreSQL."""
import os
from pathlib import Path
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_path
from server.services.storage_breakdown import breakdown
from server.storage.registry import classify
from .test_unified_queue_stage3 import system
from .test_stage1_lifecycle import _batch,_job
from .accounting_checks import settle,exact

def test_v2_owner_trees_and_reprocessing_count_physical_inode_once(system):
    from server import database
    batch=_batch(system)
    with database.connect() as db:
        row=db.execute("SELECT id,target_path FROM uploads WHERE batch_id=%s",(batch,)).fetchone()
        owner=db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch,)).fetchone()["owner_id"]
    original=Path(row["target_path"])
    normalized=managed_path(Category.FO_NORMALIZED,user_id=owner,batch_uuid=batch,upload_uuid=row["id"],ext="jpg")
    normalized.parent.mkdir(parents=True)
    normalized.write_bytes(b"B"*4096)
    with database.connect() as db:db.execute("UPDATE uploads SET media_output_path=%s WHERE id=%s",(str(normalized),row["id"]))
    runs=[_job(system,batch),_job(system,batch)]
    for run in runs:
        copy=managed_path(Category.RESULT_MEDIA,user_id=owner,batch_uuid=batch,run_id=run)/"SAM 0001"/"photo.jpg"
        copy.parent.mkdir(parents=True)
        os.link(normalized,copy)
    archive=managed_path(Category.ZIP_RESULTS,run_id=runs[0])/("5ef5ef5ef5ef-"+"f"*20+".zip")
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"ZIP"*8192)
    settle()
    report=breakdown()
    groups=report["categories"]
    assert groups["originals"]["files"]==1
    assert groups["normalized"]["files"]==1
    assert groups["results_zip"]["files"]==1
    assert groups["results_files"]["allocated_bytes"]==0
    assert groups["results_files"]["hardlink_paths"]==2
    assert report["allocated_total_bytes"]==sum(x["allocated_bytes"] for x in groups.values())
    row=next(x for x in report["batches"] if x["batch_id"]==str(batch))
    assert row["normalized"]["allocated_bytes"]==normalized.stat().st_blocks*512
    assert row["results_zip"]["allocated_bytes"]==archive.stat().st_blocks*512

def test_symlink_leaf_reported_without_following(system,tmp_path):
    outside=tmp_path/"outside"
    outside.mkdir()
    (outside/"secret.jpg").write_bytes(b"never count")
    link=config.APP_STORAGE_ROOT/"external"
    link.symlink_to(outside,target_is_directory=True)
    settle()
    row=exact(link)
    assert row["kind"]=="symlink" and row["issue"]=="unexpected_symlink"
    assert (outside/"secret.jpg").read_bytes()==b"never count"
    assert breakdown()["files_scanned"]==1

def test_category_names_cover_v2_media_archives_and_unknown():
    batch="11111111-1111-4111-8111-111111111111"
    run="20261123T123000-abcdef123456"
    assert classify(f"app/users/1/batches/{batch}/originals/{batch}.jpg")[0]=="fo_original"
    assert classify(f"app/users/1/batches/{batch}/normalized/{batch}.jpg")[0]=="fo_normalized"
    assert classify(f"app/temporary/archives/results/{run}/{'a'*12}-{'b'*20}.lock")[0]=="archive_lock"
    assert classify(f"app/temporary/archives/references/{'a'*64}.zip")[0]=="zip_references"
    assert classify("app/outputs/legacy/file.jpg")[0]=="unknown"
