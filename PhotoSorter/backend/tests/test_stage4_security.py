"""Stage4 safety regression on synthetic data / disposable PostgreSQL."""
from __future__ import annotations
import hashlib
import uuid
import pytest
from fastapi import HTTPException
from .test_stage1_lifecycle import _batch,_job,sandbox,db
from .test_stage2_platform import thumbs,_jpg
from server.database import connect

def test_login_limit_is_bounded_and_recovers():
    from server.security.login_throttle import LoginThrottle,WINDOW,ATTEMPTS
    clock=[1000.0]
    gate=LoginThrottle(clock=lambda:clock[0])
    for _ in range(ATTEMPTS):
        gate.check("admin","127.0.0.1")
        gate.fail("admin","127.0.0.1")
    with pytest.raises(HTTPException) as exc:
        gate.check("admin","127.0.0.1")
    assert exc.value.status_code==429
    with pytest.raises(HTTPException):
        gate.check("other","127.0.0.1")
    clock[0]+=WINDOW+1
    gate.check("admin","127.0.0.1")
    gate.succeed("admin","127.0.0.1")

@pytest.mark.parametrize("sam,file",[
    ("..","a.jpg"),("../evil","a.jpg"),("SAM-0001/../../etc","a.jpg"),
    ("SAM-0001","../secret.jpg"),("SAM-0001","dir/file.jpg"),
    ("SAM-0001","a\\b.jpg"),("SAM-0001","evil\x00.jpg"),("","a.jpg")
])
def test_zip_rejects_manifest_path_escape(sam,file):
    from server.api.routes.downloads import archive_member
    with pytest.raises(HTTPException) as exc:archive_member(sam,file)
    assert exc.value.status_code==422

def test_zip_valid_sam_names():
    from server.api.routes.downloads import archive_member
    assert archive_member("SAM-0217-A","84fa_photo.jpg")=="SAM-0217-A/84fa_photo.jpg"
    assert archive_member("_Неопределено","photo.jpg")=="_Неопределено/photo.jpg"

def test_large_image_pixel_bomb_is_rejected_before_publishing(thumbs,monkeypatch):
    from server import uploads
    from server.services import cleanup
    own=_batch(thumbs,with_photo=False)
    raw=_jpg()
    item=uuid.uuid4()
    uploads._create_upload(uploads.BeginUpload(kind="fo",filename="huge.jpg",size=len(raw),
        batch_id=str(own)),item)
    (thumbs/"incoming"/f"{item}.part").write_bytes(raw)
    class Huge:
        width=uploads.PIXEL_LIMIT+1
        height=1
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def verify(self):raise AssertionError("must check pixels before verify")
    monkeypatch.setattr(uploads.Image,"open",lambda path:Huge())
    with pytest.raises(HTTPException) as exc:uploads._finalize_sync(str(item))
    assert exc.value.status_code==422
    with connect() as db:
        assert not db.execute("SELECT 1 FROM uploads WHERE id=%s AND finalized",(item,)).fetchone()
    cleanup.request(own)
    cleanup.cleanup_one(own)
