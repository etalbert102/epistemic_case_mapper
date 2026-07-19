from __future__ import annotations

import ast
import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    short_text as _short_text,
)


def synthesis_group_sections(packet: dict[str, Any]) -> tuple[str, ...]:
    return (
        "primary_reasoning_chain",
        "main_counterweights",
        "decision_cruxes",
        "scope_and_applicability",
        "quantitative_anchors",
        "background_context",
    )


def foreground_sections() -> tuple[str, ...]:
    return (
        "primary_reasoning_chain",
        "main_counterweights",
        "decision_cruxes",
        "scope_and_applicability",
        "quantitative_anchors",
    )


def ledger_ids(ledger: dict[str, Any]) -> list[str]:
    return [
        str(row.get("evidence_item_id") or "")
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    ]


def ids_for_roles(rows: list[dict[str, Any]], roles: set[str], *, limit: int) -> list[str]:
    return [
        str(row.get("evidence_item_id") or "")
        for row in rows
        if str(row.get("memo_use") or "") in roles and str(row.get("evidence_item_id") or "").strip()
    ][:limit]


def is_quantity_row(row: dict[str, Any]) -> bool:
    return str(row.get("input_kind") or "") == "top_quantity_anchor"


def applicability_limits(memo_use: str, ledger_row: dict[str, Any], adjudication_row: dict[str, Any]) -> list[str]:
    limits = []
    if memo_use in {"scope_or_applicability", "decision_crux"}:
        limits.append(str(adjudication_row.get("rationale") or ledger_row.get("why_it_matters") or "").strip())
    if adjudication_row.get("downgrade_reason"):
        limits.append(str(adjudication_row.get("downgrade_reason")))
    return _dedupe([_short_text(limit, 220) for limit in limits if limit])


def why_this_read(groups: list[dict[str, Any]]) -> str:
    primary = first_group_text(groups, "load_bearing_primary_support")
    counter = first_group_text(groups, "load_bearing_counterweight")
    if primary and counter:
        return f"The primary support is: {primary} The main counterweight is: {counter}"
    return primary or counter or "The adjudicated evidence packet should be weighed directly."


def first_group_text(groups: list[dict[str, Any]], memo_use: str) -> str:
    for group in groups:
        if group.get("memo_role") == memo_use:
            return str(group.get("proposition") or "").strip()
    return ""


def must_not_overstate(groups: list[dict[str, Any]]) -> list[str]:
    lines = []
    for group in groups:
        if group.get("memo_role") in {"load_bearing_counterweight", "scope_or_applicability", "decision_crux"}:
            text = str(group.get("proposition") or group.get("rationale") or "").strip()
            if text:
                lines.append(_short_text(text, 220))
    return _dedupe(lines[:8])


def clean_answer_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = _parse_literal(text)
    if isinstance(parsed, dict):
        for key in ("current_read", "default_read", "primary_answer", "classification"):
            candidate = str(parsed.get(key) or "").strip()
            if candidate:
                return _short_text(candidate, 360)
    return _short_text(text, 360)


def content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "after",
        "also",
        "because",
        "before",
        "between",
        "could",
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
    terms = [
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z-]{3,}", text)
        if term.lower() not in stop
    ]
    return list(dict.fromkeys(terms))


def _parse_literal(text: str) -> Any:
    if not text.startswith("{"):
        return None
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None
