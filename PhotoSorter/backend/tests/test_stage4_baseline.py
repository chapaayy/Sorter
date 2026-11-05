"""Actual/golden fixture comparator must catch SAM, grouping, rank, scores and ZIP."""
from __future__ import annotations
import importlib.util
import json
import zipfile
from pathlib import Path
MODULE=Path(__file__).resolve().parents[2]/"tools"/"stage4"/"compare_baseline.py"
spec=importlib.util.spec_from_file_location("compare_baseline",MODULE)
compare=importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)

def fixtures(tmp_path):
    manifest=[
      {"query":"/old/fo/a.jpg","assigned_sam":"SAM-0001","group_id":"G0001",
       "group_size":2,"group_status":"valid","score":.91234,
       "top":[{"label":"SAM-0001","score":.91234,"reference":"/x/references/SAM-0001/abc.jpg"}]},
      {"query":"/old/fo/b.jpg","assigned_sam":"_Неопределено","group_id":"G0001",
       "group_size":2,"group_status":"valid","score":None,"top":[]}
    ]
    p=tmp_path/"golden.json"
    p.write_text(json.dumps(manifest),encoding="utf8")
    updated=json.loads(json.dumps(manifest))
    for row in updated:row["query"]=row["query"].replace("/old/","/new/")
    candidate=tmp_path/"candidate.json"
    candidate.write_text(json.dumps(updated),encoding="utf8")
    return p,candidate,updated

def test_identical_assignments_ranks_scores_and_uncertainty(tmp_path):
    old,new,_=fixtures(tmp_path)
    report=compare.compare_manifests(old,new)
    assert report["same"] and report["uncertain_baseline"]==1
    assert report["groups_baseline"]==1

def test_sam_score_and_rank_regressions_fail(tmp_path):
    old,new,rows=fixtures(tmp_path)
    rows[0]["top"][0]["score"]=.81
    rows[0]["assigned_sam"]="SAM-0002"
    new.write_text(json.dumps(rows),encoding="utf8")
    result=compare.compare_manifests(old,new)
    assert not result["same"]
    assert {"assigned_sam","top"}<=set(d["field"] for d in result["differences"])

def test_zip_comparison_catches_crc_and_missing_paths(tmp_path):
    before=tmp_path/"golden.zip"
    after=tmp_path/"actual.zip"
    for f,data in ((before,b"unchanged"),(after,b"unchanged")):
        with zipfile.ZipFile(f,"w") as z:z.writestr("SAM-0001/fo.jpg",data)
    assert compare.compare_zip(before,after)["same"]
    with zipfile.ZipFile(after,"w") as z:z.writestr("SAM-0001/fo.jpg",b"changed")
    assert not compare.compare_zip(before,after)["same"]

def test_duplicate_basename_needs_path_root(tmp_path):
    old,new,rows=fixtures(tmp_path)
    rows.append({**rows[0],"query":"/new/other/a.jpg"})
    new.write_text(json.dumps(rows),encoding="utf8")
    assert not compare.compare_manifests(old,new)["same"]
