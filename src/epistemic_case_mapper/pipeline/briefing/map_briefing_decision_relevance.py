from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def analyst_relevance_plan(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _list(model.get("memo_relevance_decisions")):
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        inclusion = str(row.get("memo_inclusion") or "").strip()
        if evidence_id and inclusion:
            rows[evidence_id] = {
                "evidence_item_id": evidence_id,
                "memo_inclusion": inclusion,
                "group_id": str(row.get("group_id") or "").strip(),
                "source_ids": _string_list(row.get("source_ids")),
                "rationale": str(row.get("rationale") or "").strip(),
                "derived_from": "memo_relevance_decision",
            }
    for group in _list(model.get("evidence_groups")):
        if not isinstance(group, dict):
            continue
        inclusion = _memo_inclusion_from_group(group)
        for evidence_id in _string_list(group.get("covered_evidence_item_ids")):
            group_decision = {
                "evidence_item_id": evidence_id,
                "memo_inclusion": inclusion,
                "group_id": str(group.get("group_id") or "").strip(),
                "source_ids": _string_list(group.get("source_ids")),
                "rationale": str(group.get("answer_impact") or group.get("rationale") or "").strip(),
                "derived_from": "evidence_group_role",
            }
            existing = rows.get(evidence_id)
            if not existing:
                rows[evidence_id] = group_decision
            elif _group_decision_should_override(existing, group_decision):
                rows[evidence_id] = {
                    **group_decision,
                    "rationale": _combined_rationale(existing, group_decision),
                    "overrode_memo_inclusion": existing.get("memo_inclusion", ""),
                    "override_reason": "Evidence group role is more memo-diagnostic than row-level relevance.",
                }
    for disposition in _list(model.get("evidence_dispositions")):
        if not isinstance(disposition, dict):
            continue
        evidence_id = str(disposition.get("evidence_item_id") or "").strip()
        if evidence_id and evidence_id not in rows:
            rows[evidence_id] = {
                "evidence_item_id": evidence_id,
                "memo_inclusion": _memo_inclusion_from_disposition(disposition),
                "group_id": str(disposition.get("group_id") or "").strip(),
                "source_ids": [],
                "rationale": str(disposition.get("rationale") or "").strip(),
                "derived_from": "evidence_disposition",
            }
    return rows


def analyst_quantity_relevance_plan(model: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _list(model.get("quantity_relevance_decisions")):
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        value = str(row.get("quantity_value") or "").strip()
        inclusion = str(row.get("memo_inclusion") or "").strip()
        if evidence_id and value and inclusion:
            rows[(evidence_id, value)] = {
                "evidence_item_id": evidence_id,
                "quantity_value": value,
                "memo_inclusion": inclusion,
                "quantity_role": str(row.get("quantity_role") or "").strip(),
                "retention_phrase": str(row.get("retention_phrase") or "").strip(),
                "rationale": str(row.get("rationale") or "").strip(),
            }
    return rows


def serializable_quantity_relevance_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        f"{evidence_id}::{quantity_value}": decision
        for (evidence_id, quantity_value), decision in value.items()
        if isinstance(decision, dict)
    }


def unit_relevance_decisions(unit: dict[str, Any], *, semantic_context: dict[str, Any]) -> list[dict[str, Any]]:
    plan = _dict(semantic_context.get("analyst_relevance_plan"))
    rows = []
    for evidence_id in _string_list(_dict(unit.get("lineage")).get("covered_evidence_item_ids")):
        decision = _dict(plan.get(evidence_id))
        if decision:
            rows.append(decision)
    return rows


def combined_relevance_decision(evidence_ids: list[str], *, semantic_context: dict[str, Any]) -> dict[str, Any]:
    decisions = [
        _dict(_dict(semantic_context.get("analyst_relevance_plan")).get(evidence_id))
        for evidence_id in evidence_ids
    ]
    decisions = [decision for decision in decisions if decision]
    if not decisions:
        return {}
    priority = {"memo_spine": 0, "supporting_context": 1, "trace_only": 2, "exclude": 3}
    selected = sorted(decisions, key=lambda row: priority.get(str(row.get("memo_inclusion") or ""), 9))[0]
    rationales = _dedupe([str(row.get("rationale") or "").strip() for row in decisions if str(row.get("rationale") or "").strip()])
    return {
        **selected,
        "rationale": "; ".join(rationales[:3]) or selected.get("rationale", ""),
        "covered_decision_count": len(decisions),
    }


def _memo_inclusion_from_group(group: dict[str, Any]) -> str:
    role = str(group.get("memo_role") or "").strip()
    if role in {"load_bearing_primary_support", "load_bearing_counterweight", "quantitative_anchor", "decision_crux"}:
        return "memo_spine"
    if role in {"scope_or_applicability", "mechanism_or_context", "needs_human_or_model_review"}:
        return "supporting_context"
    return "trace_only"


def _memo_inclusion_from_disposition(disposition: dict[str, Any]) -> str:
    value = str(disposition.get("disposition") or "").strip()
    if value == "needs_review":
        return "supporting_context"
    if value == "not_decision_relevant":
        return "exclude"
    return "trace_only"


def _group_decision_should_override(existing: dict[str, Any], group_decision: dict[str, Any]) -> bool:
    current = str(existing.get("memo_inclusion") or "").strip()
    proposed = str(group_decision.get("memo_inclusion") or "").strip()
    if current == "exclude":
        return False
    return _memo_inclusion_priority(proposed) < _memo_inclusion_priority(current)


def _memo_inclusion_priority(value: str) -> int:
    return {
        "memo_spine": 0,
        "supporting_context": 1,
        "trace_only": 2,
        "exclude": 3,
    }.get(str(value or "").strip(), 9)


def _combined_rationale(existing: dict[str, Any], group_decision: dict[str, Any]) -> str:
    values = _dedupe(
        [
            str(group_decision.get("rationale") or "").strip(),
            str(existing.get("rationale") or "").strip(),
        ]
    )
    return "; ".join(value for value in values if value)
