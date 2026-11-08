"""Conservative homography validation: refusing a guess is a valid outcome."""
from __future__ import annotations
import cv2
import numpy as np

MIN_MATCHES=12
MIN_INLIERS=10
MIN_RATIO=.35

def _fail(reason,matched=0,inliers=0,error=None,sides=None,debug=None):
    return {"status":"not_found","reason":reason,"matches":matched,"inliers":inliers,
            "reprojection_error_px":error,"supported_sides":sides or [],
            "debug_matches":debug or []}

def solve(ref_xy:np.ndarray,fo_xy:np.ndarray,sides:np.ndarray,
          corners:list[dict],image_size:tuple[int,int])->dict:
    n=len(ref_xy)
    if n<MIN_MATCHES:return _fail("Недостаточно совпадений XFeat",n)
    width,height=image_size
    if len(fo_xy)!=n or len(sides)!=n:
        return _fail("Несогласованные соответствия",n)
    if not np.isfinite(ref_xy).all() or not np.isfinite(fo_xy).all():
        return _fail("Некорректные точки",n)
    threshold=max(3.5,min(12.,max(width,height)*.0025))
    flag=getattr(cv2,"USAC_MAGSAC",cv2.RANSAC)
    H,mask=cv2.findHomography(ref_xy.astype("float32"),fo_xy.astype("float32"),
                            flag,threshold)
    if H is None or mask is None or not np.isfinite(H).all():
        return _fail("Гомография не вычислена",n)
    inliers=mask.ravel().astype(bool)
    count=int(inliers.sum())
    if count<MIN_INLIERS or count/n<MIN_RATIO:
        return _fail("Недостаточно геометрически согласованных точек",n,count)
    supported=[int(s) for s in range(4) if (sides[inliers]==s).sum()>=2]
    if len(supported)<3:
        return _fail("Совпадения сосредоточены на одной части рамки",n,count,sides=supported)
    p=ref_xy[inliers];q=fo_xy[inliers]
    if np.ptp(p,axis=0).min()<8 or np.ptp(q,axis=0).min()<8:
        return _fail("Почти коллинеарные точки",n,count,sides=supported)
    try:
        projected=cv2.perspectiveTransform(p.reshape(-1,1,2),H).reshape(-1,2)
        inverse=np.linalg.inv(H)
        back=cv2.perspectiveTransform(q.reshape(-1,1,2),inverse).reshape(-1,2)
        error=np.linalg.norm(projected-q,axis=1)
        reverse_error=np.linalg.norm(back-p,axis=1)
    except (np.linalg.LinAlgError,cv2.error):
        return _fail("Вырожденная гомография",n,count,sides=supported)
    median=float(np.median(error))
    if (not np.isfinite(reverse_error).all() or
        median>threshold or np.percentile(error,90)>threshold*1.75 or
        np.median(reverse_error)>max(8.,np.ptp(p,axis=0).max()*.02)):
        return _fail("Высокая ошибка переноса",n,count,median,supported)
    quad=np.array([[pt["x"],pt["y"]] for pt in corners],dtype=np.float32)
    result=cv2.perspectiveTransform(quad.reshape(-1,1,2),H).reshape(4,2)
    if not np.isfinite(result).all():
        return _fail("Контур вне изображения",n,count,median,supported)
    if (np.any(result[:,0]<0) or np.any(result[:,0]>width) or
        np.any(result[:,1]<0) or np.any(result[:,1]>height)):
        return _fail("Контур выходит за границы ФО",n,count,median,supported)
    vectors=np.roll(result,-1,axis=0)-result
    crosses=np.cross(vectors,np.roll(vectors,-1,axis=0))
    area=abs(float(cv2.contourArea(result)))
    if not (np.all(crosses>0) or np.all(crosses<0)) or not 0.00005<area/(width*height)<.8:
        return _fail("Нереалистичная форма или площадь экрана",n,count,median,supported)
    side_lengths=np.linalg.norm(vectors,axis=1)
    if side_lengths.min()<5 or side_lengths.max()/side_lengths.min()>30:
        return _fail("Слишком искажённая геометрия",n,count,median,supported)
    # Screen-frame features must be supported spatially on multiple sides.
    ref_center=quad.mean(axis=0)
    if np.linalg.norm(p.mean(axis=0)-ref_center)>float(np.ptp(quad,axis=0).max())*1.5:
        return _fail("Совпадения не относятся к экрану",n,count,median,supported)
    inds=np.flatnonzero(inliers)
    samples=[{"reference":[round(float(ref_xy[i,0]),2),round(float(ref_xy[i,1]),2)],
              "photo":[round(float(fo_xy[i,0]),2),round(float(fo_xy[i,1]),2)],
              "side":int(sides[i])} for i in inds[:80]]
    return {"status":"found","reason":"Геометрия подтверждена","matches":n,"inliers":count,
            "reprojection_error_px":round(median,2),"supported_sides":supported,
            "corners":[{"x":round(float(x),2),"y":round(float(y),2)} for x,y in result],
            "debug_matches":samples,"area_px":round(area)}
