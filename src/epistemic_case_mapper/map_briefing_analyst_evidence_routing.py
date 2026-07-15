from __future__ import annotations

from collections import Counter
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)

FULL_DECISION_MODEL = "full_decision_model"
COMPACT_CONTEXT = "compact_context"
TRACE_ONLY = "trace_only"
OUT_OF_SCOPE = "out_of_scope"

FULL_MEMO_USES = {
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
    "needs_human_or_model_review",
}
CONTEXT_MEMO_USES = {"mechanism_or_context", "background_only"}
TRACE_MEMO_USES = {"covered_by_group"}
OUT_OF_SCOPE_MEMO_USES = {"not_decision_relevant"}

STRUCTURAL_FULL_ROLES = {
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
}


def build_analyst_evidence_routing_bundle(
    *,
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
    adjudication_report: dict[str, Any] | None = None,
    adjudication_parse_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routing = build_analyst_evidence_routing(
        ledger=ledger,
        adjudication=adjudication,
        adjudication_report=adjudication_report,
        adjudication_parse_report=adjudication_parse_report,
    )
    return {
        "analyst_evidence_routing": routing,
        "analyst_evidence_routing_report": build_analyst_evidence_routing_report(routing, ledger),
    }


def build_analyst_evidence_routing(
    *,
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
    adjudication_report: dict[str, Any] | None = None,
    adjudication_parse_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = []
    adjudication_by_id = _adjudication_by_id(adjudication)
    valid_adjudication = _adjudication_is_valid(adjudication_report, adjudication_parse_report)
    for ledger_row in _ledger_rows(ledger):
        evidence_id = str(ledger_row.get("evidence_item_id") or "").strip()
        if not evidence_id:
            continue
        adjudicated = adjudication_by_id.get(evidence_id, {})
        base_route, route_basis = _route_from_adjudication(adjudicated, valid_adjudication)
        route, guardrails = _apply_guardrails(base_route, ledger_row, adjudicated)
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": evidence_id,
                    "route": route,
                    "base_route": base_route,
                    "route_basis": route_basis,
                    "guardrail_escalations": guardrails,
                    "memo_use": adjudicated.get("memo_use"),
                    "answer_relation": adjudicated.get("answer_relation"),
                    "importance_rank": adjudicated.get("importance_rank"),
                    "risk_if_omitted": _risk_if_omitted(route, ledger_row, adjudicated, guardrails),
                    "rationale": _routing_rationale(route, ledger_row, adjudicated, guardrails),
                    "source_ids": _string_list(ledger_row.get("source_ids"))[:4],
                    "quantity_values": _string_list(ledger_row.get("quantity_values"))[:6],
                }
            )
        )
    return {
        "schema_id": "analyst_evidence_routing_v1",
        "decision_question": str(ledger.get("decision_question") or "").strip(),
        "method": "analyst_adjudication_routes_with_deterministic_guardrail_escalation",
        "adjudication_status": _adjudication_status(adjudication_report, adjudication_parse_report),
        "rows": rows,
    }


def build_analyst_evidence_routing_report(routing: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in _list(routing.get("rows")) if isinstance(row, dict)]
    ledger_ids = _ledger_ids(ledger)
    routed_ids = [str(row.get("evidence_item_id") or "") for row in rows if str(row.get("evidence_item_id") or "").strip()]
    missing = sorted(set(ledger_ids) - set(routed_ids))
    unknown = sorted(set(routed_ids) - set(ledger_ids))
    route_counts = Counter(str(row.get("route") or "unknown") for row in rows)
    guardrail_count = sum(1 for row in rows if _list(row.get("guardrail_escalations")))
    full_count = route_counts.get(FULL_DECISION_MODEL, 0)
    issues = [
        *(["missing_routing_rows"] if missing else []),
        *(["unknown_routing_rows"] if unknown else []),
        *(["no_full_decision_model_rows"] if rows and full_count == 0 else []),
    ]
    return {
        "schema_id": "analyst_evidence_routing_report_v1",
        "status": "ready" if not issues else "warning",
        "valid": not missing and not unknown and bool(rows),
        "ledger_row_count": len(ledger_ids),
        "routed_row_count": len(rows),
        "full_decision_model_row_count": full_count,
        "routed_away_row_count": max(0, len(rows) - full_count),
        "route_counts": dict(route_counts),
        "guardrail_escalation_count": guardrail_count,
        "missing_evidence_item_ids": missing,
        "unknown_evidence_item_ids": unknown,
        "issues": issues,
    }


