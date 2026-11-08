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
            "top":candidates,
            "margin":gap,"thresholds":{"min_similarity":minimum,"min_margin":margin}}


def rank_group(members: list[dict], layouts: list[tuple[dict, np.ndarray]], *,
               minimum: float = MIN_SIMILARITY, margin: float = MIN_MARGIN) -> dict:
    """Rank ALL layouts by the mean cosine across ALL group members.

    Individual scores are retained with each candidate for inspection and
    never replaced by a representative or a visually attractive outlier.
    """
    if not members:
        raise ValueError("Cannot match an empty advertisement group")
    vectors = np.stack([np.asarray(item["feature"], dtype=np.float32)
                        for item in members])
    if (vectors.ndim != 2 or vectors.shape[1] != 384 or
            not np.isfinite(vectors).all() or
            np.any(np.linalg.norm(vectors, axis=1) <= 1e-8)):
        raise ValueError("Invalid screen embeddings")
    vectors /= np.linalg.norm(vectors, axis=1)[:, None]
    candidates = []
    for row, feature in layouts:
        reference = np.asarray(feature, dtype=np.float32).reshape(-1)
        if reference.shape != (384,) or not np.isfinite(reference).all():
            continue
        norm = float(np.linalg.norm(reference))
        if norm <= 1e-8:
            continue
        cosines = np.clip(vectors @ (reference / norm), -1, 1)
        candidates.append({
            "id": str(row["id"]),
            "name": row["name"],
            "version": row["version"],
            "checksum": row["checksum"],
            "score": round(float(cosines.mean()), 6),
            "minimum_member_score": round(float(cosines.min()), 6),
            "maximum_member_score": round(float(cosines.max()), 6),
            "member_scores": [
                {"index": int(member["index"]), "screen_id": str(member["screen_id"]),
                 "score": round(float(score), 6)}
                for member, score in zip(members, cosines)
            ]
        })
    candidates.sort(key=lambda row: (-row["score"], row["id"]))
    if not candidates:
        return {"status": "no_layouts", "reason": "Нет подготовленных рекламных макетов",
                "candidate_id": None, "margin": None, "rankings": [],
                "matching_threshold": minimum}
    best = candidates[0]
    gap = round(best["score"] - candidates[1]["score"], 6) if len(candidates) > 1 else None
    if best["score"] < minimum:
        status, reason = "no_match", "Среднее сходство группы ниже заданного порога"
    elif gap is not None and gap < margin:
        status, reason = "uncertain", "Несколько макетов имеют близкое сходство"
    else:
        status, reason = "matched", "Группа визуально совместима с макетом"
    return {
        "status": status, "reason": reason,
        "candidate_id": best["id"] if status != "no_match" else None,
        "best_score": best["score"],
        "margin": gap,
        "matching_threshold": minimum,
        "margin_threshold": margin,
        "method": "mean_member_cosine",
        "rankings": candidates
    }
