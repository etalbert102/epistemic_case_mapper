from __future__ import annotations

import json
import re
from typing import Any


SOURCE_LABEL_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&'./-]+(?:\s+|$)){1,8}"
    r"(?:Study|Trial|Review|Report|Guidance|Guideline|Meta-Analysis|Meta Analysis|Analysis|Cohort|Survey|Memo|Dataset|Database)\b"
)
CITATION_LIKE_RE = re.compile(r"\(([A-Z][A-Za-z&'.-]*(?:\s+[A-Z][A-Za-z&'.-]*){0,3}\s+(?:19|20)\d{2}[a-z]?)\)")
QUANTITY_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:RR|OR|HR|CI|I2|p|n|N)?\s*"
    r"(?:[<>]=?\s*)?"
    r"\d+(?:,\d{3})*(?:\.\d+)?"
    r"(?:\s*(?:%|mg|g|kg|mcg|ug|µg|mL|ml|L|IU|ppm|ppb|PM2\.5|per\s+\d+(?:,\d{3})?|\bCI\b|\bRR\b|\bOR\b|\bHR\b))"
    r"|(?<![A-Za-z0-9])(?:RR|OR|HR|CI)\s*\d+(?:\.\d+)?"
)
STRONG_UNSUPPORTED_MARKERS = (
    "proves",
    "proved",
    "guarantees",
    "guaranteed",
    "eliminates",
    "eliminated",
    "definitively",
    "conclusively",
    "settles",
    "settled",
    "no risk",
    "risk-free",
    "clearly safe",
    "proven safe",
)


def evidence_drift_issues(text: str, allowed: Any, *, subject: str = "text") -> list[str]:
    allowed_text = _stringify_allowed(allowed)
    allowed_norm = _normalize(allowed_text)
    text_norm = _normalize(text)
    issues: list[str] = []

    unsupported_quantities = [
        quantity
        for quantity in _distinct(_normalize_quantity(match.group(0)) for match in QUANTITY_RE.finditer(text))
        if quantity and quantity not in allowed_norm
    ]
    for quantity in unsupported_quantities[:5]:
        issues.append(f"{subject} introduces unsupported quantity `{quantity}`")
    if _contradictory_statistical_significance(text):
        issues.append(f"{subject} contains contradictory statistical-significance language")

    unsupported_sources = unsupported_source_labels(text, allowed)
    for label in unsupported_sources[:5]:
        issues.append(f"{subject} introduces unsupported source label `{label}`")

    for sentence in _sentences(text):
        sentence_norm = _normalize(sentence)
        if not any(marker in sentence_norm for marker in STRONG_UNSUPPORTED_MARKERS):
            continue
        if _content_overlap_count(sentence, allowed_text) < 3:
            issues.append(f"{subject} makes unsupported strong claim `{_short(sentence)}`")
            break

    return issues


def unsupported_source_labels(text: str, allowed: Any) -> list[str]:
    allowed_labels = allowed_source_labels(allowed)
    allowed_norm = {_normalize_label(label) for label in allowed_labels}
    allowed_text_norm = _normalize(_stringify_allowed(allowed))
    labels = _distinct(
        [
            *[match.group(0).strip() for match in SOURCE_LABEL_RE.finditer(_strip_markdown_headings(text))],
            *[match.group(1).strip() for match in CITATION_LIKE_RE.finditer(str(text))],
        ]
    )
    unsupported: list[str] = []
    for label in labels:
        norm = _normalize_label(label)
        if norm in allowed_norm:
            continue
        if not allowed_norm and norm in allowed_text_norm:
            continue
        unsupported.append(label)
    return unsupported


def allowed_source_labels(allowed: Any) -> set[str]:
    labels: set[str] = set()
    _collect_source_labels(allowed, labels)
    return {label for label in labels if label}


def _stringify_allowed(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _strip_markdown_headings(text: str) -> str:
    return re.sub(r"^\s*#{1,6}\s+.+$", "", str(text), flags=re.MULTILINE)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9.%<>/=]+", " ", str(text).lower()).strip()


def _normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _normalize_quantity(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.lower().replace(",", "")).strip()
    cleaned = cleaned.replace("µ", "u")
    return cleaned


def _contradictory_statistical_significance(text: str) -> bool:
    for sentence in _sentences(text):
        lowered = sentence.lower()
        if "not statistically significant" not in lowered:
            continue
        for value in re.findall(r"\bp\s*[=<]\s*(0(?:\.\d+)?|1(?:\.0+)?)", lowered):
            try:
                if float(value) <= 0.05:
                    return True
            except ValueError:
                continue
    return False


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.findall(r"[^.!?]+[.!?]", re.sub(r"\s+", " ", str(text))) if sentence.strip()]


def _content_overlap_count(text: str, allowed_text: str) -> int:
    terms = set(_content_terms(text))
    allowed_terms = set(_content_terms(allowed_text))
    return len(terms & allowed_terms)


def _content_terms(text: str) -> list[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "because",
        "before",
        "brief",
        "claim",
        "claims",
        "does",
        "evidence",
        "from",
        "have",
        "into",
        "more",
        "section",
        "source",
        "than",
        "that",
        "this",
        "with",
    }
    return [term for term in re.findall(r"[a-z][a-z0-9-]{3,}", str(text).lower()) if term not in stopwords]


def _distinct(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _collect_source_labels(value: Any, labels: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {"source", "source_title", "source_titles", "source_display_names", "source_citation_labels"}:
                if isinstance(item, dict):
                    for nested in item.values():
                        _collect_source_labels(nested, labels)
                elif isinstance(item, list):
                    for nested in item:
                        _collect_source_labels(nested, labels)
                elif str(item).strip():
                    labels.add(str(item).strip())
            else:
                _collect_source_labels(item, labels)
    elif isinstance(value, list):
        for item in value:
            _collect_source_labels(item, labels)


def _short(text: str, limit: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3].rstrip(" ,.;") + "..."
