from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_residual_quantities import quantity_signature


def quantity_prompt_candidate(row: dict[str, Any]) -> dict[str, Any]:
    candidate = {
        "candidate_id": row.get("candidate_id"),
        "group_id": row.get("group_id"),
        "memo_role": row.get("memo_role"),
        "group_proposition": _short_text(str(row.get("group_proposition") or ""), 280),
        "quantity": row.get("value"),
        "source_evidence_item_id": row.get("source_evidence_item_id"),
        "source_claim": _short_text(_sanitize_quantity_context(str(row.get("source_claim") or ""), row), 320),
        "local_quantity_context": _local_quantity_context(row),
        "source_labels": row.get("source_labels", []),
    }
    flags = _string_list(row.get("deterministic_warnings"))
    if flags:
        candidate["screening_flags"] = flags
    return candidate


def _local_quantity_context(row: dict[str, Any]) -> str:
    value = str(row.get("value") or "").strip()
    excerpt = str(row.get("source_excerpt") or "").strip()
    if not value or not excerpt:
        return ""
    focused = _focused_quantity_phrase(value, excerpt)
    if focused:
        return _short_text(_sanitize_quantity_context(focused, row), 220)
    return _short_text(_sanitize_quantity_context(_window_around_value(value, excerpt), row), 220)


def _sanitize_quantity_context(text: str, row: dict[str, Any]) -> str:
    candidate = str(row.get("value") or "").strip()
    excluded = [
        quantity
        for quantity in [
            *_string_list(row.get("claim_bound_quantity_values")),
            *_string_list(row.get("residual_quantity_values")),
            *_string_list(row.get("excluded_quantity_values")),
        ]
        if quantity_signature(quantity) != quantity_signature(candidate)
    ]
    cleaned = str(text or "")
    candidate_norm = quantity_signature(candidate)
    for quantity in sorted(excluded, key=len, reverse=True):
        excluded_norm = quantity_signature(quantity)
        if excluded_norm and (excluded_norm in candidate_norm or candidate_norm in excluded_norm):
            continue
        cleaned = re.sub(re.escape(quantity), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bI\s*2\s*=\s*(?:[,.;)]|$)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bI²\s*=\s*(?:[,.;)]|$)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(\s*[,; ]*\)", "", cleaned)
    cleaned = re.sub(r"\s+([,.;:)])", r"\1", cleaned)
    cleaned = re.sub(r"([(])\s+", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" ,;:")


def _focused_quantity_phrase(value: str, excerpt: str) -> str:
    value_pattern = re.escape(str(value).strip())
    measure_prefix = r"(?:hazard ratio|relative risk|risk ratio|odds ratio|mean difference|confidence interval|95% confidence interval|hr|rr|or)"
    before = re.search(rf"({measure_prefix}[^.;:\n]{{0,90}}?{value_pattern}[^.;:\n]{{0,120}})", excerpt, flags=re.IGNORECASE)
    if before:
        return _trim_descriptor_tail(before.group(1))
    after = re.search(rf"([^.;:\n]{{0,90}}{value_pattern}[^.;:\n]{{0,120}}?(?:confidence interval|ci)[^.;:\n]{{0,80}})", excerpt, flags=re.IGNORECASE)
    if after:
        return _trim_descriptor_tail(after.group(1))
    return ""


def _trim_descriptor_tail(text: str) -> str:
    text = re.split(
        r"\b(?:in|from|across|among)\s+\d[\d\s,]*(?:risk estimates?|participants?|events?|cohorts?|studies|trials|person years?)\b",
        str(text or ""),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return re.sub(r"\s+", " ", text).strip(" ,;:")


def _window_around_value(value: str, excerpt: str, *, before_chars: int = 90, after_chars: int = 90) -> str:
    lowered = excerpt.lower()
    index = lowered.find(str(value).lower())
    if index < 0:
        return excerpt[: before_chars + after_chars]
    start = max(0, index - before_chars)
    end = min(len(excerpt), index + len(value) + after_chars)
    return _trim_descriptor_tail(excerpt[start:end])
