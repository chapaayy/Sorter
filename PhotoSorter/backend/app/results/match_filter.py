"""Optional post-MegaLoc quality gate for the selected construction.

This runs only after FO grouping and SAM resolution. It does not change model
vectors, group membership, group voting or candidate ranking. One weak FO may
become _Неопределено while the rest of its group remains assigned.
"""
from __future__ import annotations

import math


def apply_min_match_score(rows: list[dict], threshold: float) -> list[dict]:
    """Return classified rows, retaining diagnostic candidates for rejected FO.

    The decision uses each photo's own similarity to its group's chosen SAM.
    Videos already collapsed to a single row use the video vote's mean score.
    A setting of 0 disables filtering entirely (also for negative scores).
    """
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Минимальное сходство должно быть от 0.000 до 1.000")
    if threshold == 0:
        return rows
    output = []
    for row in rows:
        winner = (row.get("top") or [None])[0]
        if winner is None:
            output.append(row)
            continue
        value = row.get("assigned_sam_score")
        if value is None:
            value = winner.get("score")  # Aggregated video, no per-frame assignment.
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = float("nan")
        updated = dict(row)
        updated["min_match_score"] = threshold
        updated["match_score"] = round(score, 6) if math.isfinite(score) else None
        if not math.isfinite(score) or score < threshold:
            updated["top"] = []
            updated["match_rejected"] = True
            updated["reason"] = (
                f"Сходство ФО с выбранной конструкцией "
                f"{score:.3f} ниже порога {threshold:.3f}"
                if math.isfinite(score)
                else "Не удалось получить сходство ФО с выбранной конструкцией"
            )
        output.append(updated)
    return output
