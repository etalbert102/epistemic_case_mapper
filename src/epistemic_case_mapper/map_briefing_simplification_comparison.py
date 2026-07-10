from __future__ import annotations

from typing import Any


def build_pipeline_simplification_comparison(
    *,
    scaffold: dict[str, Any],
    final_outputs: dict[str, Any],
    briefing_path: str,
    evidence_appendix_path: str,
) -> dict[str, Any]:
    diagnostics = _dict(final_outputs.get("diagnostics"))
    rewrite_report = _dict(_dict(final_outputs.get("rewrite_result")).get("report"))
    packet = _active_memo_ready_packet(scaffold)
    evidence_items = _list(packet.get("evidence_items"))
    mandatory_items = [item for item in evidence_items if isinstance(item, dict) and item.get("must_use")]
    warnings = _known_weaknesses(scaffold=scaffold, diagnostics=diagnostics, rewrite_report=rewrite_report)
    active_packet_report = _dict(scaffold.get("active_memo_ready_packet_report"))
    return {
        "schema_id": "pipeline_simplification_comparison_v1",
        "status": "warning" if warnings else "ready_for_review",
        "synthesis_path": _synthesis_path(rewrite_report, active_packet_report),
        "active_packet_report": active_packet_report,
        "reader_artifacts": {
            "briefing_path": briefing_path,
            "evidence_appendix_path": evidence_appendix_path,
        },
        "retention_metrics": _retention_metrics(_dict(diagnostics.get("packet_retention"))),
        "source_lineage_metrics": _source_lineage_metrics(_dict(diagnostics.get("source_lineage"))),
        "assembly_audit_summary": _assembly_audit_summary(_dict(scaffold.get("packet_assembly_audit"))),
        "role_assignment_summary": _role_assignment_summary(_dict(scaffold.get("packet_role_assignment_report"))),
        "quantity_binding_summary": _quantity_binding_summary(_dict(scaffold.get("quantity_binding_report"))),
        "diagnosticity_summary": _diagnosticity_summary(_dict(scaffold.get("diagnosticity_matrix"))),
        "evidence_profile_and_warrant_coverage": _profile_warrant_coverage(mandatory_items),
        "provenance_lineage_completeness": _lineage_completeness(mandatory_items),
        "packet_quality_report": _packet_quality_summary(_dict(scaffold.get("memo_ready_packet_quality_report"))),
        "runtime_model_call_summary": _runtime_summary(_dict(diagnostics.get("runtime_budget"))),
        "manual_memo_quality_read": _manual_review_placeholder(diagnostics, rewrite_report),
        "remaining_known_weaknesses": warnings,
        "retained_legacy_compatibility_paths": _retained_legacy_paths(final_outputs),
    }


def _retention_metrics(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status", "missing"),
        "must_retain_count": _int(report.get("must_retain_count") or report.get("mandatory_item_count")),
        "retained_must_retain_count": _int(report.get("retained_must_retain_count") or report.get("retained_mandatory_count")),
        "missing_critical_count": _int(report.get("missing_critical_count") or report.get("missing_mandatory_count")),
        "missing_quantity_count": _int(report.get("missing_quantity_count")),
    }


def _active_memo_ready_packet(scaffold: dict[str, Any]) -> dict[str, Any]:
    analyst = _dict(scaffold.get("analyst_memo_ready_packet"))
    if analyst.get("evidence_items"):
        return analyst
    return _dict(scaffold.get("memo_ready_packet"))


def _synthesis_path(rewrite_report: dict[str, Any], active_packet_report: dict[str, Any]) -> str:
    if rewrite_report.get("analyst_memo_ready_packet_path") or active_packet_report.get("active_packet") == "analyst_memo_ready_packet":
        return "analyst_memo_ready_packet"
    if rewrite_report.get("memo_ready_packet_path"):
        return "memo_ready_packet"
    return "legacy_compatibility"


def _source_lineage_metrics(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status", "missing"),
        "matched_source_count": _int(report.get("matched_source_count")),
        "expected_source_count": _int(report.get("expected_source_count")),
        "unmatched_source_count": _int(report.get("unmatched_source_count")),
    }


def _assembly_audit_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status", "missing"),
        "dropped_claim_count": _list_len(report.get("dropped_claims")),
        "merged_claim_count": _list_len(report.get("merged_claims")),
        "kept_separate_near_duplicate_count": _list_len(report.get("kept_separate_near_duplicates")),
        "uncertain_role_count": _list_len(report.get("uncertain_role_assignments")),
        "provenance_warning_count": _list_len(report.get("provenance_warnings")),
    }


def _role_assignment_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status", "missing"),
        "assigned_role_count": _list_len(report.get("role_assignments")),
        "uncertain_role_count": _list_len(report.get("uncertain_role_assignments")),
        "warning_count": _list_len(report.get("warnings")),
    }


