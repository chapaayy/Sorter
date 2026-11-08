"""Stage-2 XFeat homography, mask, version and lossless crop regression."""
from __future__ import annotations
import uuid
import cv2
import numpy as np
import pytest
from PIL import Image
from app.screen_detection.features import border_features,match
from app.screen_detection.geometry import solve
from app.screen_detection.cache import key
from server.services import screen_search

QUAD=[{"x":80,"y":80},{"x":440,"y":80},{"x":440,"y":280},{"x":80,"y":280}]
DST=np.array([[610,250],[1090,210],[1140,590],[650,620]],dtype=np.float32)

def correspondences():
    rng=np.random.default_rng(43)
    corners=np.array([[p["x"],p["y"]] for p in QUAD],dtype=np.float32)
    ref=[];sides=[]
    for side in range(4):
        start,end=corners[side],corners[(side+1)%4]
        for t in np.linspace(.07,.93,12):
            ref.append(start*(1-t)+end*t);sides.append(side)
    ref=np.array(ref,dtype=np.float32)
    H=cv2.getPerspectiveTransform(corners,DST)
    target=cv2.perspectiveTransform(ref.reshape(-1,1,2),H).reshape(-1,2)
    target+=rng.normal(0,.45,target.shape).astype(np.float32)
    return ref,target,np.array(sides,dtype=np.uint8)

def test_planar_geometry_projects_all_four_corners():
    ref,target,sides=correspondences()
    rng=np.random.default_rng(5)
    out_ref=rng.uniform([0,0],[500,350],size=(14,2)).astype("float32")
    out_fo=rng.uniform([0,0],[1600,900],size=(14,2)).astype("float32")
    result=solve(np.vstack((ref,out_ref)),np.vstack((target,out_fo)),
                 np.r_[sides,np.zeros(14,dtype="uint8")],QUAD,(1600,900))
    assert result["status"]=="found",result
    assert result["inliers"]>=40
    assert len(result["supported_sides"])==4
    assert np.max(np.abs(np.array([[p["x"],p["y"]] for p in result["corners"]])-DST))<8
    assert result["reprojection_error_px"]<3

def test_arbitrary_four_matches_rejected():
    ref,target,sides=correspondences()
    assert solve(ref[:4],target[:4],sides[:4],QUAD,(1600,900))["status"]=="not_found"

def test_one_sided_matches_rejected():
    ref,target,sides=correspondences()
    assert solve(ref[:12],target[:12],sides[:12],QUAD,(1600,900))["status"]=="not_found"

def test_outside_image_rejected():
    ref,target,sides=correspondences()
    assert solve(ref,target+np.array([2000,1000],dtype=np.float32),sides,QUAD,(1600,900))["status"]=="not_found"

def test_border_mask_excludes_advertisement():
    corners=[{"x":20,"y":10},{"x":180,"y":10},{"x":180,"y":110},{"x":20,"y":110}]
    xy=np.array([[50,10],[180,55],[100,110],[20,50],[100,60],[0,0]],dtype=np.float32)
    result=border_features({"xy":xy,"descriptors":np.eye(6,64,dtype=np.float32)},corners,6,200,120)
    assert len(result["xy"])==4
    assert set(map(int,result["sides"]))=={0,1,2,3}

def test_mutual_descriptor_match():
    ref={"xy":np.array([[0,0],[1,1]],dtype=np.float32),
         "descriptors":np.eye(2,64,dtype=np.float32),
         "sides":np.array([0,1],dtype=np.uint8)}
    a,b,s=match(ref,{"xy":ref["xy"],"descriptors":ref["descriptors"]})
    assert len(a)==len(b)==len(s)==2

def test_cache_versions_and_band_change_key():
    base={"id":str(uuid.uuid4()),"source_sha256":"a"*64,"version":1,
          "corners":QUAD,"band_width_px":9}
    first=key(base)
    assert first!=key({**base,"version":2})
    assert first!=key({**base,"band_width_px":12})

def test_unwarped_crop_preserves_source(tmp_path,monkeypatch):
    monkeypatch.setattr(screen_search,"DATA_DIR",tmp_path)
    run="20261108T120000-123abc123abc"
    rgb=np.zeros((300,400,3),dtype=np.uint8)
    rgb[60:200,70:260]=[10,130,210]
    before=rgb.copy()
    item={"index":0,"status":"found","screens":[{"screen_id":str(uuid.uuid4()),
        "status":"found","corners":[{"x":70,"y":60},{"x":260,"y":60},
                                   {"x":260,"y":200},{"x":70,"y":200}]}]}
    screen_search._save(run,0,item,rgb)
    saved=screen_search.saved(run,0)
    file=screen_search.crop(run,0,uuid.UUID(item["screens"][0]["screen_id"]))
    with Image.open(file) as photo:
        assert photo.size==(190,140)
        assert list(np.asarray(photo)[0,0])==[10,130,210]
    assert np.array_equal(rgb,before)
    assert saved["screens"][0]["crop_box"]["width"]==190

def test_invalid_run_identifier_rejected():
    with pytest.raises(ValueError):
        screen_search.saved("../../etc",0)
