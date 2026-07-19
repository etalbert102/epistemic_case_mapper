from __future__ import annotations

from collections import Counter
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


FOREGROUND_GROUP_ROLES = {
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
    "mechanism_or_context",
}

DOWNGRADED_DISPOSITIONS = {
    "background",
    "not_decision_relevant",
    "covered_by_group",
    "needs_review",
}


def build_global_decision_model_bundle(
    *,
    ledger: dict[str, Any],
    analyst_decision_model: dict[str, Any],
    analyst_decision_model_report: dict[str, Any] | None = None,
    analyst_decision_model_parse_report: dict[str, Any] | None = None,
    parallel_report: dict[str, Any] | None = None,
    evidence_routing_report: dict[str, Any] | None = None,
    deferred_evidence_audit: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    model = build_global_decision_model(
        ledger=ledger,
        analyst_decision_model=analyst_decision_model,
        analyst_decision_model_report=analyst_decision_model_report or {},
        analyst_decision_model_parse_report=analyst_decision_model_parse_report or {},
        parallel_report=parallel_report or {},
        evidence_routing_report=evidence_routing_report or {},
        deferred_evidence_audit=deferred_evidence_audit or {},
    )
    report = build_global_decision_model_report(model)
    return {
        "global_decision_model": model,
        "global_decision_model_report": report,
        "global_decision_model_reconciliation_report": model["reconciliation"],
        "global_decision_model_failure_accounting": model["failure_accounting"],
    }


def build_global_decision_model(
    *,
    ledger: dict[str, Any],
    analyst_decision_model: dict[str, Any],
    analyst_decision_model_report: dict[str, Any],
    analyst_decision_model_parse_report: dict[str, Any],
    parallel_report: dict[str, Any],
    evidence_routing_report: dict[str, Any],
    deferred_evidence_audit: dict[str, Any],
) -> dict[str, Any]:
    groups = _sorted_groups(analyst_decision_model)
    evidence_accounting = _evidence_accounting(ledger, analyst_decision_model, analyst_decision_model_parse_report)
    failure_accounting = _failure_accounting(analyst_decision_model_report, parallel_report)
    routing_accounting = _routing_accounting(evidence_routing_report, deferred_evidence_audit)
    return {
        "schema_id": "global_decision_model_v1",
        "method": "side_by_side_projection_from_analyst_decision_model",
        "decision_question": str(ledger.get("decision_question") or analyst_decision_model.get("decision_question") or "").strip(),
        "bounded_answer": _bounded_answer(analyst_decision_model),
        "confidence": str(analyst_decision_model.get("confidence") or "not_specified"),
        "confidence_reasons": _confidence_reasons(analyst_decision_model),
        "strongest_support": _groups_for_roles(groups, {"load_bearing_primary_support", "quantitative_anchor"}),
        "strongest_counterargument": _groups_for_roles(groups, {"load_bearing_counterweight"}),
        "scope_boundaries": _groups_for_roles(groups, {"scope_or_applicability"}),
        "decision_cruxes": _groups_for_roles(groups, {"decision_crux"}),
        "contextual_evidence": _groups_for_roles(groups, {"mechanism_or_context", "background_only", "needs_human_or_model_review"}),
        "quantitative_anchors": _dedupe(_string_list(analyst_decision_model.get("quantitative_anchors")) + _group_quantities(groups)),
        "missing_evidence": _string_list(analyst_decision_model.get("what_would_change_the_answer")),
        "uncertainty_drivers": _uncertainty_drivers(groups, analyst_decision_model),
        "argument_plan": _list(analyst_decision_model.get("argument_plan")),
        "decision_logic": _dict(analyst_decision_model.get("decision_logic")),
        "source_hierarchy": _dict(analyst_decision_model.get("source_hierarchy")),
        "source_hierarchy_report": _dict(analyst_decision_model.get("source_hierarchy_report")),
        "source_weight_judgments": _list(analyst_decision_model.get("source_weight_judgments")),
        "source_weight_judgment_report": _dict(analyst_decision_model.get("source_weight_judgment_report")),
        "evidence_accounting": evidence_accounting,
        "routing_accounting": routing_accounting,
        "failure_accounting": failure_accounting,
        "reconciliation": _reconciliation(evidence_accounting, failure_accounting, routing_accounting),
        "projection_source": {
            "artifact": "analyst_decision_model",
            "source_status": analyst_decision_model_report.get("status", "unknown"),
            "parse_status": analyst_decision_model_parse_report.get("status", "unknown"),
        },
    }


def build_global_decision_model_report(model: dict[str, Any]) -> dict[str, Any]:
    reconciliation = _dict(model.get("reconciliation"))
    issues = _string_list(reconciliation.get("issues"))
    return {
        "schema_id": "global_decision_model_report_v1",
        "status": "ready" if not issues else "ready_with_warnings",
        "method": model.get("method", ""),
        "issue_count": len(issues),
        "issues": issues,
        "ledger_row_count": _dict(model.get("evidence_accounting")).get("ledger_row_count", 0),
        "covered_evidence_item_count": len(_string_list(_dict(model.get("evidence_accounting")).get("covered_evidence_item_ids"))),
        "missing_evidence_item_count": len(_string_list(_dict(model.get("evidence_accounting")).get("missing_accounting_ids"))),
        "coverage_qualified": bool(reconciliation.get("coverage_qualified")),
        "failure_count": _dict(model.get("failure_accounting")).get("failed_count", 0),
        "deferred_count": _dict(model.get("routing_accounting")).get("deferred_count", 0),
        "excluded_count": _dict(model.get("routing_accounting")).get("excluded_count", 0),
        "side_by_side_note": "Projection runs beside the current analyst decision model and does not replace synthesis ownership yet.",
    }


def _sorted_groups(model: dict[str, Any]) -> list[dict[str, Any]]:
    groups = [dict(group) for group in _list(model.get("evidence_groups")) if isinstance(group, dict)]
    return sorted(groups, key=lambda group: (_rank(group), str(group.get("group_id") or "")))


def _rank(group: dict[str, Any]) -> int:
    try:
        return int(group.get("importance_rank", 100) or 100)
    except (TypeError, ValueError):
        return 100


def _groups_for_roles(groups: list[dict[str, Any]], roles: set[str]) -> list[dict[str, Any]]:
    return [_compact_group(group) for group in groups if str(group.get("memo_role") or "") in roles]


def _compact_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "group_id": str(group.get("group_id") or ""),
        "proposition": str(group.get("proposition") or "").strip(),
        "memo_role": str(group.get("memo_role") or "").strip(),
        "importance_rank": _rank(group),
        "covered_evidence_item_ids": _string_list(group.get("covered_evidence_item_ids")),
        "rationale": str(group.get("rationale") or "").strip(),
        "evidence_strength": str(group.get("evidence_strength") or "").strip(),
        "answer_impact": str(group.get("answer_impact") or "").strip(),
        "uncertainty_type": str(group.get("uncertainty_type") or "").strip(),
        "applicability_limits": _string_list(group.get("applicability_limits")),
        "conflict_note": str(group.get("conflict_note") or "").strip(),
    }


