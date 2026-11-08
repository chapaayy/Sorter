"""One deterministic best FO per construction/screen/advertisement.

OCR is not a classifier and must never change which layout ID DINO chose.
Review-required results live in a distinct, conspicuous ZIP section.
"""
from __future__ import annotations

def select(items:list[dict])->list[dict]:
    winners={}
    for item in items:
        if item.get("status")!="matched" or not item.get("candidate_id"):
            continue
        if item.get("quality",{}).get("status")!="measured":
            continue
        key=(item["assigned_sam"],item["screen_id"],item["candidate_id"],
             item.get("text_subgroup_id"))
        old=winners.get(key)
        # Deterministic tie: earlier photo beats later; OCR-confirmed
        # should take priority if another candidate is unconfirmed.
        rank=lambda c:(c.get("classification")=="confirmed",
                       not c.get("review_required",True),
                       float(c["quality"]["score"]),-int(c["index"]))
        if old is None or rank(item)>rank(old):
            winners[key]=item
    return sorted(winners.values(),key=lambda x:
                  (x["assigned_sam"],x.get("layout_name",""),x["screen_id"],
                   x.get("text_subgroup_id") or "",x["index"]))

def public(item:dict)->dict:
    fields=("index","assigned_sam","screen_id","screen_name","candidate_id",
            "layout_name","layout_version","layout_checksum","quality",
            "ocr","ocr_observation","classification","visual_group_id",
            "text_subgroup_id","text_subgroup_status","review_required",
            "source_annotation_version","dino_signature","source_xfeat_signature")
    return {key:item[key] for key in fields if key in item}
