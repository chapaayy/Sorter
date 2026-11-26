"""Real MegaLoc acceptance in disposable CI containers. No fake engine or weights."""
from __future__ import annotations
import hashlib
import os
import sys
import urllib.request
import uuid
from pathlib import Path
import numpy as np
from app import config
from app.system import model_store
from app.storage.categories import Category
from app.storage.paths import managed_prefix

NAME="CI_REAL_MEGALOC_STAGE5"
PHOTOS={
    "china.jpg":"e6105b5d477883e457ce3cbdd526adac65f3ac47",
    "flower.jpg":"988f972277f1acbbb15fbf07a7d790953fd3540f",
}
def fetch_photo(name):
    url="https://raw.githubusercontent.com/scikit-learn/scikit-learn/1.5.2/sklearn/datasets/images/"+name
    with urllib.request.urlopen(url,timeout=45) as response:
        data=response.read(1_000_001)
    assert len(data)<1_000_001
    assert hashlib.sha1(f"blob {len(data)}".encode()+bytes([0])+data).hexdigest()==PHOTOS[name]
    return data

def prepare():
    from app.system.downloads import Downloads
    from server import database,uploads
    from server.api.routes.reference_imports import ImportFile
    from server.api.routes.batches import ManifestFile
    from server.services import batches,regions,reference_imports,reference_uploads,upload_manifest
    from server.storage.paths import part_path
    Downloads().install()
    assert model_store.verified()
    database.initialize()
    regions.register("SAM")
    raw={name:fetch_photo(name) for name in PHOTOS}
    items=[ImportFile(upload_id=uuid.uuid4(),sam=f"SAM 98{i:02}",address=f"CI {i}",
            relative_path=f"SAM 98{i:02} — CI {i}/{name}",filename=name,size=len(data),
            sha256=hashlib.sha256(data).hexdigest()) for i,(name,data) in enumerate(raw.items(),1)]
    sid=uuid.uuid4()
    reference_imports.create(sid)
    reference_imports.register_manifest(sid,items)
    for item in items:
        reference_uploads.append(sid,item.upload_id,0,raw[item.filename])
        reference_uploads.finish(sid,item.upload_id)
    with database.connect() as db:
        owner=db.execute("SELECT id FROM users WHERE username='admin'").fetchone()["id"]
    batch=uuid.UUID(batches.create(NAME,owner_id=owner)["batch_id"])
    files=[ManifestFile(upload_id=uuid.uuid4(),relative_path=f"CI/{name}",filename=name,size=len(data))
           for name,data in raw.items()]
    upload_manifest.register(batch,files,image_format="jpg",video_format="mp4")
    for item in files:
        data=raw[item.filename]
        payload=uploads.BeginUpload(kind="fo",filename=item.filename,size=len(data),batch_id=str(batch),
                                    sha256=hashlib.sha256(data).hexdigest())
        uploads._create_upload(payload,item.upload_id)
        offset=uploads._append_chunk(part_path(batch,item.upload_id),0,data,len(data))
        uploads._record_chunk(item.upload_id,offset)
        uploads._finalize_sync(str(item.upload_id))
    print("REAL_ASSETS_AND_PHOTOS_READY",model_store.signature(),flush=True)

def offline_route():
    # Docker internal bridge has PostgreSQL connectivity, no external route.
    routes=Path("/proc/net/route").read_text().splitlines()[1:]
    assert not any(line.split()[1]=="00000000" for line in routes),routes