def _bounded_answer(model: dict[str, Any]) -> str:
    decision_logic = _dict(model.get("decision_logic"))
    return str(decision_logic.get("bounded_bottom_line") or model.get("direct_answer") or "").strip()


def _confidence_reasons(model: dict[str, Any]) -> list[str]:
    reasons = [
        str(model.get("overall_rationale") or "").strip(),
        str(_dict(model.get("decision_logic")).get("support_summary") or "").strip(),
        str(_dict(model.get("decision_logic")).get("counterweight_weighting") or "").strip(),
    ]
    return [reason for reason in _dedupe(reasons) if reason]


def _group_quantities(groups: list[dict[str, Any]]) -> list[str]:
    return [
        quantity
        for group in groups
        for quantity in _string_list(group.get("quantity_values"))
    ]


def _uncertainty_drivers(groups: list[dict[str, Any]], model: dict[str, Any]) -> list[str]:
    drivers = [
        str(group.get("uncertainty_type") or "").strip()
        for group in groups
        if str(group.get("uncertainty_type") or "").strip()
    ]
    drivers.extend(_string_list(_dict(model.get("decision_logic")).get("do_not_overstate")))
    return _dedupe(drivers)


def _evidence_accounting(
    ledger: dict[str, Any],
    model: dict[str, Any],
    parse_report: dict[str, Any],
) -> dict[str, Any]:
    ledger_ids = _ledger_ids(ledger)
    covered_ids = _covered_ids(model)
    disposition_rows = _disposition_rows(model)
    disposition_ids = sorted(disposition_rows)
    accounted_ids = sorted(set(covered_ids) | set(disposition_ids))
    downgraded_ids = sorted(
        evidence_id
        for evidence_id, row in disposition_rows.items()
        if str(row.get("disposition") or "") in DOWNGRADED_DISPOSITIONS
    )
    foreground_ids = sorted(
        evidence_id
        for evidence_id, row in disposition_rows.items()
        if str(row.get("disposition") or "") == "foreground"
    )
    reported_missing_ids = _string_list(parse_report.get("missing_accounting_ids"))
    actual_missing_ids = sorted(set(ledger_ids) - set(accounted_ids))
    return {
        "schema_id": "global_decision_model_evidence_accounting_v1",
        "ledger_row_count": len(ledger_ids),
        "ledger_evidence_item_ids": ledger_ids,
        "covered_evidence_item_ids": covered_ids,
        "covered_role_counts": _covered_role_counts(model),
        "foreground_disposition_ids": foreground_ids,
        "downgraded_or_background_evidence_item_ids": downgraded_ids,
        "accounted_evidence_item_ids": accounted_ids,
        "missing_accounting_ids": actual_missing_ids,
        "reported_missing_accounting_ids": reported_missing_ids,
        "obligation_omissions": _dict(parse_report.get("obligation_omissions")),
    }


