"""Stage 2 transfer and streaming regressions, disposable files/DB only."""
from __future__ import annotations
import asyncio,hashlib,io,os,uuid,zipfile,json
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from PIL import Image
from pathlib import Path
from .asgi_response import http_scope,receive,response_bytes
from .test_stage2_platform import thumbs,_jpg,_finalize_picture
from .test_stage1_lifecycle import _batch,_job,sandbox,db
from server.database import connect

def as_request(data,*,offset=None):
    chunks=[data[:max(1,len(data)//2)],data[max(1,len(data)//2):]]
    messages=[{"type":"http.request","body":chunks[0],"more_body":True},
              {"type":"http.request","body":chunks[1],"more_body":False}]
    async def receive():
        if messages:return messages.pop(0)
        return {"type":"http.request","body":b"","more_body":False}
    headers=[(b"upload-offset",str(offset).encode())] if offset is not None else []
    scope={"type":"http","method":"PUT","path":"/upload","headers":headers,"query_string":b""}
    return Request(scope,receive)

def test_direct_put_idempotent_and_thumbnail_queued(thumbs):
    from server import uploads
    from server.services import cleanup
    own=_batch(thumbs,with_photo=False)
    blob=_jpg()
    uid=str(uuid.uuid4())
    params=dict(upload_id=uid,request=as_request(blob),kind="fo",filename="fo.jpg",
                size=len(blob),batch_id=str(own))
    result=asyncio.run(uploads.direct_upload(**params))
    assert hashlib.sha256(blob).hexdigest()==result["sha256"]
    again=asyncio.run(uploads.direct_upload(**{**params,"request":as_request(blob)}))
    assert again["already_finalized"]
    with connect() as db:
        rows=db.execute("SELECT count(*) AS n FROM thumbnail_tasks WHERE upload_id=%s",
                        (uuid.UUID(uid),)).fetchone()["n"]
    assert rows==1
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_patch_resume_offset_checksum_and_cancel(thumbs):
    from server import uploads
    from server.services import cleanup
    own=_batch(thumbs,with_photo=False)
    blob=_jpg()
    payload=uploads.BeginUpload(kind="fo",filename="resume.jpg",size=len(blob),
                batch_id=str(own),sha256=hashlib.sha256(blob).hexdigest())
    uid=str(uuid.uuid4())
    uploads._create_upload(payload,uuid.UUID(uid))
    first=len(blob)//2
    part1=asyncio.run(uploads.upload_chunk(uid,as_request(blob[:first],offset=0)))
    assert part1["offset"]==first
    assert uploads.upload_status(uid)["offset"]==first
    with pytest.raises(HTTPException) as error:
        asyncio.run(uploads.upload_chunk(uid,as_request(blob[first:],offset=0)))
    assert error.value.status_code==409
    done=asyncio.run(uploads.upload_chunk(uid,as_request(blob[first:],offset=first)))
    assert done["offset"]==len(blob)
    assert asyncio.run(uploads.finalize(uid))["sha256"]==payload.sha256
    assert Path(uploads.get_upload(uid)["target_path"]).read_bytes()==blob
    with pytest.raises(HTTPException) as error:
        asyncio.run(uploads.cancel_upload(uid))
    assert error.value.status_code==409
    draft=str(uuid.uuid4())
    uploads._create_upload(payload,uuid.UUID(draft))
    uploads.part_path(own,draft).write_bytes(b"partial")
    assert asyncio.run(uploads.cancel_upload(draft))["cancelled"]
    assert not uploads.part_path(own,draft).exists()
    with pytest.raises(HTTPException) as error:uploads.get_upload(draft)
    assert error.value.status_code==404
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_image_checksum_validation_rejects_corruption(thumbs):
    from server import uploads
    from server.services import cleanup
    own=_batch(thumbs,with_photo=False)
    raw=_jpg()
    payload=uploads.BeginUpload(kind="fo",filename="mismatch.jpg",size=len(raw),
           batch_id=str(own),sha256="0"*64)
    uid=str(uuid.uuid4())
    uploads._create_upload(payload,uuid.UUID(uid))
    uploads.part_path(own,uid).write_bytes(raw)
    with pytest.raises(HTTPException) as exc:uploads._finalize_sync(uid)
    assert exc.value.status_code==422
    from server.storage.paths import batch_dir
    assert not list(batch_dir(own).glob("*"))
    cleanup.request(own)
    cleanup.cleanup_one(own)

def test_seekable_zip_lease_released_after_response_and_preserves_originals(thumbs,monkeypatch):
    from app.results import repository
    from server.api.routes import images,downloads,originals
    from server.services import cleanup
    monkeypatch.setattr(images,"DATA_DIR",thumbs)
    monkeypatch.setattr(originals,"DATA_DIR",thumbs)
    own=_batch(thumbs,with_photo=False)
    from server.storage.paths import batch_dir
    originals_dir=batch_dir(own)
    originals_dir.mkdir(parents=True)
    blob=os.urandom(512*1024)
    source=originals_dir/"report.jpg"
    source.write_bytes(blob)
    uid=uuid.uuid4()
    with connect() as db:
        db.execute("""INSERT INTO uploads(id,kind,batch_id,filename,declared_size,
            received,checksum,finalized,target_path) VALUES (%s,'fo',%s,'report.jpg',
            %s,%s,%s,true,%s)""",(uid,own,len(blob),len(blob),
             hashlib.sha256(blob).hexdigest(),str(source)))
    run=_job(thumbs,own)
    repository.save_model({"id":run,"batch_id":str(own)},
      "megaloc",[{"query":str(source),"top":[],"group_id":"G0001"}])
    async def consume_part():
        response=downloads.download_results(run)
        assert cleanup.request(own)["state"]=="deleting"

        async def send(message):
            if message["type"]=="http.response.body":
                assert await asyncio.to_thread(cleanup.cleanup_one,own)=="waiting"
                assert Path(response.path).is_file()

        await response(http_scope(headers=[(b"range",b"bytes=0-31")]),receive,send)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app=FastAPI()
    app.include_router(downloads.router)
    with TestClient(app) as client:
        assert client.get(f"/api/download/{run}",headers={"Range":"bytes=99999999-"}).status_code==416
    asyncio.run(consume_part())
    with connect() as db:
        n=db.execute("SELECT count(*) AS n FROM batch_operations WHERE batch_id=%s",
                     (own,)).fetchone()["n"]
    assert n==0
    assert cleanup.cleanup_one(own)=="completed"
    assert not batch_dir(own).exists()

def test_original_viewer_streaming_lease(thumbs,monkeypatch):
    from server.api.routes import originals
    from server.services import cleanup
    monkeypatch.setattr(originals,"DATA_DIR",thumbs)
    own=_batch(thumbs,with_photo=False)
    blob=_jpg()
    uid=_finalize_picture(thumbs,own,blob)
    response=originals.original(str(uid))
    assert asyncio.run(response_bytes(response))==blob
    assert response.headers["content-length"]==str(len(blob))
    with connect() as db:
        assert db.execute("""SELECT count(*) AS n FROM batch_operations
                      WHERE batch_id=%s""",(own,)).fetchone()["n"]==0
    cleanup.request(own)
    cleanup.cleanup_one(own)

@pytest.mark.parametrize("disconnect",["send_error","cancel"])
def test_interrupted_original_response_unblocks_batch_cleanup(thumbs,monkeypatch,disconnect):
    import anyio
    from server.api.routes import originals
    from server.services import cleanup

    monkeypatch.setattr(originals,"DATA_DIR",thumbs)
    own=_batch(thumbs,with_photo=False)
    uid=_finalize_picture(thumbs,own,_jpg())
    response=originals.original(str(uid))
    assert cleanup.request(own)["state"]=="deleting"
    assert cleanup.cleanup_one(own)=="waiting"

    async def simulate_disconnect():
        async def send(message):
            if message["type"]=="http.response.body":
                if disconnect=="send_error":
                    raise BrokenPipeError("client disconnected")
                transfer.cancel()
                await anyio.sleep_forever()

        with anyio.CancelScope() as transfer:
            if disconnect=="send_error":
                with pytest.raises(BrokenPipeError):
                    await response(http_scope(),receive,send)
            else:
                await response(http_scope(),receive,send)

    asyncio.run(simulate_disconnect())
    assert cleanup.cleanup_one(own)=="completed"


def test_parallel_upload_creation_on_same_batch_has_no_deadlocks(thumbs,monkeypatch):
    """Many browser file starts on one batch must not deadlock."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from server import uploads
    from server.services import cleanup

    batch=_batch(thumbs,with_photo=False)
    concurrency=6
    barrier=Barrier(concurrency)
    original_start=uploads.operations.start

    def aligned_start(batch_id,kind):
        token=original_start(batch_id,kind)
        if kind=='init':
            barrier.wait(timeout=15)
        return token

    monkeypatch.setattr(uploads.operations,'start',aligned_start)

    def create(index):
        uid=uuid.uuid4()
        uploads._create_upload(uploads.BeginUpload(
            kind='fo',filename=f'parallel_{index}.jpg',
            batch_id=str(batch),size=1024),uid)
        return uid

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures=[pool.submit(create,index) for index in range(concurrency)]
            identifiers=[future.result(timeout=30) for future in futures]
        with connect() as db:
            count=db.execute(
                "SELECT count(*) AS n FROM uploads WHERE batch_id=%s AND NOT finalized",
                (batch,)).fetchone()['n']
        assert count==concurrency
        assert len(set(identifiers))==concurrency
    finally:
        cleanup.request(batch)
        cleanup.cleanup_one(batch)
