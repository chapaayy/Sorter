"""Read-only diagnostics: no PostgreSQL, file writes or cleanup involved."""
from pathlib import Path
import os

from server.services.storage_breakdown import _scan,_kind


def test_categories_and_inode_dedup_are_per_batch(tmp_path):
    data=tmp_path/"data"
    models=tmp_path/"Models"
    batch="11111111-1111-4111-8111-111111111111"
    run="20261123T123000-abcdef123456"
    original=data/"uploads"/batch/"photo.heic"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"A"*8192)
    normalized=data/"uploads"/batch/".normalized"/"photo.jpg"
    normalized.parent.mkdir()
    normalized.write_bytes(b"B"*4096)
    output=data/"outputs"/run/"megaloc"/"SAM 0001"/"photo.jpg"
    output.parent.mkdir(parents=True)
    os.link(normalized,output)
    archive=data/"outputs"/run/".archives"/"all.zip"
    archive.parent.mkdir()
    archive.write_bytes(b"ZIP"*8192)
    reference=data/"reference_staging"/"session"/"files"/"ref.jpg"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"C"*8192)
    gallery=data/"references"/"SAM 0001"/"ref.jpg"
    gallery.parent.mkdir(parents=True)
    os.link(reference,gallery)
    reference_zip=data/"reference_exports"/"version.zip"
    reference_zip.parent.mkdir()
    reference_zip.write_bytes(b"R"*8192)
    model=models/"models"/"model.bin"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"M"*8192)

    report=_scan(data,models,{batch:"Выезд Самара"},{run:batch})
    groups=report["categories"]
    assert report["partial"] is False
    assert groups["originals"]["files"]==1
    assert groups["normalized"]["files"]==1
    assert groups["results_zip"]["files"]==1
    assert groups["results_zip"]["logical_bytes"]==len(b"ZIP"*8192)
    assert groups["results_files"]["allocated_bytes"]==0
    assert groups["results_files"]["hardlink_paths"]==1
    assert groups["reference_gallery"]["allocated_bytes"]==0
    assert groups["reference_gallery"]["hardlink_paths"]==1
    assert groups["references_zip"]["files"]==1
    assert groups["models"]["files"]==1
    assert report["hardlink_reused_bytes"]==4096+8192
    assert len(report["batches"])==1
    batch_row=report["batches"][0]
    assert batch_row["batch_id"]==batch
    assert batch_row["normalized"]["allocated_bytes"]==normalized.stat().st_blocks*512
    assert batch_row["results_zip"]["allocated_bytes"]==archive.stat().st_blocks*512
    assert batch_row["results_files"]["hardlink_reused_bytes"]==4096
    assert report["allocated_total_bytes"]==sum(
        row["allocated_bytes"] for row in groups.values())


def test_no_follow_symlink_and_partial_limit(tmp_path):
    root=tmp_path/"data"
    root.mkdir()
    outside=tmp_path/"private"
    outside.mkdir()
    (outside/"secret.jpg").write_bytes(b"never count")
    link=root/"uploads"
    link.symlink_to(outside,target_is_directory=True)
    model=tmp_path/"Models"
    model.mkdir()
    result=_scan(root,model,{}, {})
    assert result["files_scanned"]==0
    assert result["allocated_total_bytes"]==0
    # No write to the outside source, and never follow symbolic directories.
    assert (outside/"secret.jpg").read_bytes()==b"never count"
    link.unlink()
    original=root/"uploads"/"b"
    original.mkdir(parents=True)
    for i in range(5):
        (original/f"{i}.jpg").write_bytes(b"x")
    limited=_scan(root,model,{"b":"Sample"},{},max_files=2)
    assert limited["partial"] is True
    assert limited["files_scanned"]==2


def test_bucket_names_cover_media_and_archives():
    assert _kind(("uploads","batch",".normalized","f.jpg"))=="normalized"
    assert _kind(("uploads","batch","f.jpg"))=="originals"
    assert _kind(("outputs","run",".archives","full.zip"))=="results_zip"
    assert _kind(("outputs","run",".archives","full.lock"))=="results_temporary"
    assert _kind(("reference_staging","session","files","f.jpg"))=="reference_objects"
    assert _kind(("reference_staging","session","incoming","part"))=="reference_uploads"
    assert _kind(("reference_exports","full.zip"))=="references_zip"


def test_v2_owner_trees_and_reprocessing_count_physical_inode_once(tmp_path,monkeypatch):
    from app import config
    from app.storage.categories import Category
    from app.storage.paths import managed_path
    root=tmp_path/"app"
    root.mkdir()
    monkeypatch.setattr(config,"APP_STORAGE_ROOT",root)
    batch="11111111-1111-4111-8111-111111111111"
    upload="22222222-2222-4222-8222-222222222222"
    runs=["20261124T123000-abcdef123456","20261124T123001-abcdef123457"]
    original=managed_path(Category.FO_ORIGINAL,user_id=1,batch_uuid=batch,upload_uuid=upload,ext="png")
    normalized=managed_path(Category.FO_NORMALIZED,user_id=1,batch_uuid=batch,upload_uuid=upload,ext="jpg")
    for path,data in ((original,b"A"*8192),(normalized,b"B"*4096)):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    for run in runs:
        copy=managed_path(Category.RESULT_MEDIA,user_id=1,batch_uuid=batch,run_id=run)/"SAM 0001"/"photo.jpg"
        copy.parent.mkdir(parents=True)
        os.link(normalized,copy)
    report=_scan(tmp_path/"state",tmp_path/"models",{batch:"ФО"},{r:batch for r in runs},app_root=root)
    assert report["allocated_total_bytes"]==(original.stat().st_blocks+normalized.stat().st_blocks)*512
    assert report["categories"]["results_files"]["allocated_bytes"]==0
    assert report["hardlink_paths"]==2
    assert report["batches"][0]["allocated_bytes"]==report["allocated_total_bytes"]
