"""Photo-first OCR comparison: long fine print, conflicting offers and visual safety."""
from __future__ import annotations

import uuid

import numpy as np
from PIL import Image

from app.ad_recognition import ocr
from server.services import ad_recognition, ad_text_subgroups


def lines(*texts, score=.96):
    return [{"text": text, "score": score} for text in texts]


def test_short_photo_text_confirms_long_layout_without_counting_unreadable_fine_print():
    legal = " ".join("условие"+str(n) for n in range(65))
    expected = ("БИГФЕСТ Больше выгоды от 79 ₽ 49 ₽ до 25 октября "
                "Наггетсы (4 шт.) " + legal)
    photo = lines("БИГФЕСТ", "Больше", "ВЫГОДЫ", "OT", "7gp:",
                  "49P", "25", "октября", "Нагтетсы(4ит.)")
    result = ocr.confirm(expected, photo)
    assert result["status"] == "confirmed", result
    assert result["scoring_basis"] == "recognized_photo_text"
    assert result["total_terms"] <= 11
    assert result["matched_terms"] >= 7
    assert result["reference_terms"] > result["total_terms"]
    assert result["text_similarity"] >= .70
    assert "49" in result["matched_items"]
    assert "7gp" in result["unmatched_items"]
    assert result["contradictions"] == []


def test_photo_date_and_price_override_generic_shared_slogan():
    expected = "БИГФЕСТ Больше выгоды до 25 октября 49 ₽"
    result = ocr.confirm(expected, lines(
        "БИГФЕСТ", "Больше", "выгоды", "до", "11 ноября", "49P"))
    assert result["status"] == "mismatch"
    assert "dates" in {c["kind"] for c in result["contradictions"]}
    result = ocr.confirm(expected, lines(
        "БИГФЕСТ", "Больше", "выгоды", "до", "25 октября", "39 ₽"))
    assert result["status"] == "mismatch"
    assert "prices" in {c["kind"] for c in result["contradictions"]}


def test_old_crossed_out_price_and_correct_price_do_not_conflict():
    expected = "БИГФЕСТ больше выгоды от 79 ₽ сейчас 49 ₽"
    photo = lines("БИГФЕСТ", "Больше", "ВЫГОДЫ", "49P")
    match = ocr.confirm(expected, photo)
    assert match["status"] == "confirmed", match
    assert match["contradictions"] == []
    assert "49" in ocr._critical("49P")["prices"]


def test_split_currency_marker_does_not_turn_correct_price_into_mismatch():
    # Real PaddleOCR reference text can retain the old-price currency marker,
    # but drop the new-price marker ("79 Р* ... 49"). The new price still
    # clearly exists as a digit token in the ORIGINAL layout OCR.
    expected = ("БИГФЕСТ Больше ВЫГОДЫ ОТ 79 Р* 49 25 октября "
                "Наггетсы 4 шт")
    image = lines("БИГФЕСТ", "Больше", "ВЫГОДЫ", "OT", "7gp:",
                  "49P", "25", "октября", "Нагтетсы(4ит.)")
    assert ocr._critical(expected)["prices"] == ["79"]
    assert "49" in ocr._critical(expected)["numbers"]
    assert ocr._critical("49P")["prices"] == ["49"]
    decision = ocr.confirm(expected, image)
    assert decision["status"] == "confirmed", decision
    assert decision["text_similarity"] >= .70
    assert decision["contradictions"] == []
    assert decision["matched_terms"] >= 7

    # A genuinely foreign price still contradicts the same reference.
    wrong_price = ocr.confirm(expected, lines(
        "БИГФЕСТ", "Больше", "ВЫГОДЫ", "39P", "25", "октября"))
    assert wrong_price["status"] == "mismatch"
    assert "prices" in {item["kind"] for item in wrong_price["contradictions"]}


def test_one_word_or_weak_ocr_never_confirms():
    expected = "БИГФЕСТ Большая акция 25 октября 49 ₽"
    assert ocr.confirm(expected, lines("БИГФЕСТ"))["status"] == "probable"
    assert ocr.confirm(expected, lines("БИГФЕСТ", "Большая", "акция", score=.55))[
        "status"] == "probable"
    assert ocr.confirm(expected, [])["status"] == "unreadable"


def test_moderately_confident_contradictory_date_blocks_automatic_confirmation():
    expected = "БИГФЕСТ Больше выгоды до 25 октября 49 ₽"
    photo = lines("БИГФЕСТ", "Больше", "выгоды", "до", "11 ноября", "49P",
                  score=.79)
    result = ocr.confirm(expected, photo)
    assert result["status"] == "probable"
    assert result["possible_contradictions"]
    assert not result["contradictions"]


def test_candidate_never_reassigned_when_text_matches_multiple_visual_layouts(tmp_path, monkeypatch):
    from app.ad_recognition import dino
    sid = str(uuid.UUID(int=1))
    pic = tmp_path / "screen.png"
    Image.new("RGB", (100, 80), "red").save(pic)
    monkeypatch.setattr(ad_recognition.screen_search, "crop", lambda *_: pic)
    monkeypatch.setattr(ad_recognition.screen_search, "saved",
                        lambda *_: {"model_signature": "xfeat"})
    monkeypatch.setattr(ad_recognition, "_crop_screen",
                        lambda *_: Image.new("RGB", (100, 80), "red"))
    monkeypatch.setattr(dino, "embed", lambda *_: (_ for _ in ()).throw(
        AssertionError("DINO must not be recalculated")))
    monkeypatch.setattr(ocr, "read",
                        lambda *_: lines("БИГФЕСТ", "Больше", "выгоды"))
    first_id, second_id = str(uuid.UUID(int=10)), str(uuid.UUID(int=11))
    features = np.zeros(384, dtype="float32")
    features[0] = 1.
    alternate = features.copy()
    alternate[0] = .8
    alternate[1] = .6
    layout_a = {"id": first_id, "name": "Выпуск 1", "version": 1,
                "checksum": "a"*64, "ocr_text": "БИГФЕСТ Больше выгоды до 25 октября"}
    layout_b = {"id": second_id, "name": "Выпуск 2", "version": 1,
                "checksum": "b"*64, "ocr_text": "БИГФЕСТ Больше выгоды до 11 ноября"}
    group = {"group_id": "R0001", "status": "matched", "candidate_id": first_id,
             "reason": "Группа совпала", "best_score": 1.0, "margin": .2,
             "matching_threshold": .5, "candidate_count": 2}
    item = ad_recognition._identify(
        object(), object(), {"screen_id": sid},
        "20261108T120000-123abc123abc", 0,
        [(layout_a, features, pic), (layout_b, alternate, pic)],
        {}, [], .5, features, group)
    assert item["status"] == "matched"
    assert item["candidate_id"] == first_id
    assert item["ocr"]["status"] == "probable"
    assert item["ocr"]["ambiguous_candidates"] == [second_id]
    assert item["review_required"]
    assert item["classification"] == "probable"


def test_final_ocr_groups_never_merge_distinct_layout_candidates():
    first = {"candidate_id": "A", "ocr_observation": ocr.describe(
        lines("БИГФЕСТ", "25 октября"))}
    second = {"candidate_id": "B", "ocr_observation": ocr.describe(
        lines("БИГФЕСТ", "25 октября"))}
    assert not ad_text_subgroups._compatible(first, second)