def routing_by_evidence_id(routing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(routing.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def routed_away_rows(routing: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _list(routing.get("rows"))
        if isinstance(row, dict) and str(row.get("route") or "") != FULL_DECISION_MODEL
    ]


def apply_routed_away_accounting(model: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(model, dict):
        return model
    routed = routed_away_rows(_dict(context.get("analyst_evidence_routing")))
    if not routed:
        return model
    updated = dict(model)
    groups = [dict(group) for group in _list(updated.get("evidence_groups")) if isinstance(group, dict)]
    covered = {
        evidence_id
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    disposition_by_id = {
        str(row.get("evidence_item_id") or ""): dict(row)
        for row in _list(updated.get("evidence_dispositions"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    memo_by_id = {
        str(row.get("evidence_item_id") or ""): dict(row)
        for row in _list(updated.get("memo_relevance_decisions"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    for route_row in routed:
        evidence_id = str(route_row.get("evidence_item_id") or "").strip()
        if not evidence_id or evidence_id in covered:
            continue
        disposition_by_id.setdefault(evidence_id, _routed_disposition(route_row))
        memo_by_id.setdefault(evidence_id, _routed_memo_relevance(route_row))
    updated["evidence_dispositions"] = list(disposition_by_id.values())
    updated["memo_relevance_decisions"] = list(memo_by_id.values())
    return updated


def compact_routed_away_summary(all_rows: list[dict[str, Any]], routing: dict[str, Any]) -> list[dict[str, Any]]:
    row_by_id = {str(row.get("evidence_item_id") or ""): row for row in all_rows}
    summary = []
    for route_row in routed_away_rows(routing):
        evidence_id = str(route_row.get("evidence_item_id") or "").strip()
        ledger_row = row_by_id.get(evidence_id, {})
        summary.append(
            _drop_empty(
                {
                    "evidence_item_id": evidence_id,
                    "route": route_row.get("route"),
                    "memo_use": route_row.get("memo_use"),
                    "answer_relation": route_row.get("answer_relation"),
                    "claim": _short_text(str(ledger_row.get("claim") or ""), 220),
                    "rationale": _short_text(str(route_row.get("rationale") or ""), 180),
                    "risk_if_omitted": _short_text(str(route_row.get("risk_if_omitted") or ""), 180),
                    "source_ids": _string_list(ledger_row.get("source_ids"))[:4],
                    "quantity_values": _string_list(ledger_row.get("quantity_values"))[:4],
                }
            )
        )
    return summary


def _route_from_adjudication(adjudicated: dict[str, Any], valid_adjudication: bool) -> tuple[str, str]:
    if not valid_adjudication and not adjudicated:
        return FULL_DECISION_MODEL, "missing_or_invalid_adjudication"
    memo_use = str(adjudicated.get("memo_use") or "").strip()
    if memo_use in FULL_MEMO_USES:
        return FULL_DECISION_MODEL, "analyst_memo_use"
    if memo_use in CONTEXT_MEMO_USES:
        return COMPACT_CONTEXT, "analyst_memo_use"
    if memo_use in TRACE_MEMO_USES:
        return TRACE_ONLY, "analyst_memo_use"
    if memo_use in OUT_OF_SCOPE_MEMO_USES:
        return OUT_OF_SCOPE, "analyst_memo_use"
    return FULL_DECISION_MODEL, "unknown_or_unset_memo_use"


def _apply_guardrails(base_route: str, ledger_row: dict[str, Any], adjudicated: dict[str, Any]) -> tuple[str, list[str]]:
    guardrails: list[str] = []
    if base_route == FULL_DECISION_MODEL:
        return base_route, guardrails
    current_role = str(ledger_row.get("current_role") or "").strip()
    if current_role in STRUCTURAL_FULL_ROLES:
        guardrails.append("ledger_current_role_is_decision_bearing")
    if _string_list(ledger_row.get("quantity_values")) and str(adjudicated.get("memo_use") or "") != "not_decision_relevant":
        guardrails.append("row_has_quantities")
    if str(ledger_row.get("input_kind") or "") == "candidate_decision_edge" and base_route != OUT_OF_SCOPE:
        guardrails.append("candidate_decision_edge_needs_global_check")
    return (FULL_DECISION_MODEL, guardrails) if guardrails else (base_route, guardrails)


def _risk_if_omitted(route: str, ledger_row: dict[str, Any], adjudicated: dict[str, Any], guardrails: list[str]) -> str:
    if route == FULL_DECISION_MODEL:
        if guardrails:
            return "Structural guardrails escalated this row so the global decision model can judge it directly."
        return "Omitting this row could remove load-bearing decision evidence."
    memo_use = str(adjudicated.get("memo_use") or "")
    if route == COMPACT_CONTEXT:
        return "Memo may lose useful context, but the row is not expected to change the decision model directly."
    if route == TRACE_ONLY:
        covered_by = _string_list(adjudicated.get("covered_by"))
        return "Row is routed to audit trace because it is covered by another row." + (f" Covered by: {', '.join(covered_by)}." if covered_by else "")
    if route == OUT_OF_SCOPE:
        return str(adjudicated.get("downgrade_reason") or "Analyst adjudication judged the row outside the decision question.")
    return f"Routed from memo_use={memo_use or 'unset'}."


def _routing_rationale(route: str, ledger_row: dict[str, Any], adjudicated: dict[str, Any], guardrails: list[str]) -> str:
    if guardrails:
        return f"Escalated to full decision model because {', '.join(guardrails)}."
    if adjudicated.get("rationale"):
        return str(adjudicated.get("rationale"))
    if route == FULL_DECISION_MODEL:
        return "Needs global decision-model reasoning."
    return str(ledger_row.get("why_it_matters") or "Routed by analyst adjudication.")


def _routed_disposition(route_row: dict[str, Any]) -> dict[str, Any]:
    route = str(route_row.get("route") or "")
    disposition = {
        COMPACT_CONTEXT: "background",
        TRACE_ONLY: "covered_by_group",
        OUT_OF_SCOPE: "not_decision_relevant",
    }.get(route, "needs_review")
    return {
        "evidence_item_id": str(route_row.get("evidence_item_id") or ""),
        "disposition": disposition,
        "group_id": "",
        "rationale": _short_text(str(route_row.get("rationale") or route_row.get("risk_if_omitted") or "Routed outside full decision-model reasoning."), 360),
    }


def _routed_memo_relevance(route_row: dict[str, Any]) -> dict[str, Any]:
    route = str(route_row.get("route") or "")
    inclusion = {
        COMPACT_CONTEXT: "supporting_context",
        TRACE_ONLY: "trace_only",
        OUT_OF_SCOPE: "exclude",
    }.get(route, "trace_only")
    return {
        "evidence_item_id": str(route_row.get("evidence_item_id") or ""),
        "memo_inclusion": inclusion,
        "group_id": "",
        "source_ids": _string_list(route_row.get("source_ids")),
        "rationale": _short_text(str(route_row.get("rationale") or route_row.get("risk_if_omitted") or "Routed outside full decision-model reasoning."), 360),
    }


def _adjudication_by_id(adjudication: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(_dict(adjudication).get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _adjudication_is_valid(adjudication_report: dict[str, Any] | None, adjudication_parse_report: dict[str, Any] | None) -> bool:
    report = adjudication_report if isinstance(adjudication_report, dict) else {}
    parse = adjudication_parse_report if isinstance(adjudication_parse_report, dict) else {}
    if report:
        return bool(report.get("accepted")) or str(report.get("status") or "") == "prompt_backend_scaffold"
    if parse:
        return bool(parse.get("valid"))
    return True


def _adjudication_status(adjudication_report: dict[str, Any] | None, adjudication_parse_report: dict[str, Any] | None) -> str:
    report = adjudication_report if isinstance(adjudication_report, dict) else {}
    parse = adjudication_parse_report if isinstance(adjudication_parse_report, dict) else {}
    if report.get("status"):
        return str(report.get("status"))
    if parse.get("status"):
        return str(parse.get("status"))
    return "not_reported"


def _ledger_rows(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(_dict(ledger).get("rows")) if isinstance(row, dict)]


def _ledger_ids(ledger: dict[str, Any]) -> list[str]:
    return _dedupe([str(row.get("evidence_item_id") or "") for row in _ledger_rows(ledger) if str(row.get("evidence_item_id") or "").strip()])


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
