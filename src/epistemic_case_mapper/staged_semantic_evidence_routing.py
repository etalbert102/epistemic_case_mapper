from __future__ import annotations

from typing import Any

ROUTING_SCHEMA_ID = "evidence_relevance_ledger_v1"
ROUTING_REPORT_SCHEMA_ID = "evidence_routing_report_v1"
DEFERRED_AUDIT_SCHEMA_ID = "deferred_evidence_audit_v1"


def build_evidence_unit_routing(
    evidence_units: list[dict[str, Any]],
    *,
    decision_question: str,
    source_ids: list[str],
) -> dict[str, Any]:
    rows = [_routing_row(unit, decision_question=decision_question) for unit in evidence_units if isinstance(unit, dict)]
    report = _routing_report(rows, source_ids=source_ids)
    return {
        "evidence_relevance_ledger": {
            "schema_id": ROUTING_SCHEMA_ID,
            "decision_question": decision_question,
            "row_count": len(rows),
            "rows": rows,
        },
        "evidence_routing_report": report,
        "deferred_evidence_audit": {
            "schema_id": DEFERRED_AUDIT_SCHEMA_ID,
            "decision_question": decision_question,
            "deferred_count": sum(1 for row in rows if row["routing_decision"] == "defer"),
            "appendix_count": sum(1 for row in rows if row["routing_decision"] == "appendix"),
            "excluded_count": sum(1 for row in rows if row["routing_decision"] == "exclude"),
            "rows": [
                row
                for row in rows
                if row["routing_decision"] in {"defer", "appendix", "exclude"}
            ],
        },
    }


def _routing_row(unit: dict[str, Any], *, decision_question: str) -> dict[str, Any]:
    relevance = str(unit.get("question_relevance") or "").strip().lower()
    decision = _routing_decision(relevance)
    return {
        "unit_id": str(unit.get("unit_id") or ""),
        "source_id": str(unit.get("source_id") or ""),
        "routing_decision": decision,
        "decision_facet": _decision_facet(relevance),
        "model_relevance_label": relevance or "unspecified",
        "model_importance_label": str(unit.get("decision_importance") or "").strip().lower() or "unspecified",
        "model_rationale": str(unit.get("why_it_matters") or "").strip(),
        "proposition": str(unit.get("proposition") or "").strip(),
        "source_span": str(unit.get("source_span") or "").strip(),
        "warnings": _string_list(unit.get("warnings")),
        "decision_question": decision_question,
        "routing_basis": "model_extraction_labels_schema_projected",
        "blocking": False,
    }


def _routing_decision(relevance: str) -> str:
    if relevance in {"direct", "scope_limit"}:
        return "include"
    if relevance == "indirect":
        return "defer"
    if relevance == "background":
        return "appendix"
    if relevance == "irrelevant":
        return "exclude"
    return "defer"


def _decision_facet(relevance: str) -> str:
    if relevance == "direct":
        return "answer_bearing"
    if relevance == "scope_limit":
        return "scope_boundary"
    if relevance == "indirect":
        return "possible_crux_or_context"
    if relevance == "background":
        return "background_context"
    if relevance == "irrelevant":
        return "off_question"
    return "needs_review"


def _routing_report(rows: list[dict[str, Any]], *, source_ids: list[str]) -> dict[str, Any]:
    counts = _decision_counts(rows)
    represented_sources = {row["source_id"] for row in rows if row["routing_decision"] == "include"}
    all_sources = [source_id for source_id in source_ids if source_id]
    return {
        "schema_id": ROUTING_REPORT_SCHEMA_ID,
        "status": "ready" if rows else "warning",
        "row_count": len(rows),
        "routing_counts": counts,
        "source_count": len(all_sources),
        "represented_source_count": len(represented_sources),
        "source_coverage": [
            {
                "source_id": source_id,
                "coverage_status": _source_coverage_status(source_id, rows),
            }
            for source_id in all_sources
        ],
        "issues": [] if rows else ["no_evidence_units_to_route"],
    }


def _decision_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        decision = str(row.get("routing_decision") or "unknown")
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def _source_coverage_status(source_id: str, rows: list[dict[str, Any]]) -> str:
    source_rows = [row for row in rows if row.get("source_id") == source_id]
    if not source_rows:
        return "no_evidence_units"
    decisions = {str(row.get("routing_decision") or "") for row in source_rows}
    if "include" in decisions:
        return "represented"
    if "defer" in decisions:
        return "deferred"
    if "appendix" in decisions:
        return "appendix_only"
    if "exclude" in decisions:
        return "excluded"
    return "unknown"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []
