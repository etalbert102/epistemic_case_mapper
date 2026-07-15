from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    first as _first,
    list_value as _list,
    string_list as _string_list,
)


def build_quantity_obligation_plan(
    report: dict[str, Any],
    *,
    analyst_quantity_relevance: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    analyst_quantity_relevance = analyst_quantity_relevance if isinstance(analyst_quantity_relevance, dict) else {}
    rows = [_quantity_plan_row(row, analyst_quantity_relevance) for row in _list(report.get("candidate_bindings")) if isinstance(row, dict)]
    rows.extend(_analyst_only_quantity_rows(rows, analyst_quantity_relevance))
    return {
        "schema_id": "quantity_obligation_plan_v1",
        "method": "reuse_analyst_decision_quantity_relevance_and_quantity_binding",
        "quantity_count": len(rows),
        "must_retain_count": sum(1 for row in rows if row.get("must_retain")),
        "rows": rows,
        "source_report_status": report.get("status", "missing") if isinstance(report, dict) else "missing",
    }


def quantity_plan_by_evidence_value(plan: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _list(plan.get("rows")):
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("source_evidence_item_id") or "").strip()
        value = str(row.get("value") or "").strip()
        if evidence_id and value:
            rows[(evidence_id, value)] = row
    return rows


def quantity_plan_for_unit(unit: dict[str, Any], *, semantic_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_key = _dict(semantic_context.get("quantity_plan_by_evidence_value"))
    rows: dict[str, dict[str, Any]] = {}
    for quantity in _list(unit.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        evidence_id = str(quantity.get("source_evidence_item_id") or "").strip()
        value = str(quantity.get("value") or "").strip()
        plan = by_key.get((evidence_id, value))
        if isinstance(plan, dict):
            rows[f"{evidence_id}::{value}"] = plan
    return rows


def quantity_plan_match(quantity: dict[str, Any], quantity_plan: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_id = str(quantity.get("source_evidence_item_id") or "").strip()
    value = str(quantity.get("value") or "").strip()
    return _dict(quantity_plan.get(f"{evidence_id}::{value}"))


def quantity_must_retain(plan: dict[str, Any]) -> bool:
    return bool(plan.get("must_retain"))


def quantity_fallback_requests(quantity_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in _list(quantity_plan.get("rows")) if isinstance(row, dict)]
    must = [row for row in rows if row.get("must_retain")]
    if rows and not must:
        return [
            {
                "request_type": "quantity_obligation_review",
                "reason": "quantity_binding_selected_no_memo_facing_quantities",
                "candidate_count": len(rows),
            }
        ]
    if len(must) > 24:
        return [
            {
                "request_type": "quantity_obligation_compression",
                "reason": "too_many_memo_facing_quantities",
                "must_retain_count": len(must),
            }
        ]
    return []


def _quantity_plan_row(row: dict[str, Any], analyst_quantity_relevance: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    analyst = _analyst_quantity_match(row, analyst_quantity_relevance)
    memo_use = str(row.get("memo_use") or "").strip()
    role = _quantity_role(row)
    must_retain = bool(row.get("must_retain")) if "must_retain" in row else memo_use == "yes" and role == "decision_anchor"
    if analyst:
        memo_use, role, must_retain = _apply_analyst_quantity_decision(analyst, memo_use=memo_use, role=role, must_retain=must_retain)
    return {
        "quantity_id": str(row.get("candidate_id") or "").strip(),
        "candidate_id": str(row.get("candidate_id") or "").strip(),
        "quantity_role": role,
        "must_retain": must_retain,
        "retention_phrase": str((analyst or {}).get("retention_phrase") or row.get("interpretation") or row.get("value") or "").strip(),
        "why_quantity_matters": str((analyst or {}).get("rationale") or row.get("rationale") or "").strip(),
        "demotion_reason": "" if must_retain else str((analyst or {}).get("rationale") or row.get("rationale") or "Not selected as a memo-facing quantity.").strip(),
        "source_label": _first(_string_list(row.get("source_labels"))),
        "source_labels": _string_list(row.get("source_labels")),
        "source_evidence_item_id": str(row.get("source_evidence_item_id") or "").strip(),
        "value": str(row.get("value") or "").strip(),
        "memo_use": memo_use,
        "binding_source": str(row.get("binding_source") or "").strip(),
        "analyst_quantity_relevance": analyst or {},
    }


def _apply_analyst_quantity_decision(analyst: dict[str, Any], *, memo_use: str, role: str, must_retain: bool) -> tuple[str, str, bool]:
    inclusion = str(analyst.get("memo_inclusion") or "").strip()
    if inclusion == "must_use":
        return "yes", str(analyst.get("quantity_role") or role or "decision_anchor"), True
    if inclusion == "supporting_context" and memo_use != "yes":
        return "context_only", str(analyst.get("quantity_role") or role or "supporting_detail"), False
    if inclusion in {"trace_only", "exclude"}:
        return "no", str(analyst.get("quantity_role") or "audit_only"), False
    return memo_use, role, must_retain


def _analyst_only_quantity_rows(
    existing_rows: list[dict[str, Any]],
    analyst_quantity_relevance: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    existing_keys = {
        (str(row.get("source_evidence_item_id") or ""), str(row.get("value") or ""))
        for row in existing_rows
    }
    rows = []
    for (evidence_id, value), analyst in analyst_quantity_relevance.items():
        if (evidence_id, value) in existing_keys:
            continue
        inclusion = str(analyst.get("memo_inclusion") or "")
        role = str(analyst.get("quantity_role") or "audit_only")
        must_retain = inclusion == "must_use"
        rows.append(
            {
                "quantity_id": f"analyst_decision_quantity::{evidence_id}::{_slug(value)}",
                "candidate_id": f"analyst_decision_quantity::{evidence_id}::{_slug(value)}",
                "quantity_role": role,
                "must_retain": must_retain,
                "retention_phrase": str(analyst.get("retention_phrase") or value).strip(),
                "why_quantity_matters": str(analyst.get("rationale") or "").strip(),
                "demotion_reason": "" if must_retain else str(analyst.get("rationale") or "Analyst marked this quantity trace-only.").strip(),
                "source_label": "",
                "source_labels": [],
                "source_evidence_item_id": evidence_id,
                "value": value,
                "memo_use": "yes" if must_retain else "context_only" if inclusion == "supporting_context" else "no",
                "binding_source": "analyst_decision_model",
                "analyst_quantity_relevance": analyst,
            }
        )
    return rows


def _analyst_quantity_match(row: dict[str, Any], analyst_quantity_relevance: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    evidence_id = str(row.get("source_evidence_item_id") or "").strip()
    value = str(row.get("value") or "").strip()
    if not evidence_id or not value:
        return {}
    direct = analyst_quantity_relevance.get((evidence_id, value))
    if isinstance(direct, dict):
        return direct
    normalized_value = _quantity_value_key(value)
    for (candidate_evidence_id, candidate_value), decision in analyst_quantity_relevance.items():
        if candidate_evidence_id == evidence_id and _quantity_value_key(candidate_value) == normalized_value:
            return decision if isinstance(decision, dict) else {}
    return {}


def _quantity_role(row: dict[str, Any]) -> str:
    existing = str(row.get("quantity_role") or "").strip()
    if existing in {"decision_anchor", "supporting_detail", "study_descriptor", "statistical_detail", "audit_only"}:
        return existing
    memo_role = str(row.get("memo_role") or "").strip()
    warnings = set(_string_list(row.get("deterministic_warnings")))
    value = str(row.get("value") or "").lower()
    if str(row.get("memo_use") or "") == "no":
        return "audit_only"
    if "p_value_not_effect_measure" in warnings or "heterogeneity_statistic_not_effect_measure" in warnings or "p" in value and _contains_stat_test(value):
        return "statistical_detail"
    if memo_role == "quantitative_anchor":
        return "decision_anchor"
    if str(row.get("memo_use") or "") == "yes":
        return "supporting_detail"
    return "audit_only" if str(row.get("memo_use") or "") == "no" else "study_descriptor"


def _contains_stat_test(value: str) -> bool:
    return "p=" in value or "p <" in value or "p>" in value


def _quantity_value_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return slug[:48] or "quantity"
