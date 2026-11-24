"""Persistent content/model-addressed reference embeddings, never FO vectors."""
from __future__ import annotations
import hashlib
import io
from pathlib import Path
from typing import Iterable, Callable
import numpy as np
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_path,digest_key
from app.storage.filesystem import safe_read,atomic_write
from app.system.model_store import signature
from .database import connect
from .storage.reference_objects import object_root,object_path

def location(digest,fingerprint):
    digest=digest_key(digest)
    return managed_path(Category.REFERENCE_EMBEDDING,model_signature=fingerprint,prefix=digest[:2],sha256=digest)

def valid_vector(arr):
    return (isinstance(arr,np.ndarray) and arr.dtype==np.float32 and arr.ndim==1
            and 0<arr.size<=1_000_000 and np.isfinite(arr).all()
            and np.linalg.norm(arr.astype(np.float64))>0)

def cached_feature(db,digest,fingerprint):
    row=db.execute("""SELECT cache_path,vector_sha256,dimensions FROM reference_cache
        WHERE source_hash=%s AND model_signature=%s""",(digest,fingerprint)).fetchone()
    if not row:return None
    target=location(digest,fingerprint)
    if Path(row["cache_path"])!=target:return None
    try:
        with safe_read(config.APP_STORAGE_ROOT,target.relative_to(config.APP_STORAGE_ROOT)) as stream:
            raw=stream.read(4_100_001)
        if len(raw)>4_100_000 or hashlib.sha256(raw).hexdigest()!=row['vector_sha256']:return None
        arr=np.load(io.BytesIO(raw),allow_pickle=False)
        if valid_vector(arr) and arr.size==row['dimensions']:return arr
    except (OSError,ValueError,EOFError):pass
    return None

class ReferenceCachedMegaLoc:
    name='megaloc'
    device='cpu'
    def __init__(self,engine):
        self.engine=engine
        self.performance=engine.performance
        self.fingerprint=digest_key(signature())
        self.reference_cache_hits=0
        self.reference_cache_misses=0

    def extract(self,path):
        return next(self.extract_many([path]))[1]

    def extract_many(self,paths:Iterable[Path],*,stop:Callable[[],bool]|None=None):
        paths=[Path(p) for p in paths]
        if not paths:return
        if not all(p.is_relative_to(object_root()) for p in paths):
            yield from self.engine.extract_many(paths,stop=stop)
            return
        found={};missing={}
        with connect() as db:
            for path in dict.fromkeys(paths):
                if stop and stop():raise InterruptedError('Остановлено')
                try:
                    digest=digest_key(path.name)
                    if path!=object_path(digest):raise ValueError("Invalid reference path")
                    with safe_read(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT)) as stream:
                        if hashlib.file_digest(stream,'sha256').hexdigest()!=digest:
                            raise ValueError("Reference content mismatch")
                    vector=cached_feature(db,digest,self.fingerprint)
                    if vector is not None:found[path]=(vector,None)
                    else:missing[path]=digest
                except (OSError,ValueError) as exc:found[path]=(None,exc)
        self.reference_cache_hits+=sum(error is None for _,error in found.values())
        self.reference_cache_misses+=len(missing)
        if missing:
            for path,vector,error in self.engine.extract_many(list(missing),stop=stop):
                path=Path(path)
                if error is None:
                    vector=np.asarray(vector,dtype=np.float32)
                    if not valid_vector(vector):error=ValueError("Invalid MegaLoc feature")
                found[path]=(vector,error)
                if error is not None:continue
                digest=missing[path]
                target=location(digest,self.fingerprint)
                # Persist intent before atomic publication so a crash never creates
                # an untracked canonical cache object. A missing file is a cache miss.
                buffer=io.BytesIO()
                np.save(buffer,vector,allow_pickle=False)
                raw=buffer.getvalue()
                with connect() as db:
                    db.execute("""INSERT INTO reference_cache(source_hash,model_signature,cache_path,unowned_since,vector_sha256,dimensions)
                        VALUES (%s,%s,%s,NULL,%s,%s) ON CONFLICT(source_hash,model_signature)
                        DO UPDATE SET cache_path=excluded.cache_path,unowned_since=NULL,
                            vector_sha256=excluded.vector_sha256,dimensions=excluded.dimensions""",(digest,self.fingerprint,str(target),hashlib.sha256(raw).hexdigest(),int(vector.size)))
                with atomic_write(config.APP_STORAGE_ROOT,target.relative_to(config.APP_STORAGE_ROOT),expected_size=len(raw)) as stream:
                    stream.write(raw)
        for path in paths:
            vector,error=found.get(path,(None,RuntimeError('Missing feature')))
            yield path,vector,error

    def unload(self):self.engine.unload()
