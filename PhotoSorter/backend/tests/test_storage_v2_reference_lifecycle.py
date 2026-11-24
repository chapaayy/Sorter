"""Stage 4 integration against disposable PostgreSQL and actual storage bytes."""
import hashlib
import os
import uuid
import zipfile

import numpy as np
import pytest
from PIL import Image

from app import config
from server import database, reference_cache
from server.db.repositories import reference_versions, work_queue
from server.services import reference_uploads, reference_gc, references, thumbnails, reference_archives
from server.storage import reference_objects as objects, thumbnail_cache
from server.storage.reference_lifecycle import ReadPin
from server.workers import reference_prepare
from .test_unified_queue_stage3 import system, add_fo, finish_fo
from .test_reference_import_stage2 import entry, open_session
from .test_stage2_platform import _jpg


def test_reference_lifecycle_shared_bytes_pins_and_cache_reuse(system,monkeypatch):
    raw=_jpg()
    digest=hashlib.sha256(raw).hexdigest()
    target=objects.object_path(digest)
    inferred=[]
    class Engine:
        performance=None
        def extract_many(self,paths,*,stop=None):
            for path in paths:
                inferred.append(path)
                yield path,np.array([0.9,0.1],dtype=np.float32),None
    class Warm:
        def get(self,fp):return Engine()
    def upload(sam,filename):
        item=entry(filename,sha256=digest,sam=sam)
        sid=open_session([item])
        reference_uploads.append(sid,item.upload_id,0,raw)
        part=objects.partial(sid,item.upload_id)
        before=part.stat().st_ino
        existed=target.exists()
        reply=reference_uploads.finish(sid,item.upload_id)
        assert not reply["already_present"]
        assert not part.exists()
        if not existed:assert target.stat().st_ino==before
        with database.connect() as db:
            task=work_queue.claim_next(db)
        assert task["kind"]=="reference_preparation"
        reference_prepare.run(task["id"],warm_megaloc=Warm())
        return item.upload_id
    first=upload("SAM 0004","first.jpg")
    inode=target.stat().st_ino
    second=upload("SAM 0005","second.jpg")
    assert target.stat().st_ino==inode
    assert inferred==[target]
    embedding=reference_cache.location(digest,"a"*64)
    assert embedding.is_file()
    with database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM reference_physical_objects").fetchone()["n"]==1
        assert db.execute("SELECT count(*) AS n FROM reference_cache").fetchone()["n"]==1
        assert len(reference_versions.members(db,reference_versions.current(db)["id"]))==2
        assert reference_cache.cached_feature(db,digest,"a"*64) is not None
    duplicate=entry("duplicate.jpg",sha256=digest,sam="SAM 0004")
    sid=open_session([duplicate])
    assert reference_uploads.confirm_duplicate(sid,duplicate.upload_id,digest)["already_present"]
    assert not objects.partial(sid,duplicate.upload_id).exists()
    np.save(embedding,np.array([0.2,0.8],dtype=np.float32))
    with database.connect() as db:
        assert reference_cache.cached_feature(db,digest,"a"*64) is None
    third=upload("SAM 0006","third.jpg")
    assert inferred==[target,target]
    from server.services import reference_sides
    from app.results.sides import attach_sides
    reference_sides.assign("SAM 0004",[first],"A1")
    reference_sides.assign("SAM 0005",[second],"B2")
    assert target.read_bytes()==raw
    assert target.stat().st_ino==inode
    while (task:=thumbnails.claim()) is not None:
        assert thumbnails.complete(task)=="ready"
    preview=thumbnail_cache.location(digest)
    with Image.open(preview) as img:assert img.format=="WEBP"
    with ReadPin():
        plan=reference_archives.current_plan()
        archive=reference_archives.prepare(plan)
        assert reference_gc.collect(history_grace=0,grace_seconds=0)["blocked"]
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist())==3
        assert all(z.read(n)==raw for n in z.namelist())
    run=add_fo()
    with database.connect() as db:
        task=work_queue.claim_next(db)
        pin=db.execute("SELECT reference_version_id FROM jobs WHERE id=%s",(run,)).fetchone()["reference_version_id"]
        assert pin is not None
        assert len(task["info"]["reference_members"])==3
        rows=[{"top":[{"label":sam,"reference":str(target)}]} for sam in ("SAM 0004","SAM 0005")]
        assert [row["side"] for row in attach_sides(rows,task["info"]["reference_members"])]==["A1","B2"]
    assert references.delete_photo(first)["queued"]
    assert reference_gc.collect(history_grace=0,grace_seconds=0)["objects"]==0
    finish_fo(run)
    with database.connect() as db:
        deletion=work_queue.claim_next(db)
    references.process_deferred(deletion["id"])
    assert references.delete_photo(second)["deleted"]
    assert references.delete_photo(third)["deleted"]
    assert reference_gc.collect(history_grace=0,grace_seconds=0)["objects"]==0
    assert target.exists() and embedding.exists() and preview.exists()
    assert thumbnails.gc_unowned(grace_seconds=0)==0
    history=reference_gc.history_usage()
    assert history["objects"]==1 and history["embeddings"]==1
    with database.connect() as db:
        assert len(reference_versions.members(db,pin))==3
        db.execute("DELETE FROM work_queue WHERE fo_run_id=%s",(run,))
        db.execute("DELETE FROM jobs WHERE id=%s",(run,))
    result=reference_gc.collect(history_grace=0,grace_seconds=86400)
    assert result["objects"]==0 and result["embeddings"]==0
    assert target.exists() and embedding.exists()
    with database.connect() as db:
        assert db.execute("SELECT members_retired_at FROM reference_library_versions WHERE id=%s",(pin,)).fetchone()["members_retired_at"] is not None
        with pytest.raises(ValueError):reference_versions.members(db,pin)
        db.execute("UPDATE reference_physical_objects SET unowned_since=now()-interval '2 days'")
        db.execute("UPDATE reference_cache SET unowned_since=now()-interval '2 days'")
    result=reference_gc.collect(history_grace=0)
    assert result["objects"]==1 and result["embeddings"]==1
    assert not target.exists() and not embedding.exists()
    assert thumbnails.gc_unowned(grace_seconds=0)==1
    assert not preview.exists()


