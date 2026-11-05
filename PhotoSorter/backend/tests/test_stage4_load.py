"""End-to-end 1315 *synthetic* photo metadata and ZIP stream on disposable Linux/PG.

Not a 6.4 GiB or MegaLoc inference benchmark. No real model weights/photos.
"""
from __future__ import annotations
import asyncio
import hashlib
import io
import json
import os
import time
import uuid
import zipfile
from pathlib import Path
import pytest

from .test_stage1_lifecycle import _batch,_job,sandbox,db
from server.database import connect
from server.storage import paths

def _read_zip(response):
    async def drain():
        content=bytearray()
        async for chunk in response.body_iterator:content.extend(chunk)
        return bytes(content)
    return asyncio.run(drain())

def test_1315_synthetic_hardlinks_full_zip_filters_and_cleanup(sandbox,monkeypatch):
    from server.services import result_pages,cleanup
    from server.api.routes import downloads,images
    from app.results import repository
    monkeypatch.setattr(result_pages,"DATA_DIR",sandbox)
    # Legacy safe_manifest reads run index; outputs symlink ownership checked.
    own=_batch(sandbox)
    source=next(paths.batch_dir(own).iterdir())
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    run=_job(sandbox,own)
    output=sandbox/"outputs"/run/"megaloc"
    output.mkdir(parents=True)
    (sandbox/"runs"/run/"models").mkdir(parents=True)
    records=[]
    sam_counts={"SAM-0001":0,"SAM-0002":0,"_Неопределено":0}
    for i in range(1315):
        label=["SAM-0001","SAM-0002","_Неопределено"][i%3]
        sam_counts[label]+=1
        folder=output/label
        folder.mkdir(exist_ok=True)
        linked=folder/f"fo_{i:04d}.jpg"
        os.link(source,linked)
        records.append({"query":str(source),"copy":str(linked),"assigned_sam":label,
            "group_id":f"G{i//40:04d}","score":round((i%100)/100,2),
            "top":[{"label":label,"score":round((i%100)/100,2)}] if label!="_Неопределено" else []})
    (output/"manifest.json").write_text(json.dumps(records,ensure_ascii=False),encoding="utf8")
    with (output/"manifest.rows.jsonl").open("w",encoding="utf8") as f:
        for i,row in enumerate(records):f.write(json.dumps({"index":i,**row},ensure_ascii=False)+"\n")
    (sandbox/"runs"/run/"models"/"megaloc.json").write_text(json.dumps({"path":str(output/"manifest.json")}))

    start=time.perf_counter()
    assert result_pages.counts(run)["sam"]==sam_counts
    cursor=None
    seen=[]
    while True:
        page=result_pages.page(run,cursor=cursor,limit=73)
        seen.extend(r["index"] for r in page["rows"])
        cursor=page["next_cursor"]
        if not cursor:break
    assert seen==list(range(1315))
    archive=_read_zip(downloads.download_results(run))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert len(z.namelist())==1315
        assert len(set(z.namelist()))==1315
        assert z.read("SAM-0001/fo_0000.jpg")==source.read_bytes()
        assert len([n for n in z.namelist() if n.startswith("_Неопределено/")])==sam_counts["_Неопределено"]
        assert z.testzip() is None
    partial=_read_zip(downloads.download_results(run,sam="SAM-0001"))
    with zipfile.ZipFile(io.BytesIO(partial)) as z:
        assert len(z.namelist())==sam_counts["SAM-0001"]
        assert all(n.startswith("SAM-0001/") for n in z.namelist())
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert (source.stat().st_ino,source.stat().st_dev)==(
        (output/"SAM-0001"/"fo_0000.jpg").stat().st_ino,(output/"SAM-0001"/"fo_0000.jpg").stat().st_dev)
    with connect() as database:
        assert database.execute("SELECT count(*) AS c FROM batch_operations WHERE batch_id=%s",(own,)).fetchone()["c"]==0
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="completed"
    assert not output.exists() and not paths.batch_dir(own).exists()
    assert time.perf_counter()-start<120, "Disposable metadata/stream test timed out"

def test_retention_exact_utc_month_edges_and_nonconfirmed_guard(sandbox):
    from server.services import retention,cleanup
    own=_batch(sandbox,with_photo=False)
    assert retention.status(own)["delete_after_at"] is None
    assert own not in retention.due_batch_ids(limit=1000)
    with connect() as db:
        cases=[
            ("2026-01-31 12:00:00","2026-03-31 12:00:00"),
            ("2024-02-29 12:00:00","2024-04-29 12:00:00"),
            ("2026-11-30 12:00:00","2027-01-30 12:00:00")
        ]
        for start,expected in cases:
            value=db.execute("SELECT (%s::timestamp + interval '2 months') AS deadline",(start,)).fetchone()["deadline"]
            assert str(value)==expected
    cleanup.request(own)
    assert cleanup.cleanup_one(own)=="completed"
