"""Targeted Stage 1 layout preparation tests (real PostgreSQL, synthetic model results)."""
from __future__ import annotations

import io
import uuid

import numpy as np
from PIL import Image

from app.ad_recognition import dino,embedding_cache,ocr
from server.database import connect
from server.services import ad_layouts,ad_pipeline_settings
from server.workers import ad_layout_prepare
from .test_unified_queue_stage3 import system


def _image():
    buffer=io.BytesIO()
    Image.new("RGB",(160,100),"white").save(buffer,format="PNG")
    return buffer.getvalue()


def _claim_layout(layout_id):
    with connect() as db:
        prep=db.execute("""SELECT id FROM ad_layout_preparation_jobs
            WHERE layout_id=%s AND state='queued' ORDER BY created_at DESC LIMIT 1""",
            (layout_id,)).fetchone()
        assert prep
        db.execute("UPDATE ad_layout_preparation_jobs SET state='running' WHERE id=%s",
                   (prep["id"],))
        db.execute("UPDATE ad_layouts SET preparation_state='running' WHERE id=%s",
                   (layout_id,))
        db.execute("UPDATE work_queue SET state='running' WHERE layout_job_id=%s",
                   (prep["id"],))
    return prep["id"]


def test_fifo_layout_prepare_reuses_content_addressed_ocr_and_dino(system,monkeypatch):
    monkeypatch.setattr(ad_layouts,"ROOT",system/"ad_layouts")
    monkeypatch.setattr(embedding_cache,"ROOT",system/"cache"/"dinov2"/"layouts")
    monkeypatch.setattr(dino,"verify",lambda:True)
    monkeypatch.setattr(ocr,"status",lambda:{"available":True})
    monkeypatch.setattr(ocr,"signature",lambda:"fixture-ocr-model")
    calls={"dino":0,"ocr":0}

    def vector(model,row,filename):
        calls["dino"]+=1
        path=embedding_cache.ROOT/(embedding_cache.key(row["checksum"])+".npy")
        path.parent.mkdir(parents=True,exist_ok=True)
        arr=np.zeros(dino.EMBED_DIM,dtype="float32")
        arr[0]=1
        np.save(path,arr)
        return arr

    def read(engine,picture):
        calls["ocr"]+=1
        return [{"text":"Бигфест 11 ноября","score":.97,
                 "polygon":[[0,0],[120,0],[120,40],[0,40]]}]

    monkeypatch.setattr(dino,"load",lambda:object())
    monkeypatch.setattr(embedding_cache,"vector",vector)
    monkeypatch.setattr(ocr,"load",lambda:object())
    monkeypatch.setattr(ocr,"read",read)

    first=uuid.UUID(ad_layouts.create(_image(),"first.png","Первый")["id"])
    with connect() as db:
        assert db.execute("""SELECT count(*) AS total FROM work_queue
            WHERE kind='layout_preparation'""").fetchone()["total"]==1
    ad_layout_prepare.run(_claim_layout(first))
    layouts=ad_layouts.list_layouts()["layouts"]
    assert layouts[0]["preparation_state"]=="completed"
    assert layouts[0]["ocr_normalized_text"]=="бигфест 11 ноября"
    assert layouts[0]["ocr_raw_lines"][0]["score"]==.97
    assert len(ad_layouts.active_files())==1
    assert calls=={"dino":1,"ocr":1}

    # An equal-byte upload after removal can reuse both validated signatures.
    ad_layouts.delete(first)
    second=uuid.UUID(ad_layouts.create(_image(),"second.png","Второй")["id"])
    ad_layout_prepare.run(_claim_layout(second))
    assert calls=={"dino":1,"ocr":1}
    assert ad_layouts.list_layouts()["layouts"][0]["preparation_state"]=="completed"


def test_dino_thresholds_are_saved_and_frozen_for_disabled_claims(system):
    result=ad_pipeline_settings.update(grouping_threshold=.53,matching_threshold=.92)
    assert result["grouping_threshold"]==.53
    assert result["matching_threshold"]==.92
    from server.services.ad_pipeline_snapshot import capture
    with connect() as db:
        snapshot=capture(db,[])
    assert snapshot=={"enabled":False,"grouping_threshold":.53,"matching_threshold":.92}
