from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def answer_relation_by_evidence_id(analyst_adjudication: dict[str, Any]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for row in _list(analyst_adjudication.get("rows")):
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or row.get("claim_id") or "").strip()
        relation = normalize_answer_relation(row.get("answer_relation"))
        if evidence_id and relation:
            rows[evidence_id] = relation
    return rows


def memo_use_by_evidence_id(analyst_adjudication: dict[str, Any]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for row in _list(analyst_adjudication.get("rows")):
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or row.get("claim_id") or "").strip()
        memo_use = str(row.get("memo_use") or row.get("role") or "").strip()
        if evidence_id and memo_use:
            rows[evidence_id] = memo_use
    return rows


def answer_relation_for_unit(unit: dict[str, Any], *, semantic_context: dict[str, Any]) -> dict[str, str]:
    explicit = normalize_answer_relation(unit.get("answer_relation") or unit.get("answer_relation_to_default"))
    if explicit:
        return {"answer_relation": explicit, "basis": "global_decision_model_answer_relation"}
    evidence_ids = _string_list(_dict(unit.get("lineage")).get("covered_evidence_item_ids"))
    adjudicated = _dedupe(
        [
            normalize_answer_relation(_dict(semantic_context.get("answer_relation_by_evidence_id")).get(evidence_id))
            for evidence_id in evidence_ids
        ]
    )
    adjudicated = [value for value in adjudicated if value and value != "uncertain_relation"]
    if len(adjudicated) == 1:
        return {"answer_relation": adjudicated[0], "basis": "analyst_adjudication_answer_relation"}
    if len(adjudicated) > 1:
        return {"answer_relation": "uncertain_relation", "basis": "conflicting_analyst_answer_relations"}
    role = str(unit.get("role") or "context_only").strip()
    return {"answer_relation": answer_relation_from_role(role), "basis": "role_default"}


def normalize_answer_relation(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "support": "supports_answer",
        "supports": "supports_answer",
        "supports_default": "supports_answer",
        "supports_bottom_line": "supports_answer",
        "counterweight": "challenges_answer",
        "challenge": "challenges_answer",
        "challenges": "challenges_answer",
        "limits": "bounds_scope",
        "scope": "bounds_scope",
        "scope_boundary": "bounds_scope",
        "applicability": "bounds_scope",
        "crux": "identifies_crux",
        "decision_crux": "identifies_crux",
        "context": "contextualizes_answer",
        "mechanism": "contextualizes_answer",
        "background": "contextualizes_answer",
        "irrelevant": "not_decision_relevant",
        "not_relevant": "not_decision_relevant",
        "uncertain": "uncertain_relation",
    }
    normalized = aliases.get(text, text)
    allowed = {
        "supports_answer",
        "challenges_answer",
        "bounds_scope",
        "identifies_crux",
        "contextualizes_answer",
        "not_decision_relevant",
        "uncertain_relation",
    }
    return normalized if normalized in allowed else ""


def answer_relation_from_role(role: str) -> str:
    return {
        "strongest_support": "supports_answer",
        "quantitative_anchor": "supports_answer",
        "strongest_counterweight": "challenges_answer",
        "scope_boundary": "bounds_scope",
        "decision_crux": "identifies_crux",
        "context_only": "contextualizes_answer",
    }.get(role, "contextualizes_answer")


def effective_writer_role(source_role: str, relation: dict[str, str]) -> str:
    if relation.get("basis") == "role_default":
        return source_role or "context_only"
    return {
        "supports_answer": "strongest_support",
        "challenges_answer": "strongest_counterweight",
        "bounds_scope": "scope_boundary",
        "identifies_crux": "decision_crux",
        "contextualizes_answer": "context_only",
    }.get(str(relation.get("answer_relation") or ""), source_role or "context_only")


def merged_source_appraisal(evidence_ids: list[str], ledger_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    appraisals = [
        _dict(ledger_by_id.get(evidence_id, {}).get("source_appraisal"))
        for evidence_id in evidence_ids
        if isinstance(ledger_by_id.get(evidence_id, {}).get("source_appraisal"), dict)
    ]
    appraisals = [row for row in appraisals if row.get("status") == "ready"]
    if not appraisals:
        return {}
    return {
        "status": "ready",
        "source_appraisal_ids": _dedupe(
            [value for row in appraisals for value in _string_list(row.get("source_appraisal_ids"))]
        ),
        "document_types": _dedupe([value for row in appraisals for value in _string_list(row.get("document_types"))]),
        "evidence_proximity": _dedupe([value for row in appraisals for value in _string_list(row.get("evidence_proximity"))]),
        "recommended_uses": _dedupe([value for row in appraisals for value in _string_list(row.get("recommended_uses"))]),
        "decision_directness": _least_direct([str(row.get("decision_directness") or "") for row in appraisals]),
        "allowed_wording": _merged_allowed_wording(appraisals),
        "source_use_warnings": _dedupe([value for row in appraisals for value in _string_list(row.get("source_use_warnings"))]),
        "interpretation_caveats": _dedupe([value for row in appraisals for value in _string_list(row.get("interpretation_caveats"))])[:8],
    }


def _merged_allowed_wording(appraisals: list[dict[str, Any]]) -> dict[str, Any]:
    allowed_rows = [_dict(row.get("allowed_wording")) for row in appraisals if isinstance(row.get("allowed_wording"), dict)]
    if not allowed_rows:
        return {}
    qualifiers = _dedupe([value for row in allowed_rows for value in _string_list(row.get("must_qualify_with"))])
    return {
        "causal_language_allowed": all(row.get("causal_language_allowed") is not False for row in allowed_rows),
        "must_qualify_with": qualifiers,
    }


def _least_direct(values: list[str]) -> str:
    order = {"direct": 0, "partial": 1, "indirect": 2, "unknown": 3}
    cleaned = [value for value in values if value]
    if not cleaned:
        return "unknown"
    return max(cleaned, key=lambda value: order.get(value, 3))
