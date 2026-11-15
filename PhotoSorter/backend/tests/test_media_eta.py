from types import SimpleNamespace

import pytest

from server.media.estimate import Estimate, work
from server.media.video import thread_budget


def clip(seconds, *, pixels=2073600, fps=30, codec='hevc'):
    return SimpleNamespace(duration=seconds,pixels=pixels,fps=fps,codec=codec,
                           pixel_format='yuv420p',audio='aac')


def test_batch_estimate_counts_video_progress_and_remaining_videos():
    model=Estimate([work(2*1024**2,'jpg'),work(100,'mp4',clip(120),video=True),
                    work(100,'mp4',clip(60),video=True)])
    assert model.snapshot(0,0)==(0,None)
    model.observe(0,1,.5)
    percent,eta=model.snapshot(1,0)
    assert percent<1 and eta is None
    model.observe(1,.25,30)
    percent,eta=model.snapshot(1,.25)
    assert 16<percent<18
    assert eta==pytest.approx(150)
    percent,eta=model.snapshot(2,0)
    assert 66<percent<68
    assert eta==pytest.approx(60)
    assert model.snapshot(3,0)==(99.9,None)


def test_remux_and_photo_do_not_drive_encode_speed():
    remux=work(200*1024**2,'mp4',clip(150,codec='h264'),video=True)
    slow=work(200*1024**2,'mp4',clip(150,pixels=3840*2160,fps=60),video=True)
    model=Estimate([remux,slow])
    model.observe(0,1,2)
    percent,eta=model.snapshot(1,0)
    assert percent<1 and eta is None
    model.observe(1,.5,20)
    assert model.snapshot(1,.5)[1]==pytest.approx(20)
    assert thread_budget(7)==(2,5)
    assert thread_budget(1)==(1,1)
    assert sum(thread_budget(3))==3
