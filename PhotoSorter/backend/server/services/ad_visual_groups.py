"""Persisted Stage 2 screen embeddings, visual groups and complete layout rankings.

Files live inside the existing per-run output tree and inherit batch retention.
The published group document is independent of layouts/OCR; rank documents are
separate, paginated on request and never cause neural inference on the API.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import numpy as np
from fastapi import HTTPException

from app.config import DATA_DIR
from app.ad_recognition import dino, scoring, visual_grouping
from app.results.exporter import atomic_json
from ..storage.paths import run_dir, owned_file
from . import ad_recognition, screen_search

VERSION = "ad-visual-groups-v1"


def _root(run_id: str, data_dir: Path | None = None) -> Path:
    root = run_dir(run_id, (data_dir if data_dir is not None else DATA_DIR) / "outputs") / "ad_pipeline"
    if root.is_symlink():
        raise HTTPException(404, "Недоступен каталог результатов рекламы")
    return root


def _vector(root: Path, index: int, screen_id: str, feature: np.ndarray) -> str:
    if not 0 <= index <= 10_000_000:
        raise ValueError("Некорректный индекс фотографии")
    identifier = str(uuid.UUID(str(screen_id)))
    directory = root / "embeddings" / str(index)
    if directory.is_symlink():
        raise ValueError("Недопустимый каталог эмбеддингов")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (identifier + ".npy")
    if path.is_symlink():
        raise ValueError("Недопустимый путь эмбеддинга")
    fd, temporary = tempfile.mkstemp(prefix=".dino.", suffix=".npy", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.save(stream, feature, allow_pickle=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path.relative_to(root).as_posix()


def collect(job, model, detections: list[tuple], run_id: str, threshold: float,
            data_dir: Path | None = None):
    """Infer each XFeat-confirmed screen ONCE and group without consulting layouts."""
    root = _root(run_id, data_dir)
    rows = []
    vectors = {}
    errors = {}
    for number, (index, sam, screen, _size) in enumerate(detections, 1):
        if job.stopped():
            raise InterruptedError("Обработка рекламы остановлена")
        sid = str(screen["screen_id"])
        try:
            crop = screen_search.crop(run_id, index, uuid.UUID(sid))
            photo = ad_recognition._crop_screen(crop, screen)
            feature = dino.embed(model, photo)
            relative = _vector(root, index, sid, feature)
            rows.append({"index": index, "sam": sam, "screen_id": sid,
                         "screen_name": screen.get("screen_name"),
                         "annotation_id": screen.get("annotation_id"),
                         "embedding_file": relative, "feature": feature})
            vectors[(index, sid)] = feature
        except (OSError, ValueError, HTTPException) as exc:
            errors[(index, sid)] = str(exc)[:350]
        job.progress("ad_pipeline", "ad_grouping", number, len(detections),
                     f"DINOv2 · экран {number}/{len(detections)}")
    if job.stopped():
        raise InterruptedError("Обработка рекламы остановлена")
    groups = visual_grouping.group_screens(rows, threshold)
    atomic_json(root / "visual_groups.json", {
        "status": "completed", "version": VERSION, "run_id": run_id,
        "dino_signature": dino.SIGNATURE, "grouping_version": visual_grouping.VERSION,
        "grouping_threshold": threshold, "screen_count": len(detections),
        "embedded_count": len(vectors), "group_count": len(groups),
        "errors": [{"index": i, "screen_id": sid, "reason": reason}
                   for (i, sid), reason in errors.items()],
        "groups": groups
    })
    job.progress("ad_pipeline", "ad_grouping", len(detections) or 1, len(detections) or 1,
                 f"DINOv2 · визуальных групп: {len(groups)}")
    return groups, vectors, errors


def match(job, run_id: str, groups: list[dict], vectors: dict,
          layouts: list[tuple], threshold: float, data_dir: Path | None = None):
    """Rank all prepared layouts using every member; persist each complete ranking."""
    root = _root(run_id, data_dir)
    directory = root / "matches"
    if directory.is_symlink():
        raise ValueError("Недопустимый каталог сопоставлений")
    directory.mkdir(parents=True, exist_ok=True)
    summaries = []
    assignments = {}
    for number, group in enumerate(groups, 1):
        if job.stopped():
            raise InterruptedError("Обработка рекламы остановлена")
        members = [
            {"index": member["index"], "screen_id": member["screen_id"],
             "feature": vectors[(member["index"], member["screen_id"])]}
            for member in group["members"]
        ]
        ranked = scoring.rank_group(
            members, [(row, feature) for row, feature, _path in layouts],
            minimum=threshold
        )
        atomic_json(directory / (group["id"] + ".json"), {
            "group_id": group["id"], "assigned_sam": group["assigned_sam"],
            "screen_id": group["screen_id"], "member_count": len(members),
            "dino_signature": dino.SIGNATURE, **ranked
        })
        summary = {key: ranked[key] for key in (
            "status", "reason", "candidate_id", "margin", "matching_threshold", "method")}
        summary.update(group_id=group["id"], best_score=ranked.get("best_score"),
                       candidate_count=len(ranked["rankings"]))
        summaries.append(summary)
        for member in members:
            assignments[(member["index"], member["screen_id"])] = summary
        job.progress("ad_pipeline", "ad_layout_matching", number, len(groups),
                     f"DINOv2 · сопоставлено {number}/{len(groups)} групп")
    atomic_json(root / "group_matches.json", {
        "status": "completed", "version": VERSION, "run_id": run_id,
        "dino_signature": dino.SIGNATURE, "matching_threshold": threshold,
        "layout_count": len(layouts), "group_count": len(groups), "groups": summaries
    })
    if not groups:
        job.progress("ad_pipeline", "ad_layout_matching", 1, 1, "Нет визуальных групп")
    return assignments


def _load(path: Path) -> dict | None:
    if path.is_symlink():
        raise HTTPException(404, "Недоступен сохранённый результат")
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(500, "Повреждены сохранённые результаты DINOv2") from exc


def overview(run_id: str, limit: int = 50, offset: int = 0) -> dict:
    root = _root(run_id)
    document = _load(root / "visual_groups.json")
    if document is None:
        return {"status": "not_processed", "groups": [], "total": 0}
    matched = _load(root / "group_matches.json")
    matches = {item["group_id"]: item for item in matched["groups"]} if matched else {}
    groups = []
    for group in document["groups"][offset:offset + limit]:
        groups.append({
            **{key: value for key, value in group.items() if key != "members"},
            "match": matches.get(group["id"]),
            "preview": {"index": group["members"][0]["index"],
                        "screen_id": group["screen_id"]}
        })
    return {
        "status": document["status"], "match_status": matched["status"] if matched else "pending",
        "run_id": run_id, "dino_signature": document["dino_signature"],
        "grouping_threshold": document["grouping_threshold"],
        "screen_count": document["screen_count"],
        "embedded_count": document["embedded_count"],
        "errors": document["errors"],
        "total": len(document["groups"]), "limit": limit, "offset": offset,
        "groups": groups
    }


def detail(run_id: str, group_id: str) -> dict:
    root = _root(run_id)
    document = _load(root / "visual_groups.json")
    if document is None:
        raise HTTPException(404, "Визуальная группировка ещё не выполнена")
    group = next((g for g in document["groups"] if g["id"] == group_id), None)
    if group is None:
        raise HTTPException(404, "Группа рекламы не найдена")
    rank = _load(root / "matches" / (group_id + ".json"))
    return {**group, "dino_signature": document["dino_signature"],
            "grouping_version": document["grouping_version"],
            "match": ({key: value for key, value in rank.items() if key != "rankings"}
                      if rank else {"status": "pending"})}


def rankings(run_id: str, group_id: str, limit: int = 50, offset: int = 0,
             index: int | None = None, screen_id: uuid.UUID | None = None) -> dict:
    # A real group must exist; do not expose arbitrary result filenames.
    group = detail(run_id, group_id)
    document = _load(_root(run_id) / "matches" / (group_id + ".json"))
    if document is None:
        return {"status": "pending", "group_id": group_id, "rankings": [], "total": 0}
    items = document["rankings"]
    selected = None
    if index is not None or screen_id is not None:
        if index is None or screen_id is None:
            raise HTTPException(422, "Укажите индекс ФО и физический экран")
        sid = str(screen_id)
        if not any(m["index"] == index and m["screen_id"] == sid
                   for m in group["members"]):
            raise HTTPException(404, "Экран не входит в выбранную группу")
        selected = {"index": index, "screen_id": sid}
        # Same complete candidate set, ordered by this individual screen's cosine.
        items = sorted(items, key=lambda candidate: (
            -next(m["score"] for m in candidate["member_scores"]
                  if m["index"] == index and m["screen_id"] == sid),
            candidate["id"]))
    page = []
    for candidate in items[offset:offset + limit]:
        record = {key: value for key, value in candidate.items() if key != "member_scores"}
        if selected:
            record["member_score"] = next(
                score["score"] for score in candidate["member_scores"]
                if score["index"] == selected["index"]
                and score["screen_id"] == selected["screen_id"])
        page.append(record)
    member_margin = None
    if selected and len(items) > 1:
        def individual(candidate):
            return next(score["score"] for score in candidate["member_scores"]
                        if score["index"] == selected["index"]
                        and score["screen_id"] == selected["screen_id"])
        member_margin = round(individual(items[0]) - individual(items[1]), 6)
    return {
        "status": document["status"], "reason": document["reason"],
        "group_id": group_id, "candidate_id": document["candidate_id"],
        "best_score": document.get("best_score"),
        "margin": document["margin"], "member_margin": member_margin,
        "matching_threshold": document["matching_threshold"],
        "method": document["method"], "selected_member": selected,
        "total": len(items), "limit": limit, "offset": offset,
        "rankings": page
    }


def layout_members(run_id: str, group_id: str, layout_id: str,
                   limit: int = 50, offset: int = 0) -> dict:
    # Require a valid group before resolving its match document.
    detail(run_id, group_id)
    document = _load(_root(run_id) / "matches" / (group_id + ".json"))
    if document is None:
        return {"status": "pending", "group_id": group_id,
                "layout_id": layout_id, "scores": [], "total": 0}
    candidate = next((r for r in document["rankings"] if r["id"] == layout_id), None)
    if candidate is None:
        raise HTTPException(404, "Рекламный макет не участвовал в сопоставлении")
    scores = candidate["member_scores"]
    return {
        "status": "completed", "group_id": group_id, "layout_id": layout_id,
        "layout_name": candidate["name"], "group_score": candidate["score"],
        "total": len(scores), "limit": limit, "offset": offset,
        "scores": scores[offset:offset + limit]
    }
