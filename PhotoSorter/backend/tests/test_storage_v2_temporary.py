import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from app import config
from app.storage.filesystem import atomic_write
from app.storage.temporary import collect_abandoned, temporary_operation, temporary_file, download_operation

def test_active_scratch_and_download_protected(tmp_path):
    with temporary_operation(tmp_path,"worker") as stage, download_operation(tmp_path) as (download,_):
        for folder in (stage,download):
            (folder/"payload").write_bytes(b"live")
            os.utime(folder,(1,1))
        assert collect_abandoned(tmp_path,grace_seconds=0)==0
        assert stage.exists() and download.exists()
    assert not stage.exists() and not download.exists()

def test_sigkill_atomic_writer_reclaimed_without_replacing_previous_file(tmp_path):
    target=tmp_path/"published"
    target.write_bytes(b"previous")
    code="""import sys,time
from pathlib import Path
from app.storage.filesystem import atomic_write
root=Path(sys.argv[1])
with atomic_write(root,'published') as f:
    f.write(b'incomplete')
    f.flush()
    print(next((root/'temporary/scratch/worker').iterdir()),flush=True)
    time.sleep(120)
"""
    env=dict(os.environ,MAP_SERVICE="worker")
    env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])
    proc=subprocess.Popen([sys.executable,"-c",code,str(tmp_path)],stdout=subprocess.PIPE,text=True,env=env)
    try:
        stage=Path(proc.stdout.readline().strip())
        assert stage.is_relative_to(tmp_path) and stage.exists()
        assert collect_abandoned(tmp_path,grace_seconds=0)==0
        proc.kill()
        proc.wait(timeout=10)
        assert target.read_bytes()==b"previous"
        unknown=stage.parent/"not-an-operation"
        unknown.mkdir()
        assert collect_abandoned(tmp_path,grace_seconds=0)==1
        assert not stage.exists() and unknown.exists()
        assert target.read_bytes()==b"previous"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

def test_anonymous_ffmpeg_style_file_accounting_and_close(tmp_path,monkeypatch):
    monkeypatch.setattr(config,"APP_STORAGE_ROOT",tmp_path)
    with temporary_file("worker") as stream:
        fd=stream.fileno()
        stream.write(b"x"*8192)
        stream.flush()
        assert os.fstat(fd).st_size==8192
        assert os.fstat(fd).st_blocks*512>=8192
        assert "/temporary/scratch/worker/" in os.readlink(f"/proc/self/fd/{fd}")
        assert collect_abandoned(tmp_path,grace_seconds=0)==0
    with pytest.raises(OSError):
        os.fstat(fd)
    assert not list((tmp_path/"temporary/scratch/worker").iterdir())

def test_failed_atomic_publish_releases_scratch(tmp_path):
    target=tmp_path/"file"
    target.write_bytes(b"old")
    with pytest.raises(RuntimeError):
        with atomic_write(tmp_path,"file") as stream:
            stream.write(b"new")
            raise RuntimeError("cancelled")
    assert target.read_bytes()==b"old"
    assert not list((tmp_path/"temporary/scratch/worker").iterdir())
