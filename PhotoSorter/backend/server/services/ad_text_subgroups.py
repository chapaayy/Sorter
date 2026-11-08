"""OCR-based final text subgroups, isolated from DINOv2 visual grouping.

Only screen OCR evidence determines text separation. No candidate reassignment.
A low-confidence/unreadable photo is never silently assigned to a text variant.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from collections import Counter

from fastapi import HTTPException

from app.ad_recognition import ocr
from app.results.exporter import atomic_json
from . import ad_recognition, ad_visual_groups

VERSION = "ad-text-variants-v1"
MIN_READABLE_CONFIDENCE = .70
MIN_TEXT_SIMILARITY = .72


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-zа-яё0-9]+", (value or "").casefold())


def _compatible(first: dict, second: dict) -> bool:
    """Do not join different DINO candidates or contradictory OCR variants."""
    if first.get("candidate_id") != second.get("candidate_id"):
        return False
    a, b = first["ocr_observation"], second["ocr_observation"]
    if a.get("status") != "readable" or b.get("status") != "readable":
        return False
    if a.get("confidence", 0) < MIN_READABLE_CONFIDENCE or b.get("confidence", 0) < MIN_READABLE_CONFIDENCE:
        return False
    left, right = a.get("significant", {}), b.get("significant", {})
    for kind in ("dates", "prices", "percentages"):
        x, y = set(left.get(kind, ())), set(right.get(kind, ()))
        if x and y and x.isdisjoint(y):
            return False
    # Bare significant numbers are enough to separate the same ad slogan
    # carrying a different promotional offer/date. Never silently fuse them.
    x, y = set(left.get("numbers", ())), set(right.get("numbers", ()))
    if x and y and x.isdisjoint(y):
        return False
    at, bt = _tokens(a.get("normalized_text", "")), _tokens(b.get("normalized_text", ""))
    if not at or not bt:
        return False
    if at == bt:
        return True
    overlap = len(set(at) & set(bt)) / max(1, min(len(set(at)), len(set(bt))))
    ratio = SequenceMatcher(None, " ".join(at), " ".join(bt)).ratio()
    return ratio >= MIN_TEXT_SIMILARITY or (overlap >= .8 and ratio >= .50)


def _classification(item: dict) -> str:
    """OCR confirms only DINO-matched layouts; it cannot identify by itself."""
    visual = item.get("status")
    if visual != "matched" or not item.get("candidate_id"):
        return "unidentified"
    evidence = item.get("ocr_observation", {})
    if (item.get("review_required", False) or
            evidence.get("status") != "readable" or
            evidence.get("confidence", 0) < MIN_READABLE_CONFIDENCE):
        return "probable"
    if item.get("ocr", {}).get("status") == "confirmed":
        return "confirmed"
    return "probable"


def form(job, run_id: str, groups: list[dict], analyses: list[dict],
         *, data_root=None) -> dict:
    """Stable text variants per VISUAL group; no global text-only grouping."""
    index = {(int(item["index"]), str(item["screen_id"])): item for item in analyses}
    subgroups = []
    next_id = 1
    for group in groups:
        if job.stopped():
            raise InterruptedError("Группировка рекламы по тексту остановлена")
        buckets: list[list[dict]] = []
        for member in group["members"]:
            key = (int(member["index"]), str(member["screen_id"]))
            item = index.get(key)
            if item is None:
                item = {
                    "index": key[0], "screen_id": key[1],
                    "assigned_sam": group["assigned_sam"],
                    "candidate_id": None, "status": "error",
                    "review_required": True,
                    "ocr": {"status": "unavailable", "reason": "OCR не выполнено"},
                    "ocr_observation": {
                        "status": "unreadable", "raw_lines": [],
                        "normalized_text": "", "confidence": 0.0,
                        "significant": {"dates": [], "prices": [],
                                        "percentages": [], "numbers": []},
                        "regions": []},
                }
                analyses.append(item)
                index[key] = item
            item["classification"] = _classification(item)
            item["visual_group_id"] = group["id"]
            obs = item.get("ocr_observation", {})
            reliable = (obs.get("status") == "readable" and
                        obs.get("confidence", 0) >= MIN_READABLE_CONFIDENCE and
                        bool(_tokens(obs.get("normalized_text", ""))))
            placed = False
            if reliable:
                for bucket in buckets:
                    if all(_compatible(item, other) for other in bucket):
                        bucket.append(item)
                        placed = True
                        break
            if not placed:
                buckets.append([item])
        for bucket in buckets:
            subgroup_id = f"T{next_id:04d}"
            next_id += 1
            states = Counter(item["classification"] for item in bucket)
            if states["unidentified"]:
                state = "unidentified" if states["unidentified"] == len(bucket) else "probable"
            elif states["probable"]:
                state = "probable"
            else:
                state = "confirmed"
            members = []
            for item in bucket:
                item["text_subgroup_id"] = subgroup_id
                item["text_subgroup_status"] = state
                if state != "confirmed":
                    item["review_required"] = True
                # Rewrites the same atomic per-screen result after deterministic
                # subgroup selection, never touches MegaLoc/XFeat originals.
                ad_recognition._write(run_id, item["index"], item["screen_id"], item)
                obs = item.get("ocr_observation", {})
                members.append({
                    "index": item["index"], "screen_id": item["screen_id"],
                    "visual_group_id": group["id"],
                    "classification": item["classification"],
                    "review_required": bool(item["review_required"]),
                    "normalized_text": obs.get("normalized_text", ""),
                    "confidence": obs.get("confidence", 0),
                    "significant": obs.get("significant", {}),
                    "ocr_status": item.get("ocr", {}).get("status"),
                })
            reference = next(
                (member["ocr_observation"] for member in bucket
                 if member.get("ocr_observation", {}).get("status") == "readable"),
                None)
            subgroups.append({
                "id": subgroup_id,
                "visual_group_id": group["id"],
                "assigned_sam": group["assigned_sam"],
                "screen_id": group["screen_id"],
                "candidate_id": bucket[0].get("candidate_id"),
                "status": state,
                "member_count": len(bucket),
                "text": reference.get("normalized_text", "") if reference else "",
                "significant": reference.get("significant", {}) if reference else {},
                "members": members,
                "reason": ("Читаемые текстовые варианты разделены по содержанию, датам и ценам"
                           if reference else "Текст нельзя надёжно прочитать; вариант не присвоен"),
            })
    counts = Counter(group["status"] for group in subgroups)
    document = {
        "status": "completed", "version": VERSION, "run_id": run_id,
        "visual_group_count": len(groups), "subgroup_count": len(subgroups),
        "confirmed": counts["confirmed"], "probable": counts["probable"],
        "unidentified": counts["unidentified"],
        "subgroups": subgroups,
    }
    atomic_json(ad_visual_groups._root(run_id, data_root) / "text_subgroups.json", document)
    job.progress("ad_pipeline", "ad_text", len(analyses) or 1, len(analyses) or 1,
                 f"OCR · текстовых вариантов: {len(subgroups)}")
    return document


def saved(run_id: str, limit: int = 50, offset: int = 0,
          group_id: str | None = None, layout_id: str | None = None) -> dict:
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(422, "Некорректная страница результатов")
    path = ad_visual_groups._root(run_id) / "text_subgroups.json"
    document = ad_visual_groups._load(path)
    if document is None:
        return {"status": "not_processed", "subgroups": [], "total": 0}
    entries = document["subgroups"]
    if group_id is not None:
        if not re.fullmatch(r"R\d{4,8}", group_id):
            raise HTTPException(422, "Некорректная визуальная группа")
        entries = [group for group in entries if group["visual_group_id"] == group_id]
    if layout_id is not None:
        # The reserved identifier represents visually unassigned campaigns.
        if layout_id != "unidentified":
            from uuid import UUID
            try:
                layout_id = str(UUID(layout_id))
            except (ValueError, TypeError, AttributeError) as exc:
                raise HTTPException(422, "Некорректный макет") from exc
        entries = [row for row in entries
                   if str(row.get("candidate_id") or "unidentified") == layout_id]
    page = [{key: value for key, value in row.items() if key != "members"}
            for row in entries[offset:offset + limit]]
    return {key: value for key, value in document.items() if key != "subgroups"} | {
        "total": len(entries), "limit": limit, "offset": offset, "subgroups": page
    }


def detail(run_id: str, subgroup_id: str) -> dict:
    if not re.fullmatch(r"T\d{4,8}", subgroup_id):
        raise HTTPException(422, "Некорректный ID текстовой группы")
    document = ad_visual_groups._load(
        ad_visual_groups._root(run_id) / "text_subgroups.json")
    if document is None:
        raise HTTPException(404, "Результаты OCR ещё не опубликованы")
    group = next((row for row in document["subgroups"] if row["id"] == subgroup_id), None)
    if group is None:
        raise HTTPException(404, "Текстовая группа не найдена")
    return group
