"""Universal OCR word coverage, visual-only fallbacks and composite best frame."""
from __future__ import annotations

import uuid
import numpy as np
from PIL import Image
from app.ad_recognition import best, dino, ocr
from server.services import ad_recognition, ad_text_subgroups


def lines(*texts, score=.96):
    return [{"text": text, "score": score} for text in texts]


def test_short_photo_text_compared_to_long_layout_without_fine_print_penalty():
    legal = " ".join("условие"+str(n) for n in range(65))
    expected = ("БИГФЕСТ Больше выгоды от 79 ₽ 49 ₽ до 25 октября "
                "Наггетсы (4 шт.) " + legal)
    image = lines("БИГФЕСТ", "Больше", "ВЫГОДЫ", "OT", "7gp:",
                  "49P", "25", "октября", "Нагтетсы(4ит.)")
    result = ocr.confirm(expected, image)
    assert result["status"] == "confirmed", result
    assert result["scoring_basis"] == "recognized_photo_text"
    assert result["total_terms"] <= 11
    assert result["matched_terms"] >= 7
    assert result["reference_terms"] > result["total_terms"]
    assert result["text_similarity"] >= .70
    assert "49" in result["matched_items"]
    assert "7gp" in result["unmatched_items"]
    assert result["contradictions"] == []


def test_words_are_generic_and_numbers_are_not_reclassified_as_dates_or_prices():
    same = ocr.confirm("Samsung Galaxy S26", lines("Galaxy", "Samsung", "S26"))
    assert same["status"] == "confirmed"
    other = ocr.confirm("Samsung Galaxy S26", lines("Galaxy", "Samsung", "S25"))
    assert other["matched_terms"] == 2
    assert other["total_terms"] == 3
    assert other["status"] == "probable"
    assert other["contradictions"] == []
    discount = ocr.confirm("Скидки 30%", lines("Скидки 50%"))
    assert discount["matched_terms"] == 1
    assert discount["status"] == "probable"
    assert discount["contradictions"] == []


def test_one_or_two_words_are_not_blocked_by_arbitrary_minimum():
    assert ocr.confirm("Чистота", lines("Чистота"))["status"] == "confirmed"
    result = ocr.confirm("Мир техники", lines("Мир", "техники"))
    assert result["status"] == "confirmed"
    assert result["total_terms"] == 2
    assert ocr.confirm("Мир техники", [])["status"] == "unreadable"
    assert ocr.confirm("Мир техники", lines("Мир", score=.55))[
        "status"] == "unreadable"


def test_disconnected_currency_symbols_and_partial_ocr_do_not_block_best_frame():
    expected = "БИГФЕСТ Больше ВЫГОДЫ ОТ 79 Р* 49 25 октября Наггетсы 4 шт"
    result = ocr.confirm(expected, lines(
        "БИГФЕСТ", "Больше", "ВЫГОДЫ", "OT", "7gp:", "49P", "25", "октября"))
    assert result["matched_terms"] >= 6
    assert result["contradictions"] == []
    assert result["status"] == "confirmed"


def test_composite_best_photo_prefers_both_ocr_and_quality_and_uses_no_text_fallback():
    cid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    def sample(i, q, hits, terms, variant="T0001"):
        return {"index": i, "assigned_sam": "SAM 0001", "screen_id": sid,
                "candidate_id": cid, "visual_group_id": "R0001",
                "text_subgroup_id": variant, "status": "matched",
                "review_required": False, "quality": {"status": "measured", "score": q},
                "ocr": {"matched_terms": hits, "total_terms": terms}}
    photos = [sample(0,95,0,0), sample(1,80,2,2),
              sample(2,70,4,4), sample(3,98,3,3),
              sample(4,70,3,4)]
    winners = best.select(photos)
    assert [p["index"] for p in winners] == [3]
    assert photos[0]["ocr_selection_score"] == 0
    assert photos[0]["selection_score"] == 47.5
    assert photos[3]["ocr_selection_score"] == 75.
    assert photos[3]["selection_score"] == 86.5
    fallback = [sample(5,74,0,0, "T0002"),sample(6,93,0,0,"T0002")]
    assert best.select(fallback)[0]["index"] == 6
    assert all(not row["review_required"] for row in fallback)


def test_no_ocr_does_not_require_manual_review_for_dino_matched_layout(tmp_path,monkeypatch):
    picture = tmp_path/"crop.png"
    Image.new("RGB",(80,80),"red").save(picture)
    monkeypatch.setattr(ad_recognition.screen_search,"crop",lambda *_:picture)
    monkeypatch.setattr(ad_recognition.screen_search,"saved",
                        lambda *_:{"model_signature":"xfeat"})
    monkeypatch.setattr(ad_recognition,"_crop_screen",
                        lambda *_:Image.new("RGB",(80,80),"red"))
    monkeypatch.setattr(dino,"embed",lambda *_:(_ for _ in ()).throw(
        AssertionError("DINO already embedded")))
    feature=np.zeros(384,dtype="float32");feature[0]=1.
    layout={"id":str(uuid.uuid4()),"name":"Реклама","version":1,
            "checksum":"a"*64,"ocr_text":"Только сегодня"}
    group={"group_id":"R0001","status":"matched","candidate_id":layout["id"],
           "reason":"Совместимо по DINO","best_score":.9,"margin":None,
           "matching_threshold":.5,"candidate_count":1}
    monkeypatch.setattr(ocr,"read",lambda *_:[])
    found=ad_recognition._identify(object(),object(),{"screen_id":str(uuid.uuid4())},
         "20261108T120000-123abc123abc",0,[(layout,feature,picture)],
         {},[],.5,feature,group)
    assert found["status"]=="matched"
    assert found["ocr"]["status"]=="unreadable"
    assert found["review_required"] is False
    assert found["classification"]=="probable"
    assert found["verification_basis"]=="visual_only"


def test_same_generic_text_suitable_for_two_dino_layouts_is_not_unique(tmp_path,monkeypatch):
    sid = str(uuid.uuid4())
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
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    vector = np.zeros(384, dtype="float32");vector[0] = 1.
    alt = vector.copy();alt[0] = .8;alt[1] = .6
    layout_a={"id":a,"name":"Выпуск 1","version":1,"checksum":"a"*64,
              "ocr_text":"БИГФЕСТ Больше выгоды 25 октября"}
    layout_b={"id":b,"name":"Выпуск 2","version":1,"checksum":"b"*64,
              "ocr_text":"БИГФЕСТ Больше выгоды 11 ноября"}
    group={"group_id":"R0001","status":"matched","candidate_id":a,
           "reason":"Визуальная группа","best_score":1., "margin":.2,
           "matching_threshold":.5,"candidate_count":2}
    result=ad_recognition._identify(object(),object(),{"screen_id":sid},
        "20261108T120000-123abc123abc",0,
        [(layout_a,vector,pic),(layout_b,alt,pic)],{},[],.5,vector,group)
    assert result["candidate_id"] == a
    assert result["ocr"]["status"] == "probable"
    assert result["ocr"]["ambiguous_candidates"] == [b]
    assert result["review_required"] is False


def test_text_variants_different_candidates_stay_separate_without_semantics():
    first = {"candidate_id": "A", "ocr_observation": ocr.describe(
        lines("БИГФЕСТ", "25 октября"))}
    second = {"candidate_id": "B", "ocr_observation": ocr.describe(
        lines("БИГФЕСТ", "25 октября"))}
    assert not ad_text_subgroups._compatible(first, second)