def sort(phase):
    offline_route()
    from app.system.downloads import Downloads
    from app.results.repository import load_model
    from server import database,jobs,reference_cache
    from server.db.repositories import work_queue
    from server.services import thumbnails
    from server.workers import reference_prepare
    from server.workers.warm_megaloc import WarmMegaLoc
    assert model_store.verified()
    weight=model_store.checkpoint()
    st=weight.stat()
    # Even explicit repeated install is a no-op offline.
    Downloads().install()
    assert weight.stat().st_ino==st.st_ino and weight.stat().st_mtime_ns==st.st_mtime_ns
    database.initialize()
    warm=WarmMegaLoc()
    try:
        with database.connect() as db:
            batch=db.execute("SELECT id FROM batches WHERE display_name=%s",(NAME,)).fetchone()["id"]
            if phase=="before":
                preparation=work_queue.claim_next(db)
                assert preparation["kind"]=="reference_preparation"
            else:
                preparation=None
                previous=db.execute("SELECT id,snapshot FROM jobs WHERE batch_id=%s AND status='completed' ORDER BY created_at LIMIT 1",(batch,)).fetchone()
                assert previous
        if preparation:
            result=reference_prepare.run(preparation["id"],warm_megaloc=warm)
            assert result["changed"] and result["version"]>=2
        with database.connect() as db:
            entries=db.execute("SELECT source_hash,model_signature,cache_path,vector_sha256,dimensions FROM reference_cache ORDER BY source_hash").fetchall()
            assert len(entries)==2
            for row in entries:
                arr=reference_cache.cached_feature(db,row["source_hash"],row["model_signature"])
                assert arr is not None and arr.shape==(8448,) and np.isfinite(arr).all()
        stamps={row["cache_path"]:(Path(row["cache_path"]).stat().st_ino,Path(row["cache_path"]).stat().st_mtime_ns)
                for row in entries}
        while (task:=thumbnails.claim()) is not None:
            assert thumbnails.complete(task)=="ready"
        run=jobs.enqueue(jobs.NewRun(batch_id=batch,grouping_threshold=.99))["id"]
        with database.connect() as db:
            task=work_queue.claim_next(db)
        assert task["id"]==run and task["kind"]=="fo_processing"
        job=jobs.ServerJob(task["info"],warm_megaloc=warm)
        job.run()
        assert job.info["status"]=="completed",job.info
        stats=job.info["models"]["megaloc"]["performance"]
        assert stats["reference_cache_hits"]==2 and stats["reference_cache_misses"]==0,stats
        rows=load_model(run,"megaloc")
        assert len(rows)==2 and all(row["assigned_sam"].startswith("SAM 98") for row in rows),rows
        assert len({row["assigned_sam"] for row in rows})==2,rows
        for row in entries:
            path=Path(row["cache_path"])
            assert (path.stat().st_ino,path.stat().st_mtime_ns)==stamps[str(path)]
        if phase=="after":
            old=load_model(previous["id"],"megaloc")
            assert {r["query"]:r["assigned_sam"] for r in old}=={r["query"]:r["assigned_sam"] for r in rows}
            assert previous["snapshot"]["model_signature"]==job.info["model_signature"]
        print("REAL_FO_"+phase.upper(),stats,"signature",model_store.signature(),flush=True)
    finally:warm.close()

def isolated_inference():
    offline_route()
    from app.recognition.engines.megaloc.extractor import MegaLocEngine
    from server.storage.reference_objects import object_root
    from server.reference_cache import location
    assert model_store.verified()
    engine=MegaLocEngine()
    try:
        for path in sorted(object_root().glob("*/*")):
            arr=engine.extract(path)
            previous=np.load(location(path.name,model_store.signature()),allow_pickle=False)
            assert arr.shape==(8448,) and np.isfinite(arr).all()
            assert np.allclose(arr,previous,rtol=1e-4,atol=1e-5)
        print("REAL_NETWORK_NONE_INFERENCE_OK",flush=True)
    finally:engine.unload()

def purge():
    from app.system.technical_cache import clear_disposable
    from server.storage.reference_objects import object_root
    def protected():
        roots=[object_root(),managed_prefix(Category.REFERENCE_EMBEDDING),managed_prefix(Category.REFERENCE_THUMBNAIL),
               managed_prefix(Category.FO_THUMBNAIL)]
        files=[]
        for root in roots:
            files.extend(path for path in root.rglob("*") if path.is_file() and
                         (root!=roots[-1] or path.suffix==".webp"))
        return {str(path):(path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns) for path in files}
    before=protected()
    assert before
    for provider in ("torch","huggingface","xdg"):
        directory=managed_prefix(Category.TECHNICAL_CACHE,provider=provider)
        directory.mkdir(parents=True,exist_ok=True)
        (directory/"ci-disposable").write_bytes(b"cache")
    clear_disposable()
    assert all(not managed_prefix(Category.TECHNICAL_CACHE,provider=p).exists() for p in ("torch","huggingface","xdg"))
    assert protected()==before and model_store.verified()
    print("PROVIDER_CACHE_PURGE_OK",flush=True)

if __name__=="__main__":
    phase=sys.argv[1]
    if phase=="prepare":prepare()
    elif phase in ("before","after"):sort(phase)
    elif phase=="network-none":isolated_inference()
    elif phase=="purge":purge()
    else:raise ValueError(phase)
