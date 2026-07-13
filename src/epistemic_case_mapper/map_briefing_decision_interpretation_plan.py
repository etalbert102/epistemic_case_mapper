from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


def build_decision_interpretation_plan(model_context: dict[str, Any]) -> dict[str, Any]:
    """Project evidence rows into prose-ready decision interpretations."""

    context = model_context if isinstance(model_context, dict) else {}
    evidence = _list(context.get("decision_evidence_table"))
    ledger = _list(context.get("mandatory_evidence_ledger"))
    rows = [_interpretation_row(row) for row in evidence if isinstance(row, dict)]
    ledger_ids = {str(row.get("item_id") or "") for row in ledger if isinstance(row, dict)}
    interpreted_ids = {str(row.get("item_id") or "") for row in rows if str(row.get("item_id") or "")}
    for row in ledger:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "")
        if item_id and item_id in interpreted_ids:
            continue
        rows.append(_interpretation_row(row))
    missing = sorted(item_id for item_id in ledger_ids if item_id and item_id not in {str(row.get("item_id") or "") for row in rows})
    return {
        "schema_id": "decision_interpretation_plan_v1",
        "method": "deterministic_projection_from_existing_roles_relations_and_quantities",
        "interpretation_count": len(rows),
        "missing_mandatory_item_ids": missing,
        "interpretations": rows,
    }


def _interpretation_row(row: dict[str, Any]) -> dict[str, Any]:
    role = str(row.get("role") or "").strip()
    relation = str(row.get("answer_relation") or "").strip()
    claim = _short(row.get("claim") or row.get("reader_claim"), 420)
    projected = {
        "item_id": row.get("item_id"),
        "role": role,
        "answer_relation": relation,
        "claim": claim,
        "source_label": row.get("source_label"),
        "source_labels": _string_list(row.get("source_labels")),
        "source_id": row.get("source_id"),
        "source_ids": _string_list(row.get("source_ids")),
        "answer_effect": _answer_effect(role, relation),
        "decision_interpretation": _decision_interpretation(row, role, relation, claim),
        "quantity_meanings": _quantity_meanings(row, role),
        "reader_use": _reader_use(role, relation),
    }
    return _drop_empty(projected)


def _answer_effect(role: str, relation: str) -> str:
    if relation == "supports_answer" or role in {"strongest_support", "quantitative_anchor"}:
        return "supports_default_answer"
    if relation == "challenges_answer" or role == "strongest_counterweight":
        return "tests_or_weakens_default_answer"
    if relation == "bounds_scope" or role == "scope_boundary":
        return "bounds_where_answer_applies"
    if relation == "identifies_crux" or role == "decision_crux":
        return "marks_decision_crux_or_uncertainty"
    return "contextualizes_answer"


def _decision_interpretation(row: dict[str, Any], role: str, relation: str, claim: str) -> str:
    relevance = _short(row.get("decision_relevance"), 260)
    caveat = _short(row.get("caveat"), 220)
    if relevance:
        return relevance
    if role in {"strongest_support", "quantitative_anchor"} or relation == "supports_answer":
        return _short(f"Use this to explain why the default answer follows: {claim}", 360)
    if role == "strongest_counterweight" or relation == "challenges_answer":
        return _short(f"Use this to show what could weaken or qualify the default answer: {claim}", 360)
    if role == "scope_boundary" or relation == "bounds_scope":
        return _short(f"Use this to state where the answer applies, does not apply, or needs extra caution: {claim}", 360)
    if role == "decision_crux" or relation == "identifies_crux":
        return _short(f"Use this to name the distinction that could change the decision read: {claim}", 360)
    if caveat:
        return caveat
    return _short(f"Use this as context for interpreting the answer: {claim}", 360)


def _quantity_meanings(row: dict[str, Any], role: str) -> list[dict[str, str]]:
    quantities = row.get("quantities") if isinstance(row.get("quantities"), list) else row.get("quantities_to_preserve")
    meanings = []
    for quantity in _list(quantities):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        interpretation = _short(quantity.get("interpretation"), 220)
        meanings.append(
            {
                "value": value,
                "meaning": interpretation or _quantity_fallback_meaning(value, role),
                "retention_phrase": str(quantity.get("retention_phrase") or "").strip(),
            }
        )
    return meanings[:8]


def _quantity_fallback_meaning(value: str, role: str) -> str:
    if role == "scope_boundary":
        return f"Use {value} to bound the population, subgroup, dose, or setting where the answer changes."
    if role == "strongest_counterweight":
        return f"Use {value} to show the size of the counterweight or concern."
    if role == "decision_crux":
        return f"Use {value} to calibrate the crux rather than treating it as a standalone conclusion."
    return f"Use {value} to calibrate the size or confidence of the default answer."


def _reader_use(role: str, relation: str) -> str:
    if role in {"strongest_support", "quantitative_anchor"} or relation == "supports_answer":
        return "main_reason"
    if role == "strongest_counterweight" or relation == "challenges_answer":
        return "counterweight_disposition"
    if role == "scope_boundary" or relation == "bounds_scope":
        return "scope_or_exception"
    if role == "decision_crux" or relation == "identifies_crux":
        return "crux_or_uncertainty"
    return "interpretive_context"


def _short(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return _short_text(text, limit) if text else ""


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if value not in ("", None, []) and value != {}
    }
