"""Real FFmpeg fixtures and PostgreSQL tests for a mixed photo/video import."""
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import uuid
import zipfile

import numpy as np
import psycopg
from psycopg.conninfo import make_conninfo
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from server import database,jobs
from server.api.routes import batches as batch_api,images,originals,work_queue as queue_api
from server.db.repositories import work_queue
from server.media import formats,sorting,video
from server.services import batches,cleanup,media_preparation,thumbnails,upload_manifest
from server.workers import media_prepare
from .test_stage1_lifecycle import _batch,sandbox
from .test_stage2_platform import _jpg,thumbs
from .test_unified_queue_stage3 import add_published_reference
from .test_upload_manifest import File,_send


@pytest.fixture
def db(monkeypatch):
    url=database.DB_URL
    if not url:pytest.skip('Requires disposable PostgreSQL')
    schema='media_'+uuid.uuid4().hex[:16]
    with psycopg.connect(url) as conn:
        conn.execute('CREATE SCHEMA '+schema)
    monkeypatch.setattr(database,'DB_URL',make_conninfo(url,options='-c search_path='+schema))
    database.initialize()
    try:
        yield
    finally:
        with psycopg.connect(url) as conn:
            conn.execute('DROP SCHEMA '+schema+' CASCADE')


@pytest.fixture
def clips(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Requires FFmpeg')
    original = tmp_path/'test.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=128x96:rate=14',
                    '-frames:v','20','-c:v','libx264','-threads','1',str(original)],check=True)
    mov = tmp_path/'test.mov'
    subprocess.run(['ffmpeg','-v','error','-i',str(original),'-c','copy',str(mov)],check=True)
    return original,mov


def _file(name, data):
    return File(uuid.uuid4(),'Выезд/'+name,len(data))


def _import(root,batch,files,*,auto=False,image='jpg',movie='mp4'):
    items=[(_file(name,data),data) for name,data in files]
    upload_manifest.register(batch,[f for f,_ in items],auto_process=auto,image_format=image,video_format=movie)
    return [(f,_send(root,batch,f,data)) for f,data in items]


def test_compatible_files_are_untouched_no_media_queue_and_video_has_poster(thumbs,clips,monkeypatch):
    batch=_batch(thumbs,with_photo=False)
    mp4=clips[0].read_bytes()
    monkeypatch.setattr(originals,'DATA_DIR',thumbs)
    saved=_import(thumbs,batch,[('photo.JPG',_jpg()),('video.mp4',mp4)])
    with database.connect() as db:
        assert not work_queue.entries(db)
        rows=db.execute("SELECT media_action,media_output_path FROM uploads WHERE batch_id=%s",(batch,)).fetchall()
        assert rows==[{'media_action':'keep','media_output_path':None}]*2
    assert batches.get(batch)['videos']==1
    while task:=thumbnails.claim():
        assert thumbnails.complete(task)=='ready'
    gallery=batch_api.gallery(str(batch))['photos']
    tile=next(p for p in gallery if p['media_kind']=='video')
    assert tile['thumbnail_status']=='ready' and tile['thumbnail_url'] and tile['duration']>0
    assert Path(saved[1][1]['path']).read_bytes()==mp4
    app=FastAPI()
    app.include_router(originals.router)
    with TestClient(app) as client:
        response=client.get(tile['play_url'],headers={'Range':'bytes=0-19'})
        assert client.get(tile['play_url'],headers={'Range':f'bytes={len(mp4)+1}-'}).status_code==416
    with database.connect() as db:
        assert db.execute("SELECT 1 FROM batch_operations WHERE batch_id=%s",(batch,)).fetchone() is None
    assert response.status_code==206 and response.content==mp4[:20]
    assert response.headers['content-type']=='video/mp4'


