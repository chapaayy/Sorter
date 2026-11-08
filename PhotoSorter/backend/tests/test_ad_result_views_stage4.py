"""Stage 4 results: saved-only projections and historical snapshots, no inference."""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi import HTTPException
from PIL import Image

from server.services import (
    ad_pipeline, ad_layouts, ad_result_views, ad_recognition,
    ad_visual_groups, screen_search, result_pages,
)

RUN = "20261108T120000-123abc123abc"
SCREEN = str(uuid.UUID(int=1))
LAYOUT = str(uuid.UUID(int=100))
UNKNOWN = str(uuid.UUID(int=200))


def _json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def saved(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for module in (ad_pipeline, ad_recognition, ad_visual_groups,
                   screen_search, result_pages):
        monkeypatch.setattr(module, "DATA_DIR", data)
    monkeypatch.setattr(ad_layouts, "ROOT", data / "ad_layouts")
    original = data / "ad_layouts" / (LAYOUT + ".png")
    original.parent.mkdir(parents=True)
    Image.new("RGB", (80, 60), "red").save(original)
    pinned = {"id": LAYOUT, "name": "Бигфест — ноябрь",
              "version": 9, "checksum": "a" * 64,
              "target_path": str(original), "ocr_text": "До 11 ноября"}
    other = {"id": UNKNOWN, "name": "Старая акция", "version": 2,
             "checksum": "b" * 64, "target_path": str(original),
             "ocr_text": "Скидки 50"}
    snapshot = {"enabled": True, "layouts": [pinned, other],
                "grouping_threshold": .72, "matching_threshold": .81,
                "layout_library_revision": 8}
    monkeypatch.setattr(ad_result_views, "_snapshot", lambda _run: snapshot)
    root = data / "outputs" / RUN
    rows = [
        {"index": i, "query": f"FO{i}.png", "assigned_sam": "SAM 0001",
         "group_id": "G0001"} for i in range(3)
    ]
    _json(root / "megaloc" / "manifest.json", rows)
    source = root / "megaloc" / "manifest.rows.jsonl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    geometry = {"screen_id": SCREEN, "screen_name": "LED",
                "status": "found", "reference_id": str(uuid.UUID(int=3)),
                "annotation_id": str(uuid.UUID(int=4)),
                "annotation_version": 5,
                "crop_box": {"x": 1, "y": 1, "width": 60, "height": 40},
                "corners": [{"x": 2, "y": 3}, {"x": 61, "y": 3},
                            {"x": 61, "y": 43}, {"x": 2, "y": 43}],
                "matches": 42, "inliers": 31, "reprojection_error_px": .31}
    _json(root / "screen_search" / "0" / "result.json", {
        "index": 0, "status": "found", "assigned_sam": "SAM 0001",
        "image_width": 120, "image_height": 100,
        "model_signature": "xfeat-pinned", "screens": [geometry]})
    _json(root / "screen_search" / "1" / "result.json", {
        "index": 1, "status": "not_found", "reason": "Нет совпадений",
        "screens": []})
    _json(root / "screen_search" / "2" / "result.json", {
        "index": 2, "status": "error", "reason": "Источник не прочитан",
        "screens": []})
    _json(root / "ad_recognition" / "0" / (SCREEN + ".json"), {
        "index": 0, "screen_id": SCREEN, "candidate_id": LAYOUT,
        "status": "matched", "classification": "probable",
        "review_required": True, "visual_group_id": "R0001",
        "text_subgroup_id": "T0001", "quality": {
            "status": "measured", "score": 82.3,
            "metrics": {"sharpness": .8, "glare": .9}},
        "ocr": {"status": "mismatch", "reason": "Другая дата",
                "contradictions": [{"kind": "dates",
                    "expected": ["11.11"], "observed": ["25.10"]}]},
        "ocr_observation": {
            "status": "readable", "confidence": .98,
            "normalized_text": "до 25 октября",
            "significant": {"dates": ["25.10"], "numbers": []},
            "raw_lines": [{"text": "До 25 октября", "score": .98}],
            "regions": []}})
    _json(root / "ad_pipeline" / "text_subgroups.json", {
        "status": "completed", "run_id": RUN, "subgroup_count": 2,
        "subgroups": [
            {"id": "T0001", "visual_group_id": "R0001",
             "assigned_sam": "SAM 0001", "screen_id": SCREEN,
             "candidate_id": LAYOUT, "status": "probable",
             "member_count": 1, "members": [{
                 "index": 0, "screen_id": SCREEN,
                 "classification": "probable", "review_required": True}]},
            {"id": "T0002", "visual_group_id": "R0002",
             "assigned_sam": "SAM 0002", "screen_id": SCREEN,
             "candidate_id": None, "status": "unidentified",
             "member_count": 1, "members": [{
                 "index": 2, "screen_id": SCREEN,
                 "classification": "unidentified", "review_required": True}]}
        ]})
    _json(root / "ad_pipeline" / "summary.json", {
        "status": "completed", "run_id": RUN,
        "best": [{"index": 0, "screen_id": SCREEN}]})
    return data, original


