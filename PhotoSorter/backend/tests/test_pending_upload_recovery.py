"""Recover lost VPN acknowledgements without touching unrelated FO data.

All cases use the disposable PostgreSQL/filesystem fixtures.
"""
from __future__ import annotations
import asyncio
import uuid
import pytest

from server.database import connect
from server.services import batches,cleanup
from .test_stage2_platform import thumbs,_jpg
from .test_stage1_lifecycle import _batch


def test_complete_fo_parts_appear_as_pending_and_finalize_without_reupload(thumbs):
    from server import uploads
    batch=_batch(thumbs,with_photo=False)
    ids=[]
    try:
        for i in range(2):
            raw=_jpg(exif=bool(i))
            uid=uuid.uuid4()
            uploads._create_upload(uploads.BeginUpload(
                kind='fo',batch_id=str(batch),filename=f'IMG_{i}.JPG',size=len(raw)),uid)
            (thumbs/'incoming'/f'{uid}.part').write_bytes(raw)
            ids.append((uid,raw))

        before=batches.get(batch)
        assert before['photos']==0 and before['pending']==2
        entries=batches.pending_uploads(batch)['uploads']
        assert len(entries)==2
        assert all(e['can_finalize'] and e['received']==e['size'] for e in entries)
        assert all(len(e['prefix_sha256'])==64 for e in entries)
        for uid,_ in ids:
            assert uploads._finalize_sync(str(uid))['already_finalized'] is False
        after=batches.get(batch)
        assert after['photos']==2 and after['pending']==0
        assert batches.pending_uploads(batch)['uploads']==[]
        assert uploads._finalize_sync(str(ids[0][0]))['already_finalized'] is True
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_cancel_incomplete_session_keeps_all_finalized_photos(thumbs):
    from server import uploads
    batch=_batch(thumbs)
    raw=_jpg()
    uid=uuid.uuid4()
    try:
        uploads._create_upload(uploads.BeginUpload(
            kind='fo',batch_id=str(batch),filename='broken.jpg',size=len(raw)),uid)
        (thumbs/'incoming'/f'{uid}.part').write_bytes(raw[:100])
        assert batches.get(batch)['pending']==1
        assert batches.pending_uploads(batch)['uploads'][0]['received']==100
        assert asyncio.run(uploads.cancel_upload(str(uid)))=={'cancelled':True}
        assert batches.get(batch)['photos']==1
        assert batches.get(batch)['pending']==0
        assert not (thumbs/'incoming'/f'{uid}.part').exists()
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_create_idempotency_after_lost_response(thumbs):
    from server import uploads
    batch=_batch(thumbs,with_photo=False)
    uid=uuid.uuid4()
    payload=uploads.BeginUpload(kind='fo',batch_id=str(batch),filename='resume.jpg',
                                size=1234,client_upload_id=uid)
    try:
        first=uploads.create_upload(payload)
        second=uploads.create_upload(payload)
        assert first['id']==second['id']==str(uid)
        with connect() as db:
            assert db.execute("SELECT count(*) AS n FROM uploads WHERE id=%s",(uid,)).fetchone()['n']==1
        assert batches.get(batch)['pending']==1
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)


def test_missing_part_is_visible_but_cannot_be_auto_finalized(thumbs):
    from server import uploads
    batch=_batch(thumbs,with_photo=False)
    uid=uuid.uuid4()
    try:
        uploads._create_upload(uploads.BeginUpload(
            kind='fo',batch_id=str(batch),filename='missing.jpg',size=500),uid)
        (thumbs/'incoming'/f'{uid}.part').unlink()
        pending=batches.pending_uploads(batch)['uploads']
        assert len(pending)==1 and not pending[0]['has_part']
        assert not pending[0]['can_finalize']
    finally:
        cleanup.request(batch);cleanup.cleanup_one(batch)
