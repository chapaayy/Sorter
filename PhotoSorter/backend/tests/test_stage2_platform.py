"""Stage 2 tests always run against disposable PostgreSQL and tmp_path, never production."""
from __future__ import annotations
import hashlib,io,json,os,time,uuid
from pathlib import Path
from PIL import Image
import pytest
from fastapi import HTTPException
from .test_stage1_lifecycle import sandbox,_batch,_job,db
from server.database import connect
from server.services import thumbnails
from server.storage import thumbnail_cache as cache

@pytest.fixture
def thumbs(sandbox,monkeypatch):
    from server import uploads
    from server.api.routes import thumbnails as endpoint
    monkeypatch.setattr(thumbnails,"DATA_DIR",sandbox)
    monkeypatch.setattr(cache,"ROOT",sandbox/"cache"/"thumbnails")
    monkeypatch.setattr(uploads,"UPLOADS_DIR",sandbox/"uploads")
    monkeypatch.setattr(uploads,"REFERENCES_DIR",sandbox/"references")
    monkeypatch.setattr(uploads,"PART_DIR",sandbox/"incoming")
    return sandbox

def _finalize_picture(root,batch_id,raw,filename="image.jpg"):
    from server import uploads
    identifier=uuid.uuid4()
    info=uploads.BeginUpload(kind="fo",batch_id=str(batch_id),filename=filename,
              size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    uploads._create_upload(info,identifier)
    (root/"incoming"/f"{identifier}.part").write_bytes(raw)
    uploads._finalize_sync(str(identifier))
    return identifier

def _jpg(exif=False):
    image=Image.new("RGB",(80,40),"red")
    bio=io.BytesIO()
    if exif:
        metadata=Image.Exif()
        metadata[274]=6
        image.save(bio,format="JPEG",exif=metadata)
    else:image.save(bio,format="JPEG")
    return bio.getvalue()

def test_finalize_enqueues_webp_later_and_uses_exif(thumbs):
    from server.services import batches,cleanup
    from server.api.routes.thumbnails import thumbnail
    own=_batch(thumbs,with_photo=False)
    photo=_finalize_picture(thumbs,own,_jpg(exif=True))
    with connect() as db:
        row=db.execute("SELECT state,attempts FROM thumbnail_tasks WHERE upload_id=%s",
                       (photo,)).fetchone()
    assert row["state"]=="queued" and row["attempts"]==0
    with pytest.raises(HTTPException) as exc:thumbnail(str(photo))
    assert exc.value.status_code==202
    claimed=thumbnails.claim()
    assert claimed["upload_id"]==photo
    assert thumbnails.complete(claimed)=="ready"
    response=thumbnail(str(photo))
    assert response.media_type=="image/webp"
    with Image.open(response.path) as rendered:
        assert rendered.format=="WEBP"
        assert rendered.height>rendered.width, "EXIF rotation must be applied"
        assert max(rendered.size)<=cache.MAX_SIDE
    assert batches.get(own)["thumbnail_state"]=="ready"
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="completed"

def test_thumb_worker_retries_and_recovers_stale_lease(thumbs):
    from server.services import cleanup
    own=_batch(thumbs,with_photo=False)
    photo=_finalize_picture(thumbs,own,_jpg())
    with connect() as db:
        db.execute("""UPDATE thumbnail_tasks SET state='running',
           lease_until=now()-interval '1 minute' WHERE upload_id=%s""",(photo,))
    claimed=thumbnails.claim()
    assert claimed["upload_id"]==photo
    assert thumbnails.complete(claimed)=="ready"
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_content_addressed_cache_reuse_and_owner_safe_gc(thumbs,monkeypatch):
    from server.services import cleanup
    first=_batch(thumbs,with_photo=False)
    second=_batch(thumbs,with_photo=False)
    data=_jpg()
    a=_finalize_picture(thumbs,first,data)
    b=_finalize_picture(thumbs,second,data)
    rendered=[]
    real=thumbnails.render
    def wrapped(*args,**kwargs):
        rendered.append(1)
        return real(*args,**kwargs)
    monkeypatch.setattr(thumbnails,"render",wrapped)
    assert thumbnails.complete(thumbnails.claim())=="ready"
    assert thumbnails.complete(thumbnails.claim())=="ready"
    assert len(rendered)==1
    shared=cache.location(hashlib.sha256(data).hexdigest())
    assert shared.is_file()
    cleanup.request(first)
    assert cleanup.cleanup_one(first)=="completed"
    assert thumbnails.gc_unowned(limit=30,grace_seconds=0)==0
    assert shared.exists()
    cleanup.request(second)
    assert cleanup.cleanup_one(second)=="completed"
    assert thumbnails.gc_unowned(limit=30,grace_seconds=0)==1
    assert not shared.exists()

def test_corrupt_preview_failure_is_bounded(thumbs):
    from server.services import cleanup
    own=_batch(thumbs,with_photo=False)
    photo=_finalize_picture(thumbs,own,_jpg())
    with connect() as db:
        db.execute("UPDATE uploads SET target_path=%s WHERE id=%s",
                   (str(thumbs/"outside.jpg"),photo))
    for _ in range(thumbnails.MAX_ATTEMPTS):
        row=thumbnails.claim()
        assert row["upload_id"]==photo
        assert thumbnails.complete(row)=="error"
    with connect() as db:
        t=db.execute("SELECT state,attempts FROM thumbnail_tasks WHERE upload_id=%s",
                     (photo,)).fetchone()
    assert t=={"state":"failed","attempts":thumbnails.MAX_ATTEMPTS}
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_keyset_gallery_with_1001_synthetic_records(thumbs):
    from server.api.routes.batches import gallery
    from server.services import cleanup
    from server.db.repositories.pagination import decode
    own=_batch(thumbs,with_photo=False)
    with connect() as db:
        db.execute("""INSERT INTO uploads(id,kind,batch_id,filename,declared_size,
          received,checksum,finalized,created_at)
          SELECT gen_random_uuid(),'fo',%s,'synthetic_'||i||'.jpg',1,1,
             repeat('a',64),true,now()+i*interval '1 microsecond'
          FROM generate_series(1,1001) AS g(i)""",(own,))
    seen=set()
    cursor=None
    while True:
        reply=gallery(str(own),cursor=cursor,limit=73)
        for item in reply["photos"]:seen.add(item["id"])
        cursor=reply["next_cursor"]
        if not cursor:break
    assert len(seen)==1001
    with pytest.raises(HTTPException):gallery(str(own),cursor="not a cursor")
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_sequential_megaloc_jobs_and_stops(thumbs):
    from server.jobs import enqueue,stop,NewRun
    from server.db.repositories import queue
    from server.services import cleanup
    batches=[_batch(thumbs) for _ in range(3)]
    ref=uuid.uuid4()
    with connect() as db:
        db.execute("""INSERT INTO uploads(id,kind,sam,filename,declared_size,
               received,checksum,finalized,target_path)
               VALUES (%s,'reference','SAM-0001','ref.jpg',1,1,%s,true,%s)""",
               (ref,'0'*64,str(thumbs/"references"/"SAM-0001"/"ref.jpg")))
    try:
        jobs=[enqueue(NewRun(batch_id=b)) for b in batches]
        assert [job["queue_position"] for job in jobs]==[1,2,3]
        with connect() as db:
            first=queue.next_job(db)
        assert first["id"]==jobs[0]["id"]
        with connect() as db:
            assert queue.next_job(db) is None
        assert stop(jobs[2]["id"])["status"]=="stopped"
        with connect() as db:
            db.execute("""UPDATE jobs SET status='completed' WHERE id=%s""",
                       (first["id"],))
            nxt=queue.next_job(db)
        assert nxt["id"]==jobs[1]["id"]
        with connect() as db:
            db.execute("UPDATE jobs SET status='completed' WHERE id=%s",(nxt["id"],))
    finally:
        with connect() as db:
            db.execute("DELETE FROM uploads WHERE id=%s",(ref,))
        for own in batches:
            cleanup.request(own)
            cleanup.cleanup_one(own)

def test_export_rows_jsonl_and_paged_results(thumbs,monkeypatch):
    from app.results import repository
    from server.services import result_pages
    from app.config import DATA_DIR
    monkeypatch.setattr(result_pages,"DATA_DIR",thumbs)
    run="20261105T120000-"+uuid.uuid4().hex[:12]
    picture=thumbs/"uploads"/"photo.jpg"
    picture.write_bytes(b"immutable bytes")
    rows=[]
    for i in range(9):
        rows.append({"query":str(picture),"top":[{"label":f"SAM-000{i%3+1}",
            "reference":"ref","score":.88}],"group_id":f"G{i//3:04d}"})
    repository.save_model({"id":run,"output":str(thumbs/"outputs")},"megaloc",rows)
    cursor=None
    indexes=[]
    while True:
        page=result_pages.page(run,cursor=cursor,limit=4)
        indexes.extend([r["index"] for r in page["rows"]])
        cursor=page["next_cursor"]
        if not cursor:break
    assert indexes==list(range(9))
    assert result_pages.counts(run)["sam"]["SAM-0001"]==3
    selected=result_pages.page(run,sam="SAM-0001",limit=20)
    assert len(selected["rows"])==3

def test_jsonl_rotation_and_cursor_without_read_text(thumbs,monkeypatch):
    from app.logging import events
    monkeypatch.setattr(events,"RUNS_DIR",thumbs/"runs")
    monkeypatch.setattr(events,"SEGMENT_BYTES",900)
    monkeypatch.setattr(events,"SEGMENTS",3)
    monkeypatch.setattr(events,"TOTAL_BYTES",10_000)
    run="20261105T120000-"+uuid.uuid4().hex[:12]
    for i in range(30):
        events.emit(run,"INFO",f"test_{i:02d} "+("x"*70),model="megaloc")
    entries=events.read(run,limit=5)
    assert entries[-1]["message"].startswith("test_29")
    assert len(entries)==5
    reply=events.page(run,limit=2)
    assert len(reply["events"])==2
    assert reply["next_cursor"]
    subsequent=events.page(run,cursor=reply["next_cursor"],limit=2)
    assert len(subsequent["events"])==2
    files=list((thumbs/"runs"/run).glob("events.jsonl*"))
    assert len(files)<=3
    assert all(f.stat().st_size<=events.SEGMENT_BYTES for f in files)

def test_disk_reserve_blocks_growth(thumbs,monkeypatch):
    from server.services import disk_guard
    monkeypatch.setattr(disk_guard,"DATA_DIR",thumbs)
    monkeypatch.setattr(disk_guard,"stat",lambda *args:(200*1024**3,11*1024**3))
    with pytest.raises(HTTPException) as exc:
        disk_guard.check_admission(10*1024**2)
    assert exc.value.status_code==507
    monkeypatch.setattr(disk_guard,"stat",lambda *args:(200*1024**3,80*1024**3))
    assert disk_guard.check_admission(60*1024**2)["available"]==80*1024**3
