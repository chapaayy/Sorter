"""A prepared reference is read from its cache, not run through MegaLoc again."""
from contextlib import nullcontext
import hashlib

import numpy as np

from server import reference_cache


def test_reference_cache_distinguishes_reads_from_inference(tmp_path,monkeypatch):
    root=tmp_path/"reference_staging"
    root.mkdir()
    hit,miss=root/"prepared.jpg",root/"missing.jpg"
    hit.write_bytes(b"prepared")
    miss.write_bytes(b"missing")
    fo=tmp_path/"FO.jpg"
    fo.write_bytes(b"FO")
    db=type("DB",(),{"execute":lambda *a:None})()
    inferred=[]

    class Engine:
        performance=None

        def extract_many(self,paths,*,stop=None):
            for path in paths:
                inferred.append(path)
                yield path,np.array([0.,1.],dtype=np.float32),None

    def lookup(db,digest,fingerprint):
        if digest==hashlib.sha256(b"prepared").hexdigest():
            return np.array([1.,0.],dtype=np.float32)
        return None

    monkeypatch.setattr(reference_cache,"REFERENCE_ROOT",root)
    monkeypatch.setattr(reference_cache,"CACHE_DIR",tmp_path/"cache")
    monkeypatch.setattr(reference_cache,"signature",lambda:"test-signature")
    monkeypatch.setattr(reference_cache,"connect",lambda:nullcontext(db))
    monkeypatch.setattr(reference_cache,"cached_feature",lookup)
    wrapper=reference_cache.ReferenceCachedMegaLoc(Engine())
    list(wrapper.extract_many([fo]))
    rows=list(wrapper.extract_many([hit,miss]))
    assert [row[0] for row in rows]==[hit,miss]
    assert inferred==[fo,miss]
    assert (wrapper.reference_cache_hits,wrapper.reference_cache_misses)==(1,1)
    assert list((tmp_path/"cache").glob("*.npy"))
