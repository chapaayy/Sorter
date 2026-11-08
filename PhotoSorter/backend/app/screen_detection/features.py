"""EXIF-oriented originals, sparse XFeat extraction and border-only masking."""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps

MAX_SIDE=1280
TOP_K=4096
MAX_PIXELS=45_000_000

def oriented_image(path:Path)->np.ndarray:
    with Image.open(path) as image:
        width,height=image.size
        if width*height>MAX_PIXELS or min(width,height)<32:
            raise ValueError("Изображение слишком большое или маленькое")
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB")).copy()

def prepare(rgb:np.ndarray)->tuple[np.ndarray,float]:
    height,width=rgb.shape[:2]
    scale=min(1.,MAX_SIDE/max(height,width))
    if scale<1:
        rgb=cv2.resize(rgb,(max(32,round(width*scale)),max(32,round(height*scale))),
                       interpolation=cv2.INTER_AREA)
    return rgb,float(rgb.shape[1])/width

def extract(model,rgb:np.ndarray)->dict:
    import torch
    frame,scale=prepare(rgb)
    input_tensor=torch.from_numpy(np.ascontiguousarray(frame)).permute(2,0,1)
    input_tensor=input_tensor.unsqueeze(0).float().div_(255)
    with torch.inference_mode():
        result=model.detectAndCompute(input_tensor,top_k=TOP_K)[0]
    points=result["keypoints"].cpu().numpy().astype("float32")/scale
    vectors=result["descriptors"].cpu().numpy().astype("float32")
    return {"xy":points,"descriptors":vectors}

def border_features(features:dict,corners:list[dict],band:float,
                    width:int,height:int)->dict:
    """Only points in finite strips along the four physical frame edges."""
    points=features["xy"]
    # Keep the full oriented coordinate space: no screen-ad pixels or perspective warp.
    polygon=np.array([[p["x"],p["y"]] for p in corners],dtype=np.float32)
    side=np.roll(polygon,-1,axis=0)-polygon
    lengths=np.einsum("ij,ij->i",side,side)
    if np.any(lengths<4):raise ValueError("Вырожденные стороны экрана")
    delta=points[:,None,:]-polygon[None,:,:]
    t=np.clip(np.einsum("nsi,si->ns",delta,side)/lengths,0,1)
    closest=polygon[None,:,:]+t[:,:,None]*side[None,:,:]
    distances=np.linalg.norm(points[:,None,:]-closest,axis=2)
    side_ids=np.argmin(distances,axis=1)
    # Even a deliberately thick search strip must not include the centre
    # of a changing advertisement. The inward width is capped relative to
    # the physical screen edge; the outward context may use the full band.
    inward=min(float(band),max(2.,float(np.sqrt(lengths).min())*.12))
    signed=np.array([cv2.pointPolygonTest(polygon,(float(x),float(y)),True)
                     for x,y in points],dtype=np.float32)
    keep=(np.min(distances,axis=1)<=band)&(signed<=inward)
    return {"xy":points[keep],"descriptors":features["descriptors"][keep],
            "sides":side_ids[keep].astype("uint8")}

def match(reference:dict,query:dict,min_similarity:float=.82)->tuple[np.ndarray,np.ndarray,np.ndarray]:
    """Mutual nearest-neighbour on L2-normalized official 64D descriptors."""
    a,b=reference["descriptors"],query["descriptors"]
    if len(a)==0 or len(b)==0:
        return np.empty((0,2),dtype="float32"),np.empty((0,2),dtype="float32"),np.empty((0,),dtype="uint8")
    # Bound transient memory and CPU: query descriptors retained only for one FO.
    best_ref=np.full(len(a),-1,dtype=np.int32)
    best_score=np.full(len(a),-2,dtype=np.float32)
    best_query=np.full(len(b),-1,dtype=np.int32)
    query_score=np.full(len(b),-2,dtype=np.float32)
    for begin in range(0,len(a),256):
        score=a[begin:begin+256]@b.T
        ix=np.argmax(score,axis=1)
        val=score[np.arange(len(ix)),ix]
        best_ref[begin:begin+len(ix)]=ix
        best_score[begin:begin+len(ix)]=val
        other=np.argmax(score,axis=0)
        other_val=score[other,np.arange(len(b))]
        changed=other_val>query_score
        best_query[changed]=other[changed]+begin
        query_score[changed]=other_val[changed]
    ids=np.arange(len(a),dtype=np.int32)
    good=(best_score>=min_similarity)&(best_query[best_ref]==ids)
    a_ids=ids[good]
    return (reference["xy"][a_ids],query["xy"][best_ref[good]],
            reference["sides"][a_ids])
