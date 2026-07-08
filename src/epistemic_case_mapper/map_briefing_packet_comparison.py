from __future__ import annotations

from typing import Any


def build_packet_first_comparison_report(
    *,
    scaffold: dict[str, Any],
    section_rewrite_report: dict[str, Any],
    reader_rewrite_report: dict[str, Any],
    runtime_budget_report: dict[str, Any],
    memo_packet_retention_report: dict[str, Any],
) -> dict[str, Any]:
    packet_first = bool(section_rewrite_report.get("packet_first"))
    current_calls = _int_value(runtime_budget_report.get("model_call_count"))
    estimated_section_calls = _estimated_section_rewrite_calls(scaffold, section_rewrite_report)
    reader_calls = _reader_call_count(reader_rewrite_report)
    if packet_first:
        baseline_mode = "estimated_section_rewrite_baseline"
        estimated_baseline_calls = estimated_section_calls + reader_calls
    else:
        baseline_mode = "live_section_rewrite_path"
        estimated_baseline_calls = current_calls
    missing = _retention_missing_summary(memo_packet_retention_report)
    call_delta = estimated_baseline_calls - current_calls
    status = _comparison_status(packet_first=packet_first, missing=missing, call_delta=call_delta)
    return {
        "schema_id": "packet_first_comparison_report_v1",
        "status": status,
        "packet_first": packet_first,
        "baseline_mode": baseline_mode,
        "model_calls": {
            "current_path": current_calls,
            "estimated_section_rewrite_baseline": estimated_baseline_calls,
            "estimated_call_delta": call_delta,
        },
        "retention": {
            "must_retain_count": memo_packet_retention_report.get("must_retain_count", 0),
            "retained_must_retain_count": memo_packet_retention_report.get("retained_must_retain_count", 0),
            "missing_critical_count": memo_packet_retention_report.get("missing_critical_count", 0),
            "missing_high_count": memo_packet_retention_report.get("missing_high_count", 0),
            **missing,
        },
        "reader_rewrite_status": reader_rewrite_report.get("status"),
        "section_rewrite_status": section_rewrite_report.get("status"),
        "notes": _comparison_notes(packet_first=packet_first, baseline_mode=baseline_mode, missing=missing, call_delta=call_delta),
    }


def _comparison_status(*, packet_first: bool, missing: dict[str, int], call_delta: int) -> str:
    if not packet_first:
        return "section_rewrite_baseline"
    if missing["critical_item_misses"] > 0:
        return "packet_first_needs_retention_repair"
    if call_delta > 0:
        return "packet_first_supported_by_estimated_comparison"
    return "packet_first_quality_visible_no_call_savings"


def _comparison_notes(*, packet_first: bool, baseline_mode: str, missing: dict[str, int], call_delta: int) -> list[str]:
    notes = []
    if baseline_mode == "estimated_section_rewrite_baseline":
        notes.append("Comparison did not run the legacy section rewrite path live; baseline model calls are estimated from section views.")
    if packet_first and call_delta > 0:
        notes.append("Packet-first route uses fewer section-local model calls by replacing section rewrites with one whole-memo pass.")
    if missing["critical_item_misses"] > 0:
        notes.append("Packet-first memo still has critical packet-retention warnings; repair or packet quality work should take priority.")
    if missing["quantity_misses"] > 0:
        notes.append("Some packet quantities did not survive into final memo prose.")
    if missing["source_label_misses"] > 0:
        notes.append("Some packet source labels did not survive into final memo prose.")
    return notes


def _retention_missing_summary(report: dict[str, Any]) -> dict[str, int]:
    issues = [issue for issue in report.get("issues", []) if isinstance(issue, dict)]
    return {
        "critical_item_misses": sum(1 for issue in issues if issue.get("severity") == "critical"),
        "high_item_misses": sum(1 for issue in issues if issue.get("severity") == "high"),
        "quantity_misses": sum(len(issue.get("missing_quantities", []) or []) + len(issue.get("missing_required_terms", []) or []) for issue in issues),
        "source_label_misses": sum(len(issue.get("missing_source_labels", []) or []) for issue in issues),
    }


def _estimated_section_rewrite_calls(scaffold: dict[str, Any], section_rewrite_report: dict[str, Any]) -> int:
    if isinstance(section_rewrite_report.get("sections"), list) and section_rewrite_report.get("sections"):
        return sum(_int_value(row.get("attempt_count")) for row in section_rewrite_report["sections"] if isinstance(row, dict))
    packet = scaffold.get("decision_briefing_packet", {}) if isinstance(scaffold.get("decision_briefing_packet"), dict) else {}
    section_views = packet.get("section_views", []) if isinstance(packet.get("section_views"), list) else []
    return len([row for row in section_views if isinstance(row, dict) and row.get("section")])


def _reader_call_count(reader_rewrite_report: dict[str, Any]) -> int:
    status = str(reader_rewrite_report.get("status") or "")
    if status in {"skipped_after_section_rewrite", "not_run", "skipped_prompt_backend"}:
        return 0
    return max(1, _int_value(reader_rewrite_report.get("pass_count")))


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