def test_mixed_folder_waits_for_fifo_then_sorts_and_exports_whole_video(thumbs,clips,monkeypatch):
    from app.results import repository
    from app.system import model_store
    from server.services import archives,reference_gallery,reference_publication
    from server.storage import reference_objects
    from server.media import sorting
    from server import reference_cache

    for module in (jobs,sorting,media_prepare,archives,images):
        monkeypatch.setattr(module,'DATA_DIR',thumbs,raising=False)
    monkeypatch.setattr(repository,'RUNS_DIR',thumbs/'runs')
    monkeypatch.setattr(reference_objects,'ROOT',thumbs/'staged')
    monkeypatch.setattr(reference_gallery,'GALLERY',thumbs/'references')
    monkeypatch.setattr(reference_publication,'signature',lambda:'stage3-model')
    monkeypatch.setattr(work_queue,'signature',lambda:'stage3-model')
    monkeypatch.setattr(model_store,'files_present',lambda:True)
    monkeypatch.setattr(reference_cache,'CACHE_DIR',thumbs/'ref-cache')
    monkeypatch.setattr(reference_cache,"REFERENCE_ROOT",thumbs/"staged")
    monkeypatch.setattr(reference_cache,"signature",lambda:"stage3-model")
    add_published_reference(thumbs)
    ahead=_batch(thumbs,with_photo=True)
    older=jobs.enqueue(jobs.NewRun(batch_id=ahead))['id']
    with database.connect() as conn:
        assert work_queue.claim_next(conn)['id']==older
    batch=_batch(thumbs,with_photo=False)
    photo=BytesIO()
    Image.new('RGBA',(64,32),(255,0,0,128)).save(photo,format='PNG')
    source={'Альфа.png':photo.getvalue(),'Клип.mov':clips[1].read_bytes(),'Совместимый.JPG':_jpg()}
    saved=_import(thumbs,batch,list(source.items()),auto=True)
    state=batches.get(batch)
    assert state['auto_process_state']=='waiting'
    assert state['media_preparation']['total_count']==2
    with pytest.raises(HTTPException,match='дождитесь перекодирования'):
        jobs.enqueue(jobs.NewRun(batch_id=batch))
    with database.connect() as conn:
        assert work_queue.claim_next(conn) is None
        work_queue.finish_fo(conn,older,'completed')
        conn.execute("UPDATE jobs SET status='completed' WHERE id=%s",(older,))
    assert queue_api.list_work_queue()['tasks'][0]['kind']=='media_preparation'
    with database.connect() as conn:
        task=work_queue.claim_next(conn)
    media_prepare.run(task,stopping=lambda:False)
    state=batches.get(batch)
    assert state['media_preparation']['state']=='completed'
    assert state['media_preparation']['completed_count']==2
    assert state['auto_process_state']=='queued'
    assert (state['photos'],state['videos'])==(2,1)
    for upload,metadata in saved:
        assert Path(metadata['path']).read_bytes()==source[upload.filename]
    with database.connect() as conn:
        item=work_queue.claim_next(conn)
    assert item['kind']=='fo_processing' and item['info']['has_media_profile']

    class Engine:
        device='cpu'
        performance=None
        def extract_many(self,paths,*,stop=None):
            for path in paths:
                yield path,np.asarray([1.,0.],dtype='float32'),None

    class Warm:
        def ready_for(self,fp):return True
        def get(self,fp):return Engine()

    job=jobs.ServerJob(item['info'],warm_megaloc=Warm())
    job.run()
    assert job.info['status']=='completed',job.info.get('error')
    rows=repository.load_model(item['id'],'megaloc')
    assert len(rows)==3
    videos=[row for row in rows if row['media_kind']=='video']
    assert len(videos)==1 and videos[0]['assigned_sam']=='SAM 0001'
    assert not list(job.path.glob('media-frames-*'))
    archive=archives.published(item['id'],job.info['archive_file'])
    with zipfile.ZipFile(archive) as zipped:
        assert {Path(name).name for name in zipped.namelist()}=={'Альфа.jpg','Клип.mp4','Совместимый.JPG'}
        mp4=next(name for name in zipped.namelist() if name.endswith('.mp4'))
        normalized=thumbs/'downloaded.mp4'
        normalized.write_bytes(zipped.read(mp4))
        assert formats.probe(normalized).codec=='h264'
    app=FastAPI()
    app.include_router(images.router)
    index=rows.index(videos[0])
    with TestClient(app) as client:
        result=client.get(f"/api/images/{item['id']}/megaloc/{index}?kind=copy",headers={'Range':'bytes=0-19'})
    assert result.status_code==206 and result.content==normalized.read_bytes()[:20]
    cleanup.request(batch)
    assert cleanup.cleanup_one(batch)=='completed'
    assert not (thumbs/'uploads'/str(batch)/'.normalized').exists()


def test_frame_sampling_last_frame_and_alternative_video_format(tmp_path,clips):
    mp4,mov=clips
    frames=tmp_path/'frames'
    frames.mkdir()
    found=video.extract_frames(mp4,frames)
    assert len(found)==8
    with (tmp_path/'timeline').open('w+b') as index:
        for n in range(15):index.write(f"frame|best_effort_timestamp_time={n}\n".encode())
        index.seek(0)
        assert video._pick_indices(index)==list(range(0,15,2))
    webm=tmp_path/'alt.webm'
    progress=[]
    assert video.encode(mov,webm,'webm',progress=progress.append,cpus=4).codec=='vp9'
    assert any(seconds>0 for seconds in progress)
    assert formats.inspect(webm,'alt.webm','video/webm','png','webm')[0]=='keep'


def test_bad_file_does_not_poison_fifo_and_retry_has_own_history(thumbs,clips,monkeypatch):
    monkeypatch.setattr(media_prepare,'DATA_DIR',thumbs)
    batch=_batch(thumbs,with_photo=False)
    # Valid file header for recognition by libmagic, not a decodable video.
    broken=b'\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  '
    saved=_import(thumbs,batch,[('bad.mov',broken),('ok.jpg',_jpg())])
    with database.connect() as db:
        task=work_queue.claim_next(db)
    media_prepare.run(task,stopping=lambda:False)
    assert batches.get(batch)['media_preparation']['state']=='completed_with_errors'
    assert media_preparation.file_errors(batch)['files'][0]['filename']=='bad.mov'
    assert Path(saved[0][1]['path']).read_bytes()==broken
    media_preparation.retry(batch)
    history=queue_api.list_work_queue(scope='history')['tasks']
    assert history[0]['failed_count']==1
    cleanup.request(batch)
    assert cleanup.cleanup_one(batch)=='completed'


def test_conflicting_frames_abstain():
    def match(label):
        return {'individual_top':[{'label':label,'score':.9,'reference':'ref'}]}
    assert not sorting.video_vote('clip',[match('A')]*7+[match('B')])['top']
    assert not sorting.video_vote('clip',[match('A')]+[{}]*7)['top']
    assert sorting.video_vote('clip',[match('A')]*6+[{}]*2)['top'][0]['label']=='A'
