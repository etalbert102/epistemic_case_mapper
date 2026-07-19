from __future__ import annotations

import re
from typing import Any


CONTEXT_FIELDS = (
    "population",
    "exposure_or_option",
    "outcome_or_endpoint",
    "evidence_design",
    "stated_dose_or_threshold",
    "stated_scope",
    "stated_limitations",
    "applicability_limits",
)


def whole_doc_source_card(claim: dict[str, Any]) -> dict[str, Any]:
    value = claim.get("whole_doc_source_card")
    return value if isinstance(value, dict) else {}


def claim_context(value: Any) -> dict[str, str]:
    context = value if isinstance(value, dict) else {}
    return {field: _clean(context.get(field)) for field in CONTEXT_FIELDS if _clean(context.get(field))}


def source_context_fields(card: dict[str, Any], source_cards: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [card, *source_cards]
    result = {
        field: _first_text(rows, field)
        for field in ("population", "exposure_or_intervention", "outcome_or_endpoint", "evidence_type", "natural_bottom_line")
    }
    result["must_preserve_terms"] = dedupe_texts(
        term
        for row in rows
        for term in string_list(row.get("must_preserve_terms"))
    )[:10]
    result["claim_context"] = merge_claim_contexts(*(row.get("claim_context") for row in rows))
    return result


def merge_claim_contexts(*contexts: Any) -> dict[str, str]:
    merged: dict[str, str] = {}
    for value in contexts:
        for key, text in claim_context(value).items():
            merged.setdefault(key, text)
    return merged


def merged_cluster_source_context(cluster: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    update: dict[str, Any] = {}
    for key in ("population", "exposure_or_intervention", "outcome_or_endpoint", "evidence_type", "natural_bottom_line"):
        if not _clean(cluster.get(key)) and _clean(bundle.get(key)):
            update[key] = _clean(bundle.get(key))
    update["claim_context"] = merge_claim_contexts(cluster.get("claim_context"), bundle.get("claim_context"))
    return update


def writer_source_local_context(item: dict[str, Any]) -> dict[str, str]:
    context = claim_context(item.get("claim_context"))
    fields = {
        "population": item.get("population") or context.get("population"),
        "exposure_or_intervention": item.get("exposure_or_intervention") or context.get("exposure_or_option"),
        "outcome_or_endpoint": item.get("outcome_or_endpoint") or context.get("outcome_or_endpoint"),
        "evidence_type": item.get("evidence_type") or context.get("evidence_design"),
        "stated_scope": context.get("stated_scope"),
        "stated_limitations": context.get("stated_limitations"),
        "applicability_limits": context.get("applicability_limits"),
    }
    return {key: _short_text(value, 220) for key, value in fields.items() if _clean(value)}


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    return [text] if text else []


def dedupe_texts(items: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clean(item)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _first_text(rows: list[dict[str, Any]], field: str) -> str:
    return next((_clean(row.get(field)) for row in rows if _clean(row.get(field))), "")


def _short_text(value: Any, limit: int) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
