"""Screen-ROI quality diagnostics, CPU-only, heuristic not a probability.

Measure only illuminated ad pixels inside XFeat's projected quadrilateral;
do not score the frame/background as screen sharpness. Small distant screens
are recorded as low-visibility rather than silently inventing detail.
"""
from __future__ import annotations
import cv2
import numpy as np
from PIL import Image

VERSION="screen-quality-cpu-v1"
MAX_SIDE=960

def assess(photo:Image.Image,screen:dict,original_size:tuple[int,int])->dict:
    rgb=np.asarray(photo.convert("RGB"))
    height,width=rgb.shape[:2]
    box=screen["crop_box"]
    quad=np.array([[p["x"]-box["x"],p["y"]-box["y"]] for p in screen["corners"]],
                  dtype=np.float32)
    if width<8 or height<8 or len(quad)!=4:
        return {"score":0.0,"status":"insufficient","reason":"Слишком маленький экран",
                "version":VERSION}
    scale=min(1.,MAX_SIDE/max(width,height))
    if scale<1.:
        target=(max(1,round(width*scale)),max(1,round(height*scale)))
        rgb=cv2.resize(rgb,target,interpolation=cv2.INTER_AREA)
    quad*=scale
    mask=np.zeros(rgb.shape[:2],dtype=np.uint8)
    cv2.fillConvexPoly(mask,np.rint(quad).astype("int32"),255)
    # Ignore boundary reflections, frame and camera edge artifacts.
    mask=cv2.erode(mask,np.ones((3,3),np.uint8),iterations=1)>0
    count=int(mask.sum())
    if count<100:
        return {"score":0.0,"status":"insufficient","reason":"Мало видимых пикселей",
                "version":VERSION}
    pixels=rgb[mask]
    grey=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    gray_values=grey[mask]
    lap=cv2.Laplacian(grey,cv2.CV_32F,ksize=3)[mask]
    # Squash outliers so a few saturated borders cannot dominate focus.
    sharp=float(np.clip(np.log1p(float(np.mean(lap*lap)))/np.log1p(1200),0,1))
    clipping=float(np.mean((gray_values<8)|(gray_values>247)))
    exposure=float(np.clip(1.-clipping*2.8,0,1))
    hi=np.max(pixels,axis=1).astype(np.int16)
    lo=np.min(pixels,axis=1).astype(np.int16)
    glare_fraction=float(np.mean((lo>243)&((hi-lo)<15)))
    glare=float(np.clip(1.-glare_fraction*4.,0,1))
    # Visible screen area relative to the ORIGINAL full frame, not the crop.
    full_area=max(1,original_size[0]*original_size[1])
    quad_area=abs(cv2.contourArea(np.array(
        [[p["x"],p["y"]] for p in screen["corners"]],dtype=np.float32)))
    coverage=float(np.clip(quad_area/(full_area*.10),0,1))
    result=100.*(.38*sharp+.24*exposure+.20*glare+.18*coverage)
    return {"score":round(result,2),"status":"measured","version":VERSION,
            "metrics":{"sharpness":round(sharp,4),"exposure":round(exposure,4),
                       "glare":round(glare,4),"screen_coverage":round(coverage,4),
                       "overexposed_or_black_fraction":round(clipping,4),
                       "glare_fraction":round(glare_fraction,4),
                       "screen_pixels":count}}
