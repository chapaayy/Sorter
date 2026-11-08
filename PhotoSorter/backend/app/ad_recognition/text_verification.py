"""Photo-first OCR verification against an already selected DINOv2 layout.

Only legible screen terms form the matching denominator; unreadable fine print
in an original layout is never treated as a missing match. This module does
not select layouts or perform OCR inference.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

VERSION = "photo-first-text-verification-v2"
MIN_LINE_CONFIDENCE = .70
MIN_CONFLICT_CONFIDENCE = .85
MIN_MATCH_RATIO = .70

_WORD = re.compile(r"[a-zа-яё0-9]+", re.I)
_PRICE_SUFFIX = re.compile(r"(\d+(?:[.,]\d+)?)[₽рp]\Z", re.I)
# Latin lookalikes frequently appear in Russian OCR (e.g. "OT" for "от").
_LOOKALIKES = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н",
    "k": "к", "m": "м", "o": "о", "p": "р", "t": "т",
    "x": "х", "y": "у",
})


def _words(text: str) -> list[str]:
    result = []
    for word in _WORD.findall(text.casefold().replace("ё", "е")):
        price = _PRICE_SUFFIX.fullmatch(word)
        result.append(price.group(1).replace(",", ".") if price else word)
    return result


def _match(term: str, reference: list[str]) -> bool:
    if term in reference:
        return True
    alternate = term.translate(_LOOKALIKES)
    if alternate in reference:
        return True
    if term.isdecimal() or len(term) < 4 or any(char.isdigit() for char in term):
        return False
    return any(
        len(other) >= 4 and not any(char.isdigit() for char in other)
        and (SequenceMatcher(None, term, other).ratio() >= .84 or
             SequenceMatcher(None, alternate, other).ratio() >= .84)
        for other in reference
    )


def _same_date(first: str, second: str) -> bool:
    left, right = first.split("."), second.split(".")
    return (left[:2] == right[:2] and
            (len(left) < 3 or len(right) < 3 or left[2] == right[2]))


def _conflicts(expected: dict, observed: dict) -> list[dict]:
    result = []
    for kind in ("dates", "prices", "percentages"):
        left = expected.get(kind, [])
        right = observed.get(kind, [])
        if not left or not right:
            continue
        compatible = any(
            _same_date(a, b) if kind == "dates" else a == b
            for a in left for b in right
        )
        if kind == "prices" and not compatible:
            # Prepared layout OCR often reads a ruble sign as a separate
            # fragment: "79 Р* ... 49". Its structured price detector then
            # sees only 79 even though 49 is plainly present in the layout.
            # An observed price that occurs as a number anywhere in the
            # pinned layout must NOT become a false hard contradiction.
            # This is conservative: currency role cannot be inferred from
            # flattened OCR text alone.
            reference_numbers = set(expected.get("numbers", ()))
            compatible = any(price in reference_numbers for price in right)
        if not compatible:
            result.append({"kind": kind, "expected": left, "observed": right})
    # Unsuffixed numbers can express an offer (e.g. "40" vs "50"), but
    # never use isolated digits or unrelated fine-print numbers as proof.
    if not result and not any(observed.get(kind) for kind in
                              ("dates", "prices", "percentages")):
        left = {v for v in expected.get("numbers", []) if len(v) >= 2}
        right = {v for v in observed.get("numbers", []) if len(v) >= 2}
        if left and right and left.isdisjoint(right):
            result.append({"kind": "numbers",
                           "expected": sorted(left), "observed": sorted(right)})
    return result


def compare(expected_text: str, observed: list[dict], *,
            describe, extract_significant) -> dict:
    """Return a transparent comparison from reliably READ photo text to layout.

    OCR observations below the per-line confidence floor remain in diagnostics
    but cannot help confirm a layout or produce hard contradictions.
    """
    observation = describe(observed)
    expected_text = expected_text or ""
    reference = _words(expected_text)
    reliable = [row for row in observation["raw_lines"]
                if row["score"] >= MIN_LINE_CONFIDENCE]
    strong = [row for row in reliable
              if row["score"] >= MIN_CONFLICT_CONFIDENCE]
    readable_text = " ".join(row["text"] for row in reliable)
    strong_text = " ".join(row["text"] for row in strong)

    # Preserve observed order, but count each visible token once so repeated
    # OCR fragments cannot artificially boost confidence.
    photo = list(dict.fromkeys(_words(readable_text)))
    matched = [term for term in photo if _match(term, reference)]
    unmatched = [term for term in photo if term not in matched]
    ratio = len(matched) / len(photo) if photo else 0.0
    weighted = sum(max(1, len(row["text"])) for row in reliable)
    confidence = (sum(max(1, len(row["text"])) * row["score"]
                      for row in reliable) / weighted) if weighted else 0.0
    expected_significant = extract_significant(expected_text)
    observed_significant = extract_significant(strong_text)
    contradictions = _conflicts(expected_significant, observed_significant)
    # Moderate-confidence conflicting dates/offers cannot prove a mismatch,
    # but must block automatic confirmation until clearer OCR is available.
    possible_conflicts = _conflicts(expected_significant,
                                    extract_significant(readable_text))

    shared_structured = any(
        (any(_same_date(x, y) for x in expected_significant["dates"]
             for y in observed_significant["dates"]) if kind == "dates" else
         bool(set(expected_significant[kind]) & set(observed_significant[kind])))
        for kind in ("dates", "prices", "percentages")
    )
    # A short but precise offer such as "Скидки 50" still carries
    # sufficient evidence if the number was recognized confidently.
    shared_numeric = any(
        token.isdecimal() and len(token) >= 2 and token in matched
        for token in photo
    ) and bool(strong)
    sufficient = (
        len(matched) >= 3 and len(photo) >= 3 or
        len(matched) >= 2 and len(photo) >= 2
        and (shared_structured or shared_numeric)
    )
    result = {
        **observation,
        "lines": [row["text"] for row in observation["raw_lines"]],
        "expected_text": expected_text,
        "matched_terms": len(matched),
        "total_terms": len(photo),
        "matched_items": matched,
        "unmatched_items": unmatched,
        "reference_terms": len(set(reference)),
        "text_similarity": round(ratio, 3),
        "comparison_confidence": round(confidence, 3),
        "scoring_basis": "recognized_photo_text",
        "verification_version": VERSION,
        "contradictions": contradictions,
        "possible_contradictions": possible_conflicts,
    }
    if not reference:
        return {**result, "status": "not_configured",
                "reason": "У макета отсутствует контрольный OCR-текст"}
    if observation["status"] != "readable":
        return {**result, "status": "unreadable",
                "reason": "Текст на экране не прочитан; это не противоречие"}
    if contradictions:
        return {**result, "status": "mismatch",
                "reason": "Уверенно прочитанные дата, цена или предложение противоречат макету"}
    if possible_conflicts:
        return {**result, "status": "probable",
                "reason": "Возможное расхождение по дате или предложению; уверенности OCR недостаточно"}
    if (not matched and photo and confidence >= MIN_CONFLICT_CONFIDENCE
            and len(set(reference)) >= 2):
        return {**result, "status": "mismatch",
                "reason": "Уверенно прочитанный текст отсутствует в макете"}
    if sufficient and ratio >= MIN_MATCH_RATIO and confidence >= MIN_LINE_CONFIDENCE:
        return {**result, "status": "confirmed",
                "reason": (f"Совпало {len(matched)} из {len(photo)} "
                           "надёжно прочитанных элементов ФО")}
    return {**result, "status": "probable",
            "reason": ("Недостаточно надёжных совпадений по прочитанному "
                       "тексту ФО для подтверждения")}
