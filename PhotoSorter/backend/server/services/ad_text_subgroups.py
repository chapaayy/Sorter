"""Text variants within a DINO visual group, using plain OCR word overlap.

No classification of dates/prices; empty OCR joins its visual group whenever
only one readable text variant exists. Keep pinned T identifiers and API shape.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from fastapi import HTTPException
from app.ad_recognition import ocr, text_verification
from app.results.exporter import atomic_json
from . import ad_recognition, ad_visual_groups

VERSION = "ad-text-variants-words-v2"
MIN_READABLE_CONFIDENCE = .70
MIN_TEXT_OVERLAP = .70


def _tokens(value: str) -> list[str]:
    return list(dict.fromkeys(text_verification.words(value)))


def _readable(item: dict) -> bool:
    obs = item.get("ocr_observation", {})
    return (obs.get("status") == "readable"
            and obs.get("confidence", 0) >= MIN_READABLE_CONFIDENCE
            and bool(_tokens(obs.get("normalized_text", ""))))


def _compatible(first: dict, second: dict) -> bool:
    """Compare text variants as word sets; numbers are exact tokens."""
    if first.get("candidate_id") != second.get("candidate_id"):
        return False
    if not _readable(first) or not _readable(second):
        return False
    a = set(_tokens(first["ocr_observation"]["normalized_text"]))
    b = set(_tokens(second["ocr_observation"]["normalized_text"]))
    numbers_a = {word for word in a if any(ch.isdigit() for ch in word)}
    numbers_b = {word for word in b if any(ch.isdigit() for ch in word)}
    if numbers_a and numbers_b and numbers_a.isdisjoint(numbers_b):
        return False
    return len(a & b) / max(1, min(len(a), len(b))) >= MIN_TEXT_OVERLAP


def _classification(item: dict) -> str:
    """DINO selects layouts; unreadable OCR is not an error or review item."""
    if item.get("status") != "matched" or not item.get("candidate_id"):
        return "unidentified"
    return "confirmed" if item.get("ocr", {}).get("status") == "confirmed" else "probable"


def form(job, run_id: str, groups: list[dict], analyses: list[dict],
         *, data_root=None) -> dict:
    """Select one variant for readable matching ads, not one per blank OCR."""
    index = {(int(item["index"]), str(item["screen_id"])): item for item in analyses}
    subgroups = []
    next_id = 1
    for group in groups:
        if job.stopped():
            raise InterruptedError("Группировка рекламы остановлена")
        by_candidate = defaultdict(list)
        for member in group["members"]:
            key = (int(member["index"]), str(member["screen_id"]))
            item = index.get(key)
            if item is None:
                item = {
                    "index": key[0], "screen_id": key[1],
                    "assigned_sam": group["assigned_sam"],
                    "candidate_id": None, "status": "error",
                    "review_required": False,
                    "ocr": {"status": "unavailable", "reason": "OCR не выполнено"},
                    "ocr_observation": ocr.describe([]),
                }
                analyses.append(item)
                index[key] = item
            item["classification"] = _classification(item)
            item["visual_group_id"] = group["id"]
            # OCR cannot send a visually identified photo to manual review.
            if item.get("status") == "matched":
                item["review_required"] = False
            by_candidate[str(item.get("candidate_id") or "")].append(item)
        for candidates in by_candidate.values():
            readable = sorted(
                (item for item in candidates if _readable(item)),
                key=lambda item: (-len(_tokens(item["ocr_observation"].get(
                    "normalized_text", ""))), int(item["index"])),
            )
            missing = [item for item in candidates if not _readable(item)]
            buckets = []
            for item in readable:
                compatible = [bucket for bucket in buckets
                              if all(_compatible(item, peer) for peer in bucket)]
                # A fragment fitting several variants is ambiguous, not proof
                # that the variants should merge into one campaign.
                if len(compatible) == 1:
                    compatible[0].append(item)
                else:
                    buckets.append([item])
            if len(buckets) == 1:
                buckets[0].extend(missing)
            elif missing:
                # Never create ten fake text variants for ten unreadable FOs.
                buckets.append(missing)
            for bucket in buckets:
                subgroup_id = f"T{next_id:04d}"
                next_id += 1
                states = Counter(item["classification"] for item in bucket)
                if states["unidentified"]:
                    state = ("unidentified" if states["unidentified"] == len(bucket)
                             else "probable")
                elif states["probable"]:
                    state = "probable"
                else:
                    state = "confirmed"
                members = []
                for item in bucket:
                    item["text_subgroup_id"] = subgroup_id
                    item["text_subgroup_status"] = state
                    ad_recognition._write(run_id, item["index"], item["screen_id"], item)
                    obs = item.get("ocr_observation", {})
                    members.append({
                        "index": item["index"], "screen_id": item["screen_id"],
                        "visual_group_id": group["id"],
                        "classification": item["classification"],
                        "review_required": bool(item.get("review_required", False)),
                        "normalized_text": obs.get("normalized_text", ""),
                        "confidence": obs.get("confidence", 0),
                        "significant": obs.get("significant", {}),
                        "ocr_status": item.get("ocr", {}).get("status"),
                    })
                sample = next(
                    (item["ocr_observation"] for item in bucket if _readable(item)),
                    None,
                )
                subgroups.append({
                    "id": subgroup_id,
                    "visual_group_id": group["id"],
                    "assigned_sam": group["assigned_sam"],
                    "screen_id": group["screen_id"],
                    "candidate_id": bucket[0].get("candidate_id"),
                    "status": state,
                    "member_count": len(bucket),
                    "text": sample.get("normalized_text", "") if sample else "",
                    "significant": sample.get("significant", {}) if sample else {},
                    "members": members,
                    "reason": ("Сгруппировано по сходству прочитанных слов"
                               if sample else "OCR не прочитал текст; сохранено визуальное сопоставление"),
                })
    counts = Counter(row["status"] for row in subgroups)
    document = {
        "status": "completed", "version": VERSION, "run_id": run_id,
        "visual_group_count": len(groups), "subgroup_count": len(subgroups),
        "confirmed": counts["confirmed"], "probable": counts["probable"],
        "unidentified": counts["unidentified"], "subgroups": subgroups,
    }
    atomic_json(ad_visual_groups._root(run_id, data_root) / "text_subgroups.json", document)
    job.progress("ad_pipeline", "ad_text", len(analyses) or 1, len(analyses) or 1,
                 f"OCR · групп: {len(subgroups)}")
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