def _quantity_binding_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status", "missing"),
        "bound_quantity_group_count": _int(report.get("bound_quantity_group_count")),
        "unbound_quantity_group_count": _int(report.get("unbound_quantity_group_count")),
        "mandatory_unbound_quantity_count": _int(report.get("mandatory_unbound_quantity_count")),
    }


def _diagnosticity_summary(report: dict[str, Any]) -> dict[str, Any]:
    hypotheses = _list(report.get("live_hypotheses"))
    rows = _list(report.get("evidence_diagnosticity"))
    return {
        "status": report.get("status", "missing"),
        "live_hypothesis_count": len(hypotheses),
        "scored_evidence_count": len(rows),
        "high_diagnosticity_count": sum(1 for row in rows if isinstance(row, dict) and str(row.get("diagnosticity", "")).lower() == "high"),
    }


def _profile_warrant_coverage(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    with_profile = sum(1 for item in items if _dict(item.get("evidence_profile")))
    with_warrant = sum(1 for item in items if str(_dict(item.get("argument")).get("warrant", "")).strip())
    with_qualifier = sum(1 for item in items if str(_dict(item.get("argument")).get("qualifier", "")).strip())
    return {
        "mandatory_item_count": total,
        "evidence_profile_count": with_profile,
        "warrant_count": with_warrant,
        "qualifier_count": with_qualifier,
        "profile_coverage": _ratio(with_profile, total),
        "warrant_coverage": _ratio(with_warrant, total),
        "qualifier_coverage": _ratio(with_qualifier, total),
    }


def _lineage_completeness(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    with_claims = sum(1 for item in items if _list(_dict(item.get("lineage")).get("derived_from_claim_ids")))
    with_sources = sum(1 for item in items if _list(_dict(item.get("lineage")).get("derived_from_source_ids")))
    return {
        "mandatory_item_count": total,
        "claim_lineage_count": with_claims,
        "source_lineage_count": with_sources,
        "claim_lineage_coverage": _ratio(with_claims, total),
        "source_lineage_coverage": _ratio(with_sources, total),
    }


def _packet_quality_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status", "missing"),
        "issue_count": _list_len(report.get("issues")),
        "warning_count": _list_len(report.get("warnings")),
        "mandatory_item_count": _int(report.get("mandatory_item_count")),
    }


def _runtime_summary(report: dict[str, Any]) -> dict[str, Any]:
    stages = _list(report.get("stages"))
    return {
        "status": report.get("status", "missing"),
        "model_call_count": _int(report.get("model_call_count")),
        "late_stage_count": len(stages),
        "most_expensive_stage": report.get("most_expensive_stage", ""),
        "degraded_mode_triggers": report.get("degraded_mode_triggers", []),
    }


def _manual_review_placeholder(diagnostics: dict[str, Any], rewrite_report: dict[str, Any]) -> dict[str, Any]:
    final_eval = _dict(diagnostics.get("final_eval"))
    coherence = _dict(diagnostics.get("memo_coherence"))
    return {
        "status": "requires_manual_review",
        "automated_readability_signals": {
            "final_evaluation_status": final_eval.get("status", "missing"),
            "memo_coherence_status": coherence.get("status", "missing"),
            "rewrite_status": rewrite_report.get("status", "missing"),
        },
        "note": "Manual memo-quality read is intentionally not inferred from passing tests.",
    }


def _known_weaknesses(*, scaffold: dict[str, Any], diagnostics: dict[str, Any], rewrite_report: dict[str, Any]) -> list[str]:
    weaknesses = []
    packet_quality = _dict(scaffold.get("memo_ready_packet_quality_report"))
    packet_retention = _dict(diagnostics.get("packet_retention"))
    if not rewrite_report.get("memo_ready_packet_path"):
        weaknesses.append("default synthesis did not use memo_ready_packet")
    if _int(packet_retention.get("missing_critical_count") or packet_retention.get("missing_mandatory_count")):
        weaknesses.append("final memo has missing mandatory packet items")
    if _list_len(packet_quality.get("issues")):
        weaknesses.append("memo_ready_packet_quality_report has open issues")
    if _list_len(_dict(scaffold.get("quantity_binding_report")).get("unbound_quantity_groups")):
        weaknesses.append("some quantities remain unbound and diagnostic-only")
    return weaknesses


def _retained_legacy_paths(final_outputs: dict[str, Any]) -> list[dict[str, str]]:
    summary_paths = _dict(final_outputs.get("summary_paths"))
    retained = []
    for key in ("section_rewrite_report", "reader_memo_rewrite_report", "reader_packet_repair_report", "packet_repair_report"):
        if summary_paths.get(key):
            retained.append({"path_key": key, "reason": "compatibility artifact retained for diagnostics and existing consumers"})
    return retained


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _list_len(value: Any) -> int:
    return len(_list(value))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0
