"""Deterministic best photo per physical screen / DINO layout / text variant.

Within a group, OCR measures how many words of the prepared layout are read
on each FO. Quality and OCR receive equal weight; absent OCR scores zero,
without creating a manual-review task or excluding otherwise valid frames.
"""
from __future__ import annotations
from collections import defaultdict


def _key(item: dict) -> tuple:
    return (item["assigned_sam"], item["screen_id"],
            item["candidate_id"], item.get("visual_group_id"),
            item.get("text_subgroup_id"))


def select(items: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for item in items:
        if (item.get("status") == "matched" and item.get("candidate_id")
                and item.get("quality", {}).get("status") == "measured"):
            groups[_key(item)].append(item)

    winners = []
    for members in groups.values():
        max_hits = max((max(0, int(item.get("ocr", {}).get("matched_terms") or 0))
                        for item in members), default=0)
        for item in members:
            evidence = item.get("ocr", {})
            hits = max(0, int(evidence.get("matched_terms") or 0))
            total = max(0, int(evidence.get("total_terms") or 0))
            fraction = (min(hits, total) / total) if total else 0.0
            coverage = hits / max_hits if max_hits else 0.0
            ocr_score = round(100 * fraction * coverage, 2)
            quality = max(0., min(100., float(item["quality"]["score"])))
            item["ocr_selection_score"] = ocr_score
            item["selection_score"] = round((ocr_score + quality) / 2., 2)
            item["selection_basis"] = "equal_weight_ocr_coverage_and_quality_v1"
        chosen = max(members, key=lambda row: (
            row["selection_score"],
            float(row["quality"]["score"]),
            int(row.get("ocr", {}).get("matched_terms") or 0),
            -int(row["index"])))
        winners.append(chosen)

    return sorted(winners, key=lambda row: (
        row["assigned_sam"], row.get("layout_name", ""), row["screen_id"],
        row.get("text_subgroup_id") or "", row["index"]))


def public(item: dict) -> dict:
    fields = ("index", "assigned_sam", "screen_id", "screen_name",
              "candidate_id", "layout_name", "layout_version",
              "layout_checksum", "quality", "ocr", "ocr_observation",
              "classification", "visual_group_id", "text_subgroup_id",
              "text_subgroup_status", "review_required",
              "selection_score", "ocr_selection_score", "selection_basis",
              "source_annotation_version", "dino_signature",
              "source_xfeat_signature")
    return {key: item[key] for key in fields if key in item}
