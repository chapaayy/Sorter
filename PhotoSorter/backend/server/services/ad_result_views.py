"""Read-only paged result projections, sourced exclusively from saved FIFO artifacts.

No model loaders or ad-library live lookups. The pinned job snapshot determines
historical layouts; all screen and OCR diagnostics come from persisted run files.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import HTTPException

from ..database import connect
from . import ad_layouts, ad_pipeline, ad_recognition, ad_visual_groups, screen_search, result_pages

UNIDENTIFIED = "unidentified"


def _page(limit: int, offset: int = 0) -> None:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Неверная страница результатов")


def _snapshot(run_id: str) -> dict:
    # Validate first so arbitrary URLs never reach the database or filesystem.
    ad_visual_groups._root(run_id)
    with connect() as db:
        row = db.execute("SELECT snapshot FROM jobs WHERE id=%s", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Запуск не найден")
    return (row["snapshot"] or {}).get("ad_pipeline", {})


def _layouts(run_id: str) -> list[dict]:
    return _snapshot(run_id).get("layouts", [])


def _original(run_id: str, index: int) -> str:
    return f"/api/images/{run_id}/megaloc/{index}?kind=query"


def _crop(run_id: str, index: int, screen_id: str) -> str:
    return (f"/api/screen-search/runs/{run_id}/photos/{index}/screens/"
            f"{screen_id}/crop")


def _screen_record(run_id: str, row: dict) -> dict:
    index = int(row["index"])
    saved = screen_search.saved(run_id, index)
    screens = []
    for screen in saved.get("screens", []):
        sid = str(screen["screen_id"])
        compact = {key: screen.get(key) for key in (
            "screen_id", "screen_name", "status", "reason",
            "reference_id", "annotation_id", "annotation_version",
            "corners", "crop_box", "inliers", "matches",
            "supported_sides", "reprojection_error_px", "area_px"
        ) if key in screen}
        if screen.get("status") == "found":
            compact["crop_url"] = _crop(run_id, index, sid)
        screens.append(compact)
    return {
        "index": index, "assigned_sam": row.get("assigned_sam"),
        "group_id": row.get("group_id"), "image_url": _original(run_id, index),
        "status": saved.get("status", "not_processed"),
        "reason": saved.get("reason", ""),
        "image_width": saved.get("image_width"),
        "image_height": saved.get("image_height"),
        "model_signature": saved.get("model_signature"),
        "screens": screens,
    }


def screen_page(run_id: str, cursor: str | None = None, limit: int = 24) -> dict:
    _page(limit)
    rows = result_pages.page(run_id, cursor=cursor, limit=limit)
    return {"status": "completed", "photos": [
        _screen_record(run_id, row) for row in rows["rows"]
    ], "next_cursor": rows["next_cursor"]}


def _subgroups(run_id: str) -> dict | None:
    return ad_visual_groups._load(
        ad_visual_groups._root(run_id) / "text_subgroups.json")


def _best(run_id: str) -> set[tuple[int, str]]:
    document = ad_pipeline.summary(run_id, internal=True)
    return {(int(row["index"]), str(row["screen_id"]))
            for row in document.get("best", [])}


def layout_list(run_id: str, limit: int = 50, offset: int = 0) -> dict:
    _page(limit, offset)
    snapshot = _snapshot(run_id)
    document = _subgroups(run_id)
    layouts = snapshot.get("layouts", [])
    if document is None:
        stage = snapshot.get("status")
        state = ("not_processed" if not snapshot.get("enabled") else
                 "processing" if stage == "running" else
                 stage if stage in ("queued", "failed") else "not_processed")
        return {"status": state, "layouts": [], "total": 0,
                "limit": limit, "offset": offset}
    counts: dict[str, dict] = defaultdict(
        lambda: {"photos": 0, "subgroups": 0,
                 "confirmed": 0, "probable": 0, "unidentified": 0,
                 "constructions": set()})
    for group in document["subgroups"]:
        lid = str(group.get("candidate_id") or UNIDENTIFIED)
        counter = counts[lid]
        counter["photos"] += int(group["member_count"])
        counter["subgroups"] += 1
        counter[group["status"]] += 1
        if group.get("assigned_sam"):
            counter["constructions"].add(group["assigned_sam"])
    ordered = []
    for row in layouts:
        key = str(row["id"])
        counter = counts.pop(key, None)
        ordered.append({
            "id": key, "name": row["name"],
            "version": row["version"], "checksum": row["checksum"],
            "prepared_text": row.get("ocr_text") or row.get("expected_text") or "",
            "image_url": f"/api/ad-results/runs/{run_id}/layouts/{key}/image",
            **_counter(counter)
        })
    # Historical run may contain an unmatched or no-layout DINO group.
    if UNIDENTIFIED in counts:
        ordered.append({"id": UNIDENTIFIED, "name": "Реклама не определена",
                        "image_url": None, "version": None, "prepared_text": "",
                        **_counter(counts.pop(UNIDENTIFIED))})
    # Never discard an unknown pinned ID if a legacy run has incomplete metadata.
    for key, counter in sorted(counts.items()):
        ordered.append({"id": key, "name": "Макет " + key,
                        "image_url": None, "version": None, "prepared_text": "",
                        **_counter(counter)})
    return {
        "status": document["status"], "run_id": run_id,
        "total": len(ordered), "limit": limit, "offset": offset,
        "layouts": ordered[offset:offset + limit],
        "grouping_threshold": snapshot.get("grouping_threshold"),
        "matching_threshold": snapshot.get("matching_threshold"),
        "layout_library_revision": snapshot.get("layout_library_revision")
    }


def _counter(counter: dict | None) -> dict:
    counter = counter or {}
    return {"photos": counter.get("photos", 0),
            "subgroups": counter.get("subgroups", 0),
            "confirmed": counter.get("confirmed", 0),
            "probable": counter.get("probable", 0),
            "unidentified": counter.get("unidentified", 0),
            "constructions": sorted(counter.get("constructions", []))}


def _layout_id(run_id: str, layout_id: str) -> str:
    if layout_id == UNIDENTIFIED:
        return layout_id
    try:
        value = str(uuid.UUID(layout_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(422, "Некорректный ID рекламного макета") from exc
    # Historical snapshot includes removed/disabled layouts, live registry must not be used.
    if not any(str(row["id"]) == value for row in _layouts(run_id)):
        raise HTTPException(404, "Рекламный макет не входил в этот запуск")
    return value


def layout_image(run_id: str, layout_id: str) -> Path:
    lid = _layout_id(run_id, layout_id)
    if lid == UNIDENTIFIED:
        raise HTTPException(404, "У неизвестной рекламы нет макета")
    row = next(row for row in _layouts(run_id) if str(row["id"]) == lid)
    return ad_layouts._file(row)


def layout_photos(run_id: str, layout_id: str, *,
                  subgroup_id: str | None = None, best_only: bool = False,
                  limit: int = 32, offset: int = 0) -> dict:
    _page(limit, offset)
    lid = _layout_id(run_id, layout_id)
    doc = _subgroups(run_id)
    if doc is None:
        return {"status": "not_processed", "photos": [], "total": 0}
    members = []
    for group in doc["subgroups"]:
        group_layout = str(group.get("candidate_id") or UNIDENTIFIED)
        if group_layout != lid:
            continue
        if subgroup_id is not None and group["id"] != subgroup_id:
            continue
        for member in group["members"]:
            members.append((group, member))
    if subgroup_id is not None and not any(g["id"] == subgroup_id for g, _ in members):
        raise HTTPException(404, "Текстовая группа не найдена у выбранного макета")
    winners = _best(run_id) if best_only else set()
    if best_only:
        members = [(g, m) for g, m in members
                   if (int(m["index"]), str(m["screen_id"])) in winners]
    members.sort(key=lambda entry: (entry[1]["index"], entry[1]["screen_id"],
                                    entry[0]["id"]))
    page = []
    for group, member in members[offset:offset + limit]:
        index = int(member["index"])
        sid = str(member["screen_id"])
        result = ad_recognition.result(run_id, index, uuid.UUID(sid))
        page.append({
            "index": index, "screen_id": sid,
            "image_url": _original(run_id, index), "crop_url": _crop(run_id, index, sid),
            "assigned_sam": group.get("assigned_sam"),
            "visual_group_id": group["visual_group_id"],
            "text_subgroup_id": group["id"], "text_subgroup_status": group["status"],
            "classification": result.get("classification", member.get("classification")),
            "quality": result.get("quality"), "review_required": result.get(
                "review_required", member.get("review_required", True)),
            "best": bool(result.get("best_for_layout", False)),
            "ocr_status": result.get("ocr", {}).get("status"),
            "ocr_reason": result.get("ocr", {}).get("reason"),
        })
    return {"status": doc["status"], "total": len(members),
            "limit": limit, "offset": offset,
            "layout_id": lid, "subgroup_id": subgroup_id, "best_only": best_only,
            "photos": page}


def ocr_page(run_id: str, cursor: str | None = None, limit: int = 24) -> dict:
    _page(limit)
    rows = result_pages.page(run_id, cursor=cursor, limit=limit)
    prepared = {str(layout["id"]): layout for layout in _layouts(run_id)}
    photos = []
    for row in rows["rows"]:
        item = _screen_record(run_id, row)
        # All detected screen statuses remain visible, including not found/error.
        for screen in item["screens"]:
            sid = screen["screen_id"]
            if screen.get("status") != "found":
                screen["recognition"] = {"status": "not_processed"}
                continue
            found = ad_recognition.result(run_id, item["index"], uuid.UUID(sid))
            selected = prepared.get(str(found.get("candidate_id")))
            evidence = found.get("ocr", {})
            screen["recognition"] = {
                "status": found.get("status", "not_processed"),
                "reason": found.get("reason"),
                "candidate_id": found.get("candidate_id"),
                "layout_name": selected.get("name") if selected else None,
                "layout_text": (selected.get("ocr_text") or selected.get("expected_text") or ""
                                if selected else None),
                "classification": found.get("classification"),
                "review_required": found.get("review_required"),
                "visual_group_id": found.get("visual_group_id"),
                "text_subgroup_id": found.get("text_subgroup_id"),
                "ocr": {
                    "status": evidence.get("status", "not_processed"),
                    "reason": evidence.get("reason"),
                    "matched_terms": evidence.get("matched_terms"),
                    "total_terms": evidence.get("total_terms"),
                    "text_similarity": evidence.get("text_similarity"),
                    "contradictions": evidence.get("contradictions", []),
                    "expected_text": evidence.get("expected_text"),
                    "lines": evidence.get("lines", [])
                },
                "observation": found.get("ocr_observation"),
                "quality": found.get("quality")
            }
        photos.append(item)
    return {"status": "completed", "photos": photos,
            "next_cursor": rows["next_cursor"]}
