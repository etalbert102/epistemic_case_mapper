from __future__ import annotations

import re
from typing import Any


def retention_quantity_rows(row: dict[str, Any]) -> list[dict[str, str]]:
    quantities = []
    for quantity in _list(row.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if value and quantity_required_for_retention(quantity, row):
            quantities.append(
                {
                    "value": value,
                    "retention_phrase": str(quantity.get("retention_phrase") or "").strip(),
                    "interpretation": str(quantity.get("interpretation") or "").strip(),
                }
            )
    return quantities


def quantity_retained(memo: str, quantity: dict[str, str]) -> bool:
    return any(
        contains_quantity(memo, candidate)
        for candidate in _dedupe(
            [
                str(quantity.get("value") or ""),
                str(quantity.get("retention_phrase") or ""),
                str(quantity.get("interpretation") or ""),
            ]
        )
    )


def quantity_required_for_retention(quantity: dict[str, Any], row: dict[str, Any]) -> bool:
    value = str(quantity.get("value") or "").strip()
    if not value:
        return False
    text = " ".join(
        [
            value,
            str(quantity.get("quantity_type") or ""),
            str(quantity.get("interpretation") or ""),
            str(row.get("role") or ""),
            str(row.get("obligation_type") or ""),
            str(row.get("statement") or row.get("reader_claim") or ""),
        ]
    ).lower()
    if re.fullmatch(r"(?:19|20)\d{2}(?:\s*[–-]\s*(?:19|20)\d{2})?", value):
        return False
    if re.search(r"\bci\b|\bconfidence interval\b", text):
        return True
    decision_terms = (
        "risk",
        "ratio",
        "odds",
        "hazard",
        "effect",
        "reduction",
        "increase",
        "prevalence",
        "incidence",
        "mortality",
        "dose",
        "serving",
        "per day",
        "/day",
        "mg",
        "percent",
        "%",
    )
    if any(token in text for token in decision_terms):
        return True
    return str(row.get("role") or "") == "quantitative_anchor"


def contains_quantity(text: str, quantity: str) -> bool:
    if _contains_text(text, quantity):
        return True
    if "/day" in quantity.lower() and _contains_text(text, re.sub(r"/day\b", " per day", quantity, flags=re.IGNORECASE)):
        return True
    if _quantity_signature_match(_quantity_signatures(quantity), _quantity_signatures(text)):
        return True
    normalized_text = _norm(text)
    numbers = re.findall(r"\d+(?:\.\d+)?", quantity)
    return bool(numbers) and all(number in normalized_text for number in numbers)


def _quantity_signatures(text: str) -> set[str]:
    normalized = _quantity_words(text)
    signatures: set[str] = set()
    patterns = (
        r"\b(?:up to|at most|no more than)\s+(?P<count>\d+(?:\.\d+)?)\s+(?:whole\s+)?(?P<unit>[a-z]+)s?\s+per\s+(?P<period>day|week|month|year)\b",
        r"\b(?:more than|over|above|greater than)\s+(?P<count>\d+(?:\.\d+)?)\s+(?:whole\s+)?(?P<unit>[a-z]+)s?\s+per\s+(?P<period>day|week|month|year)\b",
        r"\b(?P<count>\d+(?:\.\d+)?)\s+(?:whole\s+)?(?P<unit>[a-z]+)s?\s+per\s+(?P<period>day|week|month|year)\b",
        r"\b(?:up to|at most|no more than)\s+(?P<count>\d+(?:\.\d+)?)\s+(?:whole\s+)?(?P<unit>[a-z]+)s?\s*/\s*(?P<period>day|week|month|year)\b",
        r"\b(?:more than|over|above|greater than)\s+(?P<count>\d+(?:\.\d+)?)\s+(?:whole\s+)?(?P<unit>[a-z]+)s?\s*/\s*(?P<period>day|week|month|year)\b",
        r"\b(?P<count>\d+(?:\.\d+)?)\s+(?:whole\s+)?(?P<unit>[a-z]+)s?\s*/\s*(?P<period>day|week|month|year)\b",
        r"\b(?P<op>[<>])\s*(?P<count>\d+(?:\.\d+)?)\s*/\s*(?P<period>day|week|month|year)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized):
            unit = match.groupdict().get("unit") or "unit"
            op = _quantity_operator(match.group(0), match.groupdict().get("op", ""))
            signatures.add(f"{op}:{match.group('count')}:{unit}:{match.group('period')}")
    return signatures


def _quantity_signature_match(needles: set[str], haystack: set[str]) -> bool:
    if not needles or not haystack:
        return False
    if needles & haystack:
        return True
    for needle in needles:
        left = needle.split(":")
        for candidate in haystack:
            right = candidate.split(":")
            if len(left) == len(right) == 4 and left[0] == right[0] and left[1] == right[1] and left[3] == right[3]:
                if left[2] == "unit" or right[2] == "unit":
                    return True
    return False


def _quantity_operator(text: str, symbol: str) -> str:
    if symbol == ">":
        return "above"
    if symbol == "<":
        return "below"
    lowered = text.lower()
    if any(term in lowered for term in ("up to", "at most", "no more than")):
        return "upto"
    if any(term in lowered for term in ("more than", "over", "above", "greater than")):
        return "above"
    return "exact"


def _quantity_words(text: str) -> str:
    lowered = str(text or "").lower()
    replacements = {"one": "1", "a": "1", "an": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
    for word, number in replacements.items():
        lowered = re.sub(rf"\b{word}\b", number, lowered)
    lowered = re.sub(r"\b(?:daily|per-day)\b", "per day", lowered)
    lowered = re.sub(r"/\s*d\b", "/day", lowered)
    lowered = re.sub(r"/\s*wk\b", "/week", lowered)
    return re.sub(r"\s+", " ", lowered)


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    return not needle or needle.lower() in text.lower()


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value] if value else []


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        text = str(item).strip()
        key = _norm(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.%/-]+", " ", str(text).lower())).strip()
