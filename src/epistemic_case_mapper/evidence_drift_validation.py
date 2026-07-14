from __future__ import annotations

import json
import re
from typing import Any


SOURCE_LABEL_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&'./-]+(?:\s+|$)){1,8}"
    r"(?:Study|Trial|Review|Report|Guidance|Guideline|Meta-Analysis|Meta Analysis|Analysis|Cohort|Survey|Memo|Dataset|Database)\b"
)
CITATION_LIKE_RE = re.compile(r"\(([A-Z][A-Za-z&'.-]*(?:\s+[A-Z][A-Za-z&'.-]*){0,3}\s+(?:19|20)\d{2}[a-z]?)\)")
METRIC_ALIASES = {
    "hr": "hr",
    "hazard ratio": "hr",
    "rr": "rr",
    "relative risk": "rr",
    "risk ratio": "rr",
    "or": "or",
    "odds ratio": "or",
    "ci": "ci",
    "confidence interval": "ci",
    "i2": "i2",
    "p": "p",
    "n": "n",
}
METRIC_PATTERN = r"HR|RR|OR|CI|I2|p|n|N|hazard ratio|relative risk|risk ratio|odds ratio|confidence interval"
VALUE_PATTERN = r"\d+(?:,\d{3})*(?:\.\d+)?"
QUANTITY_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    rf"(?:{METRIC_PATTERN})?\s*"
    r"(?:[<>]=?\s*)?"
    rf"{VALUE_PATTERN}"
    r"(?:\s*(?:%|mg|g|kg|mcg|ug|µg|mL|ml|L|IU|ppm|ppb|PM2\.5|per\s+\d+(?:,\d{3})?|\bCI\b|\bRR\b|\bOR\b|\bHR\b))"
    rf"|(?<![A-Za-z0-9])(?:{METRIC_PATTERN})\s*[:=]?\s*{VALUE_PATTERN}"
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
    allowed_quantities = _allowed_quantity_index(allowed_text)
    issues: list[str] = []

    unsupported_quantities = [
        quantity
        for quantity in _distinct(_normalize_quantity(match.group(0)) for match in QUANTITY_RE.finditer(text))
        if quantity and quantity not in allowed_norm and not _quantity_supported(quantity, allowed_quantities)
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
    expanded: set[str] = set()
    for label in labels:
        if not label:
            continue
        expanded.add(label)
        expanded.update(_source_label_aliases(label))
    return expanded


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


def _allowed_quantity_index(allowed_text: str) -> dict[str, set[str]]:
    """Index allowed quantities by exact form, value, and metric/value equivalence.

    The memo may say "HR 1.10" while source excerpts often write one metric
    label followed by several values, e.g. "hazard ratio 1.15 ..., unprocessed
    red meat (1.10...)".  This index treats those notation variants as the same
    allowed quantity without inventing quantities whose numeric value is absent.
    """

    exact: set[str] = set()
    values: set[str] = set()
    metric_values: set[str] = set()
    text = str(allowed_text or "")
    for match in QUANTITY_RE.finditer(text):
        quantity = _normalize_quantity(match.group(0))
        if not quantity:
            continue
        exact.add(quantity)
        for value in _quantity_values(quantity):
            values.add(value)
        parsed = _quantity_metric_values(quantity)
        if parsed["metric"]:
            for value in parsed["values"]:
                metric_values.add(f"{parsed['metric']}:{value}")
    for sentence in _sentences(text):
        metric = _sentence_metric(sentence)
        if not metric:
            continue
        for value in _quantity_values(sentence):
            metric_values.add(f"{metric}:{value}")
    values.update(_quantity_values(text))
    return {"exact": exact, "values": values, "metric_values": metric_values}


def _quantity_supported(quantity: str, allowed_quantities: dict[str, set[str]]) -> bool:
    normalized = _normalize_quantity(quantity)
    if normalized in allowed_quantities["exact"]:
        return True
    parsed = _quantity_metric_values(normalized)
    if parsed["metric"]:
        return any(
            f"{parsed['metric']}:{value}" in allowed_quantities["metric_values"] or value in allowed_quantities["values"]
            for value in parsed["values"]
        )
    return any(value in allowed_quantities["values"] for value in parsed["values"])


def _quantity_metric_values(quantity: str) -> dict[str, Any]:
    normalized = _normalize_quantity(quantity)
    metric = _sentence_metric(normalized)
    return {"metric": metric, "values": _quantity_values(normalized)}


def _sentence_metric(text: str) -> str:
    for match in re.finditer(METRIC_PATTERN, str(text), flags=re.IGNORECASE):
        metric = METRIC_ALIASES.get(match.group(0).lower())
        if metric:
            return metric
    return ""


def _quantity_values(text: str) -> list[str]:
    return _distinct([match.group(0).replace(",", "") for match in re.finditer(VALUE_PATTERN, str(text))])


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


def _source_label_aliases(label: str) -> set[str]:
    """Allow compact author-year labels derived from an allowed source title."""
    text = re.sub(r"[_-]+", " ", str(label))
    match = re.search(r"\b((?:19|20)\d{2}[a-z]?)\b", text)
    if not match:
        return set()
    year = match.group(1)
    before_year = text[: match.start()]
    tokens = [
        token.strip(" .,:;()[]{}")
        for token in re.findall(r"[A-Za-z][A-Za-z'.-]{2,}", before_year)
        if token.strip(" .,:;()[]{}")
    ]
    aliases: set[str] = set()
    for token in tokens[-8:]:
        if token.lower() in _SOURCE_ALIAS_STOPWORDS:
            continue
        aliases.add(f"{token} {year}")
    if len(tokens) >= 2:
        pair = " ".join(tokens[-2:])
        if not any(part.lower() in _SOURCE_ALIAS_STOPWORDS for part in tokens[-2:]):
            aliases.add(f"{pair} {year}")
    return aliases


_SOURCE_ALIAS_STOPWORDS = {
    "abstract",
    "analysis",
    "article",
    "cohort",
    "database",
    "dataset",
    "deep",
    "full",
    "fuller",
    "fullish",
    "guidance",
    "guideline",
    "jama",
    "journal",
    "meta",
    "prospective",
    "research",
    "report",
    "review",
    "source",
    "sources",
    "study",
    "trial",
    "updated",
}


def _short(text: str, limit: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3].rstrip(" ,.;") + "..."
