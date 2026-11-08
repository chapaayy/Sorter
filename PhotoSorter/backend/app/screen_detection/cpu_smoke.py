"""Real pretrained XFeat CPU-inference smoke; runs in disposable Docker CI."""
from __future__ import annotations
import json
import resource
import time
import cv2
import numpy as np
from .xfeat_assets import load_model,MODEL_ID
from .features import extract,match
from .geometry import solve

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
    # Exercise the FULL screen homography through the final quad-area
    # validation. Previous smoke stopped after XFeat descriptor matching,
    # so the removed ndarray.ptp() went unnoticed on NumPy 2.x.
    corners=[{"x":80,"y":80},{"x":440,"y":80},
             {"x":440,"y":280},{"x":80,"y":280}]
    bounds=np.asarray([[p["x"],p["y"]] for p in corners],dtype=np.float32)
    points=[]
    sides=[]
    for side in range(4):
        for t in np.linspace(.08,.92,12):
            points.append(bounds[side]*(1-t)+bounds[(side+1)%4]*t)
            sides.append(side)
    ref_points=np.asarray(points,dtype=np.float32)
    photo_points=ref_points+np.asarray([150,90],dtype=np.float32)
    geometry=solve(ref_points,photo_points,np.asarray(sides,dtype=np.uint8),
                   corners,(1024,768))
    if geometry["status"]!="found":
        raise RuntimeError("XFeat screen geometry compatibility failed: "+
                           str(geometry.get("reason")))
    print(json.dumps({"model":"official pretrained XFeat","device":"cpu",
                      "numpy":np.__version__,"homography_status":geometry["status"],
                      "features":count,"self_matches":len(a),
                      "seconds":seconds,
                      "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      "signature":MODEL_ID}))
if __name__=="__main__":main()
