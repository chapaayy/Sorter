"""Persistent cache ONLY for SAM references; queried after FO grouping finishes.

Cache entries are keyed by image content and the actual MegaLoc checkpoint/source
signature. No incoming FO is written to the feature cache.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Iterable, Callable
import numpy as np
from app.config import DATA_DIR
from app.system.model_store import signature
from .database import connect

REFERENCE_ROOT=(DATA_DIR/'reference_staging').resolve()
CACHE_DIR=DATA_DIR/'cache'/'megaloc'/'references'

def cached_feature(db,digest,fingerprint):
    """Validate the stored vector before trusting a DB cache hit."""
    row=db.execute("""SELECT cache_path FROM reference_cache
        WHERE source_hash=%s AND model_signature=%s""",(digest,fingerprint)).fetchone()
    if not row:return None
    target=Path(row["cache_path"])
    if not target.resolve().is_relative_to(CACHE_DIR.resolve()) or not target.is_file():
        return None
    try:
        arr=np.load(target,allow_pickle=False)
        if arr.ndim==1 and arr.size>0 and np.isfinite(arr).all():
            return arr.astype('float32')
    except (OSError,ValueError,EOFError):
        pass
    return None


class ReferenceCachedMegaLoc:
    name='megaloc'
    device='cpu'
    def __init__(self, engine):
        self.engine=engine
        self.performance=engine.performance
        self.fingerprint=signature()
        if not self.fingerprint:raise RuntimeError('Отсутствует проверяемая версия MegaLoc')
        CACHE_DIR.mkdir(parents=True,exist_ok=True)

    def extract(self,path):
        return next(self.extract_many([path]))[1]

    def extract_many(self, paths:Iterable[Path], *, stop:Callable[[],bool]|None=None):
        paths=[Path(p) for p in paths]
        if not paths:return
        # FO always uses the original bounded batched extractor.
        if not all(p.resolve().is_relative_to(REFERENCE_ROOT) for p in paths):
            yield from self.engine.extract_many(paths,stop=stop)
            return
        cached={};missing=[];hashes={}
        with connect() as db:
            for path in paths:
                if stop and stop():raise InterruptedError('Остановлено')
                try:
                    with path.open('rb') as stream:
                        digest=hashlib.file_digest(stream,'sha256').hexdigest()
                    hashes[path]=digest
                    vector=cached_feature(db,digest,self.fingerprint)
                    if vector is not None:
                        cached[path]=(vector,None)
                        continue
                    missing.append(path)
                except Exception as exc:cached[path]=(None,exc)
        # Stream each completed feature directly to the worker's progress
        # reporter. Formerly generated{} buffered a whole CPU batch.
        generated=iter(self.engine.extract_many(missing,stop=stop)) if missing else iter(())
        for path in paths:
            if path in cached:
                vector,error=cached[path]
                yield path,vector,error
                continue
            actual,vector,error=next(generated)
            if actual!=path:
                raise RuntimeError("MegaLoc reference extraction order changed")
            if error is None and vector is not None:
                digest=hashes[path]
                cache=CACHE_DIR/f'{self.fingerprint[:16]}_{digest}.npy'
                tmp=cache.with_name(cache.name+'.tmp-'+os.urandom(4).hex())
                try:
                    with tmp.open('wb') as stream:
                        np.save(stream,np.asarray(vector,dtype='float32'),allow_pickle=False)
                    tmp.replace(cache)
                    with connect() as db:
                        db.execute('INSERT INTO reference_cache(source_hash,model_signature,cache_path) '
                                   'VALUES (%s,%s,%s) ON CONFLICT(source_hash,model_signature) '
                                   'DO UPDATE SET cache_path=excluded.cache_path',
                                   (digest,self.fingerprint,str(cache)))
                finally:
                    tmp.unlink(missing_ok=True)
            yield path,vector,error

    def unload(self):self.engine.unload()
