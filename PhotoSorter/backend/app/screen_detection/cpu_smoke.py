"""Real pretrained XFeat CPU-inference smoke; runs in disposable Docker CI."""
from __future__ import annotations
import json
import resource
import time
import cv2
import numpy as np
from .xfeat_assets import load_model,MODEL_ID
from .features import extract,match

def main():
    rng=np.random.default_rng(3245)
    # Synthetic image verifies actual pretrained inference, not field accuracy.
    rgb=rng.integers(0,256,(448,640,3),dtype=np.uint8)
    for y in range(35,445,55):
        for x in range(25,630,55):
            cv2.rectangle(rgb,(x,y),(x+30,y+22),(20,240,80),2)
    model=load_model()
    start=time.perf_counter()
    features=extract(model,rgb)
    seconds=round(time.perf_counter()-start,3)
    count=len(features["xy"])
    if count<25 or features["descriptors"].shape!=(count,64):
        raise RuntimeError("XFeat CPU inference returned invalid descriptors")
    ref={**features,"sides":np.zeros(count,dtype=np.uint8)}
    a,b,_=match(ref,features)
    if len(a)<15:raise RuntimeError("XFeat matching failed identical images")
    print(json.dumps({"model":"official pretrained XFeat","device":"cpu",
                      "features":count,"self_matches":len(a),
                      "seconds":seconds,
                      "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      "signature":MODEL_ID}))
if __name__=="__main__":main()
