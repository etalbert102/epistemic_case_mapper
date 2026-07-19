from __future__ import annotations

import re
from typing import Any


def quantity_type(quantities: list[str]) -> str:
    text = " ".join(quantities).lower()
    if not text:
        return "none"
    if "confidence interval" in text or "ci" in text:
        return "interval_or_estimate"
    if re.search(r"\b(rr|hr|or)\b|risk|ratio", text):
        return "effect_estimate"
    if "%" in text:
        return "percentage"
    if re.search(r"\b(day|week|month|year|hour)\b", text):
        return "duration_or_frequency"
    if re.search(r"\d", text):
        return "numeric"
    return "textual_quantity"


def quantity_direction(quantity: str, claim: str) -> str:
    text = f"{quantity} {claim}".lower()
    if any(term in text for term in ("reduced", "lower", "decreased", "below")):
        return "lower_or_reduced"
    if any(term in text for term in ("increased", "higher", "greater", "above")):
        return "higher_or_increased"
    if any(term in text for term in ("no association", "not associated", "neutral", "near null")):
        return "near_null_or_no_clear_difference"
    return "unspecified"


def topic_key(text: str) -> str:
    terms = [
        term
        for term in re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower())
        if len(term) > 3 and term not in STOPWORDS
    ]
    return " ".join(terms[:5])


def short_text(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def first(values: list[str]) -> str:
    return values[0] if values else ""


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        text = str(item).strip()
        key = norm(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.%/-]+", " ", str(text).lower())).strip()


STOPWORDS = {
    "about",
    "above",
    "across",
    "after",
    "again",
    "against",
    "also",
    "because",
    "been",
    "before",
    "being",
    "between",
    "could",
    "does",
    "from",
    "have",
    "into",
    "only",
    "should",
    "that",
    "their",
    "there",
    "this",
    "when",
    "where",
    "with",
    "would",
}