def test_xfeat_page_preserves_failed_photos_and_saved_polygon(saved):
    first = ad_result_views.screen_page(RUN, limit=2)
    assert [row["status"] for row in first["photos"]] == ["found", "not_found"]
    assert first["next_cursor"]
    found = first["photos"][0]["screens"][0]
    assert found["inliers"] == 31 and len(found["corners"]) == 4
    assert found["annotation_version"] == 5
    assert found["crop_url"].endswith("/screens/" + SCREEN + "/crop")
    after = ad_result_views.screen_page(RUN, cursor=first["next_cursor"], limit=2)
    assert [row["status"] for row in after["photos"]] == ["error"]


def test_historical_layout_versions_and_unidentified_are_separate(saved):
    data, original = saved
    page = ad_result_views.layout_list(RUN, limit=20)
    assert page["status"] == "completed"
    assert page["matching_threshold"] == .81
    assert page["grouping_threshold"] == .72
    assert page["layout_library_revision"] == 8
    assert page["total"] == 3
    assert page["layouts"][0]["version"] == 9
    assert page["layouts"][0]["name"] == "Бигфест — ноябрь"
    assert page["layouts"][0]["photos"] == 1
    assert page["layouts"][2]["id"] == "unidentified"
    assert page["layouts"][2]["unidentified"] == 1
    assert ad_result_views.layout_image(RUN, LAYOUT) == original
    with pytest.raises(HTTPException) as exc:
        ad_result_views.layout_image(RUN, str(uuid.UUID(int=500)))
    assert exc.value.status_code == 404


def test_best_filter_and_subgroup_are_saved_only(saved):
    photos = ad_result_views.layout_photos(RUN, LAYOUT)
    assert photos["total"] == 1
    item = photos["photos"][0]
    assert item["index"] == 0 and item["quality"]["score"] == 82.3
    assert item["ocr_status"] == "mismatch"
    assert item["text_subgroup_id"] == "T0001"
    assert ad_result_views.layout_photos(RUN, LAYOUT, best_only=True)["total"] == 1
    assert ad_result_views.layout_photos(RUN, "unidentified")["total"] == 1
    assert ad_result_views.layout_photos(RUN, LAYOUT, subgroup_id="T0001")["total"] == 1
    with pytest.raises(HTTPException):
        ad_result_views.layout_photos(RUN, LAYOUT, subgroup_id="T0002")
    with pytest.raises(HTTPException):
        ad_result_views.layout_photos(RUN, "../config", limit=12)


def test_ocr_page_preserves_pinned_text_and_independent_conflicts(saved):
    result = ad_result_views.ocr_page(RUN, limit=2)
    screen = result["photos"][0]["screens"][0]
    found = screen["recognition"]
    assert found["layout_name"] == "Бигфест — ноябрь"
    assert found["layout_text"] == "До 11 ноября"
    assert found["visual_group_id"] == "R0001"
    assert found["text_subgroup_id"] == "T0001"
    assert found["observation"]["confidence"] == .98
    assert found["ocr"]["contradictions"][0]["kind"] == "dates"
    assert result["photos"][1]["screens"] == []
