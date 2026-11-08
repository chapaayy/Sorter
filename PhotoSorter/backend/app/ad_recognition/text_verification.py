"""Plain word-overlap evidence for OCR read on an advertising screen.

No price/date/percentage classifications or mandatory word count. The prepared
layout text is a searchable reference; ONLY text read on the photo forms the
denominator. A weak/no OCR result cannot invalidate a DINOv2 visual match.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

VERSION = "photo-word-coverage-v1"
MIN_LINE_CONFIDENCE = .70
MIN_MATCH_RATIO = .70

_WORD = re.compile(r"[a-zа-яё0-9]+", re.I)
_PRICE_SUFFIX = re.compile(r"(\d+(?:[.,]\d+)?)[₽рp]\Z", re.I)
# Common Latin/Cyrillic homoglyphs in Russian OCR; not word semantics.
_LOOKALIKES = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н",
    "k": "к", "m": "м", "o": "о", "p": "р", "t": "т",
    "x": "х", "y": "у",
})


def words(text: str) -> list[str]:
    result = []
    for word in _WORD.findall((text or "").casefold().replace("ё", "е")):
        suffix = _PRICE_SUFFIX.fullmatch(word)
        result.append(suffix.group(1).replace(",", ".") if suffix else word)
    return result


def _matches(token: str, reference: set[str]) -> bool:
    if token in reference or token.translate(_LOOKALIKES) in reference:
        return True
    # Never fuzz digits: "30" must not become "50", "S24" must not become
    # "S25", etc. For longer alphabetic words allow minor OCR typos.
    if len(token) < 4 or any(ch.isdigit() for ch in token):
        return False
    alternate = token.translate(_LOOKALIKES)
    return any(
        len(other) >= 4 and other.isalpha()
        and max(SequenceMatcher(None, token, other).ratio(),
                SequenceMatcher(None, alternate, other).ratio()) >= .84
        for other in reference
    )


def compare(expected_text: str, observed: list[dict], *,
            describe, extract_significant=None) -> dict:
    """Score each distinct readable PHOTO word against the entire layout.

    No minimum of three words: one or two clear words may be useful for
    selecting the best frame. Confidence that the *layout* is uniquely
    identified is handled separately by DINOv2 and alternative rankings.
    """
    evidence = describe(observed)
    reference = set(words(expected_text or ""))
    readable = [line for line in evidence["raw_lines"]
                if line["score"] >= MIN_LINE_CONFIDENCE]
    photo = list(dict.fromkeys(words(" ".join(line["text"] for line in readable))))
    matched = [term for term in photo if _matches(term, reference)]
    unmatched = [term for term in photo if term not in matched]
    ratio = len(matched) / len(photo) if photo else 0.
    weight = sum(max(1, len(line["text"])) for line in readable)
    confidence = (sum(max(1, len(line["text"])) * line["score"]
                      for line in readable) / weight if weight else 0.)

    result = {
        **evidence,
        "lines": [row["text"] for row in evidence["raw_lines"]],
        "expected_text": " ".join(words(expected_text or "")),
        "matched_terms": len(matched),
        "total_terms": len(photo),
        "matched_items": matched,
        "unmatched_items": unmatched,
        "reference_terms": len(reference),
        "text_similarity": round(ratio, 3),
        "comparison_confidence": round(confidence, 3),
        "scoring_basis": "recognized_photo_text",
        "verification_version": VERSION,
        # Historical clients may display these fields; they are intentionally
        # empty because this version never guesses date/price semantics.
        "contradictions": [], "possible_contradictions": [],
    }
    if not reference:
        return {**result, "status": "not_configured",
                "reason": "У макета нет текста для сопоставления; используется DINOv2"}
    if not photo:
        return {**result, "status": "unreadable",
                "reason": "OCR не прочитал текст; макет определён визуально по DINOv2"}
    if ratio >= MIN_MATCH_RATIO and matched:
        return {**result, "status": "confirmed",
                "reason": f"На ФО совпало {len(matched)} из {len(photo)} прочитанных элементов"}
    return {**result, "status": "probable",
            "reason": f"На ФО совпало {len(matched)} из {len(photo)} прочитанных элементов"}
