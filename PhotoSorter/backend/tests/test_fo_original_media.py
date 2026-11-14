"""FO support for Windows copy names and original-only multimedia."""
import hashlib
import struct
import uuid
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.photos.scanner import images
from server import jobs
from server.api.routes import batches as batch_routes, originals
from server.services import batches, cleanup, thumbnails, upload_manifest
from server.services.upload_validation import fo_media_type, original_storage_name, safe_name
from .test_stage1_lifecycle import _batch, sandbox, db
from .test_stage2_platform import thumbs, _jpg
from .test_upload_manifest import File, _send

def _ftyp(brand):
    return struct.pack('>I4s4sI4s',20,b'ftyp',brand,0,brand)

@pytest.mark.parametrize(('name','data','expected'),[
    ('IMG_3908 — копия.JPG', _jpg(), None),
    ('видео — 01.MOV', _ftyp(b'qt  '), 'video/quicktime'),
    ('кадр.HEIC', _ftyp(b'heic'), 'image/heic'),
    ('кадр', _ftyp(b'heic'), 'image/heic'),
    ('неверное расширение.jpg', _ftyp(b'qt  '), 'video/quicktime'),
])
def test_format_by_bytes_and_portable_name(tmp_path,name,data,expected):
    assert safe_name(name)==name
    path=tmp_path/'upload.part'
    path.write_bytes(data)
    assert fo_media_type(path,name)==expected
    stored=original_storage_name(hashlib.sha256(data).hexdigest(),name,expected)
    if expected:
        assert Path(stored).suffix=='.media'
    else:
        assert stored.endswith(name)

@pytest.mark.parametrize('name',['../a.jpg','sub/a.jpg','sub\\a.jpg','C:bad.jpg','bad\x00.jpg'])
def test_dangerous_name_not_relaxed(name):
    with pytest.raises(HTTPException,match='Недопустимое имя файла'):
        safe_name(name)

def test_non_media_rejected_and_reference_photo_names_relaxed(tmp_path):
    assert safe_name('IMG_3908 — копия.JPG',reference=True)=='IMG_3908 — копия.JPG'
    with pytest.raises(HTTPException,match='формат образца'):
        safe_name('clip.mov',reference=True)
    part=tmp_path/'file.part'
    part.write_text('not media')
    with pytest.raises(HTTPException,match='распознать фото или видео'):
        fo_media_type(part,'not-video.mov')
    with pytest.raises(HTTPException,match='корректным изображением'):
        fo_media_type(part,'not-image.jpg')

def test_mixed_batch_preserves_download_and_only_indexes_supported_photos(thumbs,monkeypatch):
    from fastapi import FastAPI
    from server.api.routes.thumbnails import thumbnail
    batch=_batch(thumbs,with_photo=False)
    monkeypatch.setattr(originals,'DATA_DIR',thumbs)
    app=FastAPI()
    app.include_router(originals.router)
    clip=_ftyp(b'qt  ')
    raw=_jpg()
    video=File(uuid.uuid4(),'321/Видео — 1.MOV',len(clip))
    photo=File(uuid.uuid4(),'321/IMG_3908 — копия.JPG',len(raw))
    try:
        upload_manifest.register(batch,[video,photo])
        saved=_send(thumbs,batch,video,clip)
        assert Path(saved['path']).read_bytes()==clip
        assert upload_manifest.status(batch)['pending']==1
        _send(thumbs,batch,photo,raw)
        assert upload_manifest.status(batch)['state']=='complete'
        record=batches.get(batch)
        assert (record['photos'],record['media_files'],record['size_bytes'])==(1,1,len(raw)+len(clip))
        assert thumbnails.counts(batch)['total']==1
        assert len(images(thumbs/'uploads'/str(batch)))==1
        gallery=batch_routes.gallery(str(batch))['photos']
        tile=next(row for row in gallery if row['id']==str(video.upload_id))
        assert tile['name']==video.filename
        assert tile['original_media_type']=='video/quicktime'
        assert tile['thumbnail_url'] is None
        with pytest.raises(HTTPException) as exc:
            thumbnail(str(video.upload_id))
        assert exc.value.status_code==404
        with TestClient(app) as client:
            response=client.get(tile['original_url'])
        assert response.status_code==200 and response.content==clip
        assert response.headers['Content-Disposition'].startswith("attachment; filename*=UTF-8''")
        assert response.headers['Content-Type']=='application/octet-stream'
        assert response.headers['X-Content-Type-Options']=='nosniff'
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)

def test_video_only_batch_cannot_schedule_megaloc(thumbs):
    batch=_batch(thumbs,with_photo=False)
    clip=_ftyp(b'qt  ')
    video=File(uuid.uuid4(),'321/clip.mov',len(clip))
    try:
        upload_manifest.register(batch,[video],auto_process=True)
        _send(thumbs,batch,video,clip)
        assert upload_manifest.status(batch)['state']=='complete'
        assert batches.get(batch)['auto_process_state']=='cancelled'
        with pytest.raises(HTTPException,match='в формате, который поддерживает MegaLoc'):
            jobs.enqueue(jobs.NewRun(batch_id=batch))
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)