def _failure_accounting(report: dict[str, Any], parallel_report: dict[str, Any]) -> dict[str, Any]:
    task_reports = [row for row in _list(parallel_report.get("task_reports")) if isinstance(row, dict)]
    failed_tasks = [row for row in task_reports if row.get("status") != "parsed"]
    failed_ids = [str(row.get("task_id") or "") for row in failed_tasks if str(row.get("task_id") or "").strip()]
    failed_count = _int_value(parallel_report.get("failed_count"), len(failed_tasks))
    return {
        "schema_id": "global_decision_model_failure_accounting_v1",
        "semantic_owner_status": str(report.get("status") or "unknown"),
        "parallel_task_count": _int_value(parallel_report.get("task_count"), len(task_reports)),
        "parallel_parsed_count": _int_value(parallel_report.get("parsed_count"), 0),
        "failed_count": failed_count,
        "failed_task_ids": failed_ids,
        "failed_task_issues": _failed_task_issues(failed_tasks),
        "coverage_qualified": failed_count > 0 or "scaffold" in str(report.get("status") or ""),
    }


def _routing_accounting(routing_report: dict[str, Any], deferred_audit: dict[str, Any]) -> dict[str, Any]:
    counts = _dict(routing_report.get("routing_counts"))
    return {
        "schema_id": "global_decision_model_routing_accounting_v1",
        "included_count": _int_value(counts.get("include"), 0),
        "deferred_count": _int_value(counts.get("defer"), _list_count(deferred_audit.get("deferred_evidence_unit_ids"))),
        "appendix_count": _int_value(counts.get("appendix"), 0),
        "excluded_count": _int_value(counts.get("exclude"), 0),
        "deferred_evidence_unit_ids": _string_list(deferred_audit.get("deferred_evidence_unit_ids")),
        "deferred_reasons": _list(deferred_audit.get("deferred_reasons")),
    }


def _reconciliation(
    evidence_accounting: dict[str, Any],
    failure_accounting: dict[str, Any],
    routing_accounting: dict[str, Any],
) -> dict[str, Any]:
    issues = []
    if _string_list(evidence_accounting.get("missing_accounting_ids")):
        issues.append("missing_evidence_accounting")
    if failure_accounting.get("failed_count", 0):
        issues.append("partial_semantic_owner_failure")
    if bool(failure_accounting.get("coverage_qualified")):
        issues.append("coverage_qualified_by_model_failure_or_scaffold")
    if _has_obligation_omissions(evidence_accounting):
        issues.append("retention_obligations_not_fully_grouped")
    if routing_accounting.get("deferred_count", 0):
        issues.append("deferred_evidence_not_in_global_model")
    return {
        "schema_id": "global_decision_model_reconciliation_report_v1",
        "status": "ready" if not issues else "warning",
        "coverage_qualified": bool(failure_accounting.get("coverage_qualified")),
        "issues": issues,
        "role_counts": _role_counts(evidence_accounting),
    }


def _role_counts(evidence_accounting: dict[str, Any]) -> dict[str, int]:
    counts = _dict(evidence_accounting.get("covered_role_counts"))
    return {str(key): _int_value(value, 0) for key, value in counts.items()}


def _has_obligation_omissions(accounting: dict[str, Any]) -> bool:
    omissions = _dict(accounting.get("obligation_omissions"))
    return any(_string_list(value) for value in omissions.values())


def _ledger_ids(ledger: dict[str, Any]) -> list[str]:
    return [
        str(row.get("evidence_item_id") or "").strip()
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    ]


def _covered_ids(model: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            evidence_id
            for group in _list(model.get("evidence_groups"))
            if isinstance(group, dict)
            for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
        ]
    )


def _covered_role_counts(model: dict[str, Any]) -> dict[str, int]:
    return dict(
        Counter(
            str(group.get("memo_role") or "unknown")
            for group in _list(model.get("evidence_groups"))
            if isinstance(group, dict) and _string_list(group.get("covered_evidence_item_ids"))
        )
    )


def _disposition_rows(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_item_id") or "").strip(): dict(row)
        for row in _list(model.get("evidence_dispositions"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _failed_task_issues(task_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "task_id": row.get("task_id"),
            "status": row.get("status"),
            "issues": _string_list(row.get("issues")),
        }
        for row in task_reports
    ]


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list_count(value: Any) -> int:
    return len(_list(value))
