"""Conservative relative DINOv2 + OCR layout decision, without new neural models.

The screen group and layout library are already immutable. OCR contains plain
word matches, never inferred price/date meaning. Relative ranking alone cannot
assert a match when all similarities are noise or text is unreadable.
"""
from __future__ import annotations

from . import ocr

VERSION = "relative-dino-ocr-v1"
MIN_VISUAL_WITH_OCR = .18
MIN_VISUAL_RELATIVE_ONLY = .36
MIN_VISUAL_GAP_RELATIVE_ONLY = .18
MIN_OCR_GAP = .18
MIN_STRONG_OCR = .65


def _layout_text(row: dict) -> str:
    value = row.get("ocr_text")
    if value is None:
        value = (row.get("ocr_corrected_text") if
                 row.get("ocr_corrected_text") is not None else
                 row.get("expected_text") or row.get("normalized_text") or "")
    return value or ""


def decide(ranked: dict, members: list[dict], layouts: list[tuple],
           observations: dict, minimum: float) -> dict:
    """Evaluate every prepared layout against the SAME photo OCR evidence.

    Group OCR uses the strongest reliably read frame per layout, not an
    average that penalizes unreadable screens. Independent disagreement
    between readable members is an explicit abstention.
    """
    candidates = ranked.get("rankings", [])
    if not candidates:
        return {**ranked, "decision_version": VERSION}
    rows = {str(row["id"]): row for row, *_ in layouts}
    best_visual = candidates[0]
    visual_margin = ranked.get("margin")
    visual_id = best_visual["id"]
    visual_score = best_visual["score"]
    evidence_per_member = {}
    evidence_per_layout = {}
    ocr_candidates = []
    max_visual = max(candidate["score"] for candidate in candidates)
    min_visual = min(candidate["score"] for candidate in candidates)
    visual_span = max_visual - min_visual
    for candidate in candidates:
        identifier = candidate["id"]
        text = _layout_text(rows[identifier])
        strongest = None
        for member in members:
            key = (int(member["index"]), str(member["screen_id"]))
            entry = observations.get(key) or {}
            lines = entry.get("lines", [])
            if entry.get("error") or not lines:
                continue
            result = ocr.confirm(text, lines)
            if not result.get("total_terms"):
                continue
            hits = result.get("matched_terms", 0)
            ratio = result.get("text_similarity", 0.)
            confidence = result.get("comparison_confidence", 0.)
            # One unique word can help, but must not overpower an otherwise
            # weak visual match. There is no mandatory fixed count of words.
            support = ratio * confidence * (1. if hits >= 2 else .55)
            assessment = {
                "index": key[0], "screen_id": key[1],
                "hits": hits, "total": result["total_terms"],
                "ratio": ratio, "confidence": confidence,
                "support": round(support, 4),
            }
            evidence_per_member.setdefault(key, []).append(
                (identifier, assessment))
            if strongest is None or (support, hits, -key[0]) > (
                    strongest["support"], strongest["hits"],
                    -strongest["index"]):
                strongest = assessment
        if strongest:
            evidence_per_layout[identifier] = strongest
        strength = strongest["support"] if strongest else 0.
        candidate.update(
            ocr_matched_terms=strongest["hits"] if strongest else 0,
            ocr_total_terms=strongest["total"] if strongest else 0,
            ocr_similarity=strongest["ratio"] if strongest else 0.,
            ocr_support=strength,
            relative_dino=(round((candidate["score"] - min_visual) / visual_span, 4)
                           if visual_span else 0.),
            combined_score=round(.5 * max(0., candidate["score"]) + .5 * strength, 4)
        )
        ocr_candidates.append(candidate)
    ocr_candidates.sort(key=lambda item: (-item["ocr_support"], item["id"]))
    best_ocr = ocr_candidates[0]
    ocr_runner = ocr_candidates[1] if len(ocr_candidates) > 1 else None
    ocr_gap = (best_ocr["ocr_support"] - ocr_runner["ocr_support"]
               if ocr_runner else None)
    ocr_strong = (best_ocr["ocr_support"] >= MIN_STRONG_OCR
                  and (ocr_gap is not None and ocr_gap >= MIN_OCR_GAP))
    per_photo_winners = set()
    for scores in evidence_per_member.values():
        scores.sort(key=lambda item: -item[1]["support"])
        leader = scores[0]
        runner = scores[1][1]["support"] if len(scores) > 1 else 0.
        if (leader[1]["support"] >= MIN_STRONG_OCR
                and leader[1]["support"] - runner >= MIN_OCR_GAP):
            per_photo_winners.add(leader[0])
    conflict = len(per_photo_winners) > 1

    # Without readable/differentiating OCR, conservative visual fallback.
    visual_only = (
        visual_score >= minimum and
        (visual_margin is None or visual_margin >= .035)
    ) or (
        len(candidates) > 1 and visual_score >= MIN_VISUAL_RELATIVE_ONLY
        and visual_margin is not None
        and visual_margin >= MIN_VISUAL_GAP_RELATIVE_ONLY
    )
    chosen = None
    method = "insufficient_evidence"
    status = "no_match"
    reason = "Недостаточно различимых визуальных и текстовых признаков"
    if conflict:
        status = "uncertain"
        method = "conflicting_group_ocr"
        reason = "Разные ФО одной визуальной группы уверенно указывают на разные макеты"
    elif ocr_strong and best_ocr["id"] == visual_id and visual_score >= MIN_VISUAL_WITH_OCR:
        if (len(candidates) > 1 and
                (visual_margin is None or visual_margin >= .04 or ocr_gap >= .35)):
            chosen, status = visual_id, "matched"
            method = "visual_ocr_agreement"
            reason = "DINOv2 и OCR независимо выделили один макет относительно остальных"
        else:
            status, method = "uncertain", "weak_visual_separation"
            reason = "OCR совпал, но визуально макеты слишком близки"
    elif ocr_strong and best_ocr["id"] != visual_id:
        # A robust OCR lead can break a *close* DINO tie, but cannot
        # silently override an unrelated, strongly different visual winner.
        if (visual_score >= MIN_VISUAL_WITH_OCR and
                visual_score - best_ocr["score"] <= .08 and
                best_ocr["score"] >= MIN_VISUAL_WITH_OCR and
                ocr_gap >= .30):
            chosen, status = best_ocr["id"], "matched"
            method = "ocr_resolved_visual_tie"
            reason = "OCR разрешил близкие результаты DINOv2"
        else:
            status, method = "uncertain", "visual_ocr_disagreement"
            reason = "DINOv2 и уверенный OCR указывают на разные макеты"
    elif visual_only:
        # OCR is missing or ambiguous; this is not a manual-review gate.
        chosen, status = visual_id, "matched"
        method = "relative_visual_only" if visual_score < minimum else "visual_only"
        reason = "Выбран визуально отличающийся макет; OCR не дал однозначного ответа"
    elif (best_ocr["ocr_support"] > 0 or
          (visual_margin is not None and visual_margin < .035)):
        status = "uncertain"
    return {
        **ranked, "status": status, "reason": reason, "candidate_id": chosen,
        "method": method, "decision_version": VERSION,
        "ocr_leader_id": best_ocr["id"] if best_ocr["ocr_support"] > 0 else None,
        "ocr_margin": round(ocr_gap, 4) if ocr_gap is not None else None,
        "visual_leader_id": visual_id,
        "ocr_conflicting_members": conflict,
        "evidence_member_count": len(evidence_per_member),
        "minimum_visual_with_ocr": MIN_VISUAL_WITH_OCR,
    }
