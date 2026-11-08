"""DINO-only layout choice; OCR is never allowed to change a candidate ID."""
from __future__ import annotations
import numpy as np

MIN_SIMILARITY=.81
MIN_MARGIN=.035

def rank(query:np.ndarray,layouts:list[tuple[dict,np.ndarray]],*,minimum=MIN_SIMILARITY,
         margin=MIN_MARGIN)->dict:
    if query.shape!=(384,) or not np.isfinite(query).all():
        raise ValueError("Invalid query embedding")
    if not layouts:
        return {"status":"no_layouts","reason":"Нет активных макетов","top":[],"candidate_id":None}
    candidates=[]
    for row,feature in layouts:
        if feature.shape!=(384,) or not np.isfinite(feature).all():
            continue
        score=float(np.dot(query,feature))
        candidates.append({"id":str(row["id"]),"name":row["name"],
                           "score":round(score,4),"version":row["version"],
                           "checksum":row["checksum"]})
    candidates.sort(key=lambda r:(-r["score"],r["id"]))
    if not candidates:
        return {"status":"no_layouts","reason":"Нет корректных признаков макетов",
                "top":[],"candidate_id":None}
    best=candidates[0]
    gap=round(best["score"]-candidates[1]["score"],4) if len(candidates)>1 else None
    if best["score"]<minimum:
        state,reason="no_match","DINOv2: сходство ниже экспериментального порога"
    elif gap is not None and gap<margin:
        state,reason="uncertain","DINOv2: слишком близкие оценки нескольких макетов"
    else:
        state,reason="matched","DINOv2: выбран наиболее близкий макет"
    return {"status":state,"reason":reason,
            "candidate_id":best["id"] if state!="no_match" else None,
            "top":candidates[:5],
            "margin":gap,"thresholds":{"min_similarity":minimum,"min_margin":margin}}