def test_reference_upload_expiry_respects_transfer_lock(system):
    raw=_jpg()
    item=entry("abandoned.jpg",sha256=hashlib.sha256(raw).hexdigest())
    sid=open_session([item])
    reference_uploads.append(sid,item.upload_id,0,raw[:20])
    part=objects.partial(sid,item.upload_id)
    with database.connect() as db:
        db.execute("UPDATE reference_import_sessions SET created_at=now()-interval '40 days',manifest_registered_at=now()-interval '40 days' WHERE id=%s",(sid,))
        db.execute("UPDATE reference_import_files SET updated_at=now()-interval '40 days' WHERE upload_id=%s",(item.upload_id,))
    with database.connect() as db:
        db.execute("SELECT upload_id FROM reference_import_files WHERE upload_id=%s FOR UPDATE",(item.upload_id,))
        assert reference_gc.collect()["cancelled_imports"]==0
        assert part.exists()
    orphan=objects.object_path("b"*64)
    orphan.parent.mkdir(parents=True,exist_ok=True)
    orphan.write_bytes(b"unknown")
    result=reference_gc.collect()
    assert result["cancelled_imports"]==1 and result["parts"]==1
    assert not part.exists() and orphan.exists()


def test_model_signature_stable_under_relocation_and_touch(tmp_path,monkeypatch):
    from app.system import model_store
    root=tmp_path/"source"
    root.mkdir()
    (root/"hubconf.py").write_text("example=1")
    weights=tmp_path/"weights"
    weights.write_bytes(b"test weight bytes")
    monkeypatch.setattr(model_store,"checkpoint",lambda:weights)
    monkeypatch.setattr(model_store,"repo_folder",lambda:root)
    monkeypatch.setattr(model_store,"files_present",lambda:True)
    sig=model_store.signature()
    os.utime(weights,None)
    assert model_store.signature()==sig
    moved=weights.with_name("moved")
    weights.rename(moved)
    weights=moved
    assert model_store.signature()==sig
    weights.write_bytes(b"new weight bytes")
    assert model_store.signature()!=sig
