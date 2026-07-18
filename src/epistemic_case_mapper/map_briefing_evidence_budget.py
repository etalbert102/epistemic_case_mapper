from __future__ import annotations

from collections import Counter
from typing import Any


FOREGROUND_MEMO_ROLES = {
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
    "mechanism_or_context",
}


def build_evidence_budget_bundle(*, analyst_decision_model: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    model = analyst_decision_model if isinstance(analyst_decision_model, dict) else {}
    ledger_rows = _ledger_rows_by_id(ledger)
    group_rows = [row for row in _list(model.get("evidence_groups")) if isinstance(row, dict)]
    disposition_rows = [row for row in _list(model.get("evidence_dispositions")) if isinstance(row, dict)]
    disposition_by_id = {
        str(row.get("evidence_item_id") or ""): row
        for row in disposition_rows
        if str(row.get("evidence_item_id") or "").strip()
    }
    group_by_evidence_id = _group_by_evidence_id(group_rows)
    budget_rows = []
    for evidence_id, ledger_row in ledger_rows.items():
        group = group_by_evidence_id.get(evidence_id, {})
        disposition = disposition_by_id.get(evidence_id, {})
        role = str(group.get("memo_role") or "")
        disposition_value = str(disposition.get("disposition") or "")
        budget_class = _budget_class(role=role, disposition=disposition_value)
        budget_rows.append(
            {
                "evidence_item_id": evidence_id,
                "source_ids": _list_text(ledger_row.get("source_ids")),
                "budget_class": budget_class,
                "memo_role": role,
                "disposition": disposition_value,
                "group_id": str(group.get("group_id") or disposition.get("group_id") or ""),
                "rationale": str(group.get("rationale") or disposition.get("rationale") or ""),
                "quantity_values": _list_text(ledger_row.get("quantity_values")),
            }
        )
    rows_by_class: dict[str, list[dict[str, Any]]] = {}
    for row in budget_rows:
        rows_by_class.setdefault(str(row["budget_class"]), []).append(row)
    foreground = rows_by_class.get("foreground", [])
    accounted_ids = {row["evidence_item_id"] for row in budget_rows if row["budget_class"] != "unaccounted"}
    evidence_universe = _evidence_universe(model=model, ledger_rows=ledger_rows, budget_rows=budget_rows)
    return {
        "evidence_universe": evidence_universe,
        "evidence_budget": {
            "schema_id": "evidence_budget_v1",
            "decision_question": str(ledger.get("decision_question") or model.get("decision_question") or ""),
            "foreground_evidence_item_ids": [row["evidence_item_id"] for row in foreground],
            "counterweight_evidence_item_ids": [row["evidence_item_id"] for row in rows_by_class.get("counterweight", [])],
            "scope_or_crux_evidence_item_ids": [
                row["evidence_item_id"]
                for row in [*rows_by_class.get("scope_or_crux", []), *rows_by_class.get("quantitative_anchor", [])]
            ],
            "appendix_or_background_evidence_item_ids": [
                row["evidence_item_id"]
                for row in [*rows_by_class.get("background", []), *rows_by_class.get("trace_only", [])]
            ],
            "routed_away_evidence_item_ids": _list_text(_dict(model.get("active_evidence_universe")).get("routed_away_evidence_item_ids")),
            "rows": budget_rows,
        },
        "evidence_accounting_report": {
            "schema_id": "evidence_accounting_report_v1",
            "status": "ready" if len(accounted_ids) == len(ledger_rows) else "warning",
            "ledger_row_count": len(ledger_rows),
            "accounted_evidence_item_count": len(accounted_ids),
            "unaccounted_evidence_item_ids": sorted(set(ledger_rows) - accounted_ids),
            "budget_class_counts": dict(Counter(row["budget_class"] for row in budget_rows)),
            "issues": [] if len(accounted_ids) == len(ledger_rows) else ["unaccounted_evidence_items"],
        },
        "foreground_evidence_report": {
            "schema_id": "foreground_evidence_report_v1",
            "status": "ready" if foreground else "warning",
            "foreground_count": len(foreground),
            "ledger_row_count": len(ledger_rows),
            "foreground_fraction": round(len(foreground) / len(ledger_rows), 4) if ledger_rows else 0.0,
            "foreground_evidence_item_ids": [row["evidence_item_id"] for row in foreground],
            "foreground_source_ids": sorted({source_id for row in foreground for source_id in row["source_ids"]}),
            "issues": [] if foreground else ["no_foreground_evidence"],
        },
        "active_cited_source_report": {
            "schema_id": "active_cited_source_report_v1",
            "active_source_ids": evidence_universe["active_source_ids"],
            "analyzed_source_ids": evidence_universe["analyzed_source_ids"],
            "foreground_source_ids": sorted({source_id for row in foreground for source_id in row["source_ids"]}),
            "source_count": len(evidence_universe["active_source_ids"]),
        },
        "source_dependency_report": {
            "schema_id": "source_dependency_report_v1",
            "status": "report_only",
            "method": "source_identity_accounting_without_semantic_independence_judgment",
            "source_ids": evidence_universe["active_source_ids"],
            "dependency_status": "unknown",
            "warnings": ["source_independence_not_semantically_adjudicated_here"],
        },
    }


def _evidence_universe(
    *,
    model: dict[str, Any],
    ledger_rows: dict[str, dict[str, Any]],
    budget_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    active = _dict(model.get("active_evidence_universe"))
    analyzed_sources = sorted({source_id for row in ledger_rows.values() for source_id in _list_text(row.get("source_ids"))})
    active_source_ids = sorted(
        set(_list_text(active.get("source_ids")))
        or {source_id for row in budget_rows if row["budget_class"] != "excluded" for source_id in row["source_ids"]}
    )
    return {
        "schema_id": "evidence_universe_v1",
        "decision_question": str(model.get("decision_question") or ""),
        "evidence_row_count": len(ledger_rows),
        "active_evidence_item_ids": _list_text(active.get("full_reasoning_evidence_item_ids")) or sorted(ledger_rows),
        "routed_away_evidence_item_ids": _list_text(active.get("routed_away_evidence_item_ids")),
        "analyzed_source_ids": analyzed_sources,
        "active_source_ids": active_source_ids,
        "omitted_source_ids": sorted(set(analyzed_sources) - set(active_source_ids)),
        "scope_status": "active_decision_model_universe",
    }


def _group_by_evidence_id(groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for group in groups:
        for evidence_id in _list_text(group.get("covered_evidence_item_ids")):
            out.setdefault(evidence_id, group)
    return out


def _budget_class(*, role: str, disposition: str) -> str:
    if disposition == "not_decision_relevant":
        return "excluded"
    if disposition in {"background", "covered_by_group"}:
        return "trace_only"
    if role == "load_bearing_counterweight":
        return "counterweight"
    if role == "quantitative_anchor":
        return "quantitative_anchor"
    if role in {"scope_or_applicability", "decision_crux"}:
        return "scope_or_crux"
    if role in FOREGROUND_MEMO_ROLES or disposition == "foreground":
        return "foreground"
    if disposition:
        return "background"
    return "unaccounted"


def _ledger_rows_by_id(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []
