"""Compare MegaLoc manifests/ZIP against a verified *provided* golden baseline.

Never infer or manufacture the user's 189/1315-photo baseline. This tool does not
load model weights or change photo assignments. Exit 0 only on an exact match.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
import zipfile
from collections import Counter
from pathlib import Path

COMPARE_FIELDS=("assigned_sam","group_id","group_size","group_status",
                "verdict","reason","checked_count","individual_sam")
SCORE_FIELDS=("score",)
MAX_DIFFERENCES=50

def label_path(value,root=None):
    if value is None:return None
    path=Path(str(value).replace("\\","/"))
    if root:
        try:return path.relative_to(Path(root)).as_posix()
        except ValueError:raise ValueError("Manifest query is outside supplied photo root")
    return path.name

def normalized_candidates(row):
    result=[]
    for entry in row or []:
        if not isinstance(entry,dict):raise ValueError("Invalid candidate")
        result.append((entry.get("label"),entry.get("score"),
                       label_path(entry.get("reference"))))
    return result

def compare_manifests(baseline,candidate,*,golden_root=None,actual_root=None):
    old=json.loads(Path(baseline).read_text(encoding="utf8"))
    new=json.loads(Path(candidate).read_text(encoding="utf8"))
    if not isinstance(old,list) or not isinstance(new,list):
        raise ValueError("Both manifests must be lists")
    differences=[]
    if len(old)!=len(new):
        differences.append({"field":"row_count","expected":len(old),"actual":len(new)})
    old_paths=[label_path(r.get("query"),golden_root) for r in old]
    new_paths=[label_path(r.get("query"),actual_root) for r in new]
    if len(old_paths)!=len(set(old_paths)) and not golden_root:
        raise ValueError("Ambiguous query basenames: specify --golden-root and --actual-root")
    for i,(a,b) in enumerate(zip(old,new)):
        if len(differences)>=MAX_DIFFERENCES:break
        for field,expect,actual in [
            ("query",old_paths[i],new_paths[i]),
            *[(name,a.get(name),b.get(name)) for name in COMPARE_FIELDS],
            ("reference",label_path(a.get("reference")),label_path(b.get("reference"))),
            ("top",normalized_candidates(a.get("top")),normalized_candidates(b.get("top"))),
            ("individual_top",normalized_candidates(a.get("individual_top")),normalized_candidates(b.get("individual_top"))),
        ]:
            if expect!=actual:
                differences.append({"row":i,"field":field,"expected":expect,"actual":actual})
                if len(differences)>=MAX_DIFFERENCES:break
        for field in SCORE_FIELDS:
            expect,actual=a.get(field),b.get(field)
            if expect is None and actual is None:continue
            try:equal=expect is not None and actual is not None and math.isclose(float(expect),float(actual),rel_tol=0,abs_tol=1e-7)
            except (TypeError,ValueError):equal=False
            if not equal and len(differences)<MAX_DIFFERENCES:
                differences.append({"row":i,"field":field,"expected":expect,"actual":actual})
    old_assign=Counter(x.get("assigned_sam") for x in old)
    new_assign=Counter(x.get("assigned_sam") for x in new)
    return {"same":not differences,
            "rows_baseline":len(old),"rows_candidate":len(new),
            "groups_baseline":len(set(x.get("group_id") for x in old)),
            "groups_candidate":len(set(x.get("group_id") for x in new)),
            "sam_counts_baseline":dict(old_assign),
            "sam_counts_candidate":dict(new_assign),
            "uncertain_baseline":old_assign.get("_Неопределено",0),
            "uncertain_candidate":new_assign.get("_Неопределено",0),
            "differences":differences}

def zip_index(path):
    with zipfile.ZipFile(path,"r") as z:
        members=z.infolist()
        names=[m.filename for m in members]
        if len(names)!=len(set(names)):raise ValueError("ZIP contains duplicate member names")
        if any(n.startswith("/") or ".." in Path(n).parts or "\\" in n for n in names):
            raise ValueError("Unsafe ZIP path")
        return sorted((m.filename,m.file_size,m.CRC) for m in members if not m.is_dir())

def compare_zip(baseline,candidate):
    a=zip_index(baseline)
    b=zip_index(candidate)
    if a==b:return {"same":True,"members":len(a),"differences":[]}
    removed=sorted(set(a)-set(b))[:MAX_DIFFERENCES]
    added=sorted(set(b)-set(a))[:MAX_DIFFERENCES]
    return {"same":False,"members_baseline":len(a),"members_candidate":len(b),
            "differences":[{"missing":x} for x in removed]+[{"unexpected":x} for x in added]}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-manifest",required=True)
    p.add_argument("--candidate-manifest",required=True)
    p.add_argument("--golden-root")
    p.add_argument("--actual-root")
    p.add_argument("--baseline-zip")
    p.add_argument("--candidate-zip")
    args=p.parse_args(argv)
    if bool(args.baseline_zip)!=bool(args.candidate_zip):
        p.error("Supply both baseline and candidate ZIP or neither")
    result=compare_manifests(args.baseline_manifest,args.candidate_manifest,
                             golden_root=args.golden_root,actual_root=args.actual_root)
    if args.baseline_zip:
        result["zip"]=compare_zip(args.baseline_zip,args.candidate_zip)
        result["same"]=result["same"] and result["zip"]["same"]
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["same"] else 1

if __name__=="__main__":sys.exit(main())
