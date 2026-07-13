from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
)


def build_reader_brief_plan(model_context: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic writing plan from the model-visible decision context."""

    context = model_context if isinstance(model_context, dict) else {}
    answer_frame = _dict(context.get("answer_frame"))
    evidence = _list(context.get("decision_evidence_table"))
    ledger = _list(context.get("mandatory_evidence_ledger"))
    return {
        "schema_id": "reader_brief_plan_v1",
        "writing_priority": "Use this as the writing plan; use the evidence ledger as the retention check.",
        "opening_answer": _short_text(answer_frame.get("direct_answer") or context.get("bottom_line"), 420),
        "why_sentence": _why_sentence(answer_frame, evidence),
        "paragraph_jobs": _paragraph_jobs(context),
        "hero_evidence": _evidence_rows(evidence, roles={"strongest_support", "quantitative_anchor"}, limit=4),
        "supporting_detail": _supporting_detail(ledger, limit=6),
        "caveats": _evidence_rows(evidence, roles={"strongest_counterweight", "scope_boundary", "decision_crux"}, limit=6),
        "practical_takeaway": _practical_takeaway(context),
    }


def _why_sentence(answer_frame: dict[str, Any], evidence: list[Any]) -> str:
    basis = _short_text(answer_frame.get("confidence_basis"), 320)
    if basis:
        return basis
    for row in evidence:
        if isinstance(row, dict) and row.get("role") in {"strongest_support", "quantitative_anchor"}:
            return _short_text(row.get("claim") or row.get("reader_claim"), 320)
    return ""


def _paragraph_jobs(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"section": "bottom_line", "job": "Give the answer, the main reason, and the main boundary without listing evidence."},
        {"section": "why", "job": "Explain the strongest reason the answer follows, using the highest-value quantity if one is available."},
        {"section": "bounds", "job": "Explain what would weaken, narrow, or change the answer."},
        {"section": "practical", "job": _practical_takeaway(context) or "Translate the answer into a practical next step."},
    ]


def _evidence_rows(rows: list[Any], *, roles: set[str], limit: int) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        if not isinstance(row, dict) or row.get("role") not in roles:
            continue
        selected.append(_brief_evidence_row(row))
    return selected[:limit]


def _supporting_detail(rows: list[Any], *, limit: int) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        if not isinstance(row, dict) or row.get("role") in {"strongest_support", "quantitative_anchor"}:
            continue
        selected.append(_brief_evidence_row(row))
    return selected[:limit]


def _brief_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": row.get("role"),
        "claim": _short_text(row.get("claim") or row.get("reader_claim"), 360),
        "source_id": row.get("source_id"),
        "source_ids": row.get("source_ids"),
        "quantities": _brief_quantities(row),
    }


def _brief_quantities(row: dict[str, Any]) -> list[dict[str, str]]:
    quantities = row.get("quantities") if isinstance(row.get("quantities"), list) else row.get("quantities_to_preserve")
    return [
        {"value": str(quantity.get("value") or ""), "interpretation": _short_text(quantity.get("interpretation"), 160)}
        for quantity in _list(quantities)
        if isinstance(quantity, dict) and str(quantity.get("value") or "").strip()
    ][:4]


def _practical_takeaway(context: dict[str, Any]) -> str:
    for card in _list(context.get("practical_implication_cards")):
        if isinstance(card, dict):
            text = _short_text(card.get("claim") or card.get("practical_implication") or card.get("statement"), 260)
            if text:
                return text
    for text in _list(context.get("practical_implications")):
        if str(text or "").strip():
            return _short_text(text, 260)
    return ""
