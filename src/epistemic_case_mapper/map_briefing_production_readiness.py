from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)


def build_memo_ready_production_readiness_report(packet: dict[str, Any]) -> dict[str, Any]:
    """Report whether a canonical memo-ready packet is safe for live synthesis.

    Prompt-mode artifacts can still be useful for debugging, but a live memo should not
    be generated from a scaffolded analyst answer frame or an empty source hierarchy.
    """

    packet = packet if isinstance(packet, dict) else {}
    applicable = _looks_like_canonical_memo_packet(packet)
    fatal_issues: list[str] = []
    warnings: list[str] = []

    if not applicable:
        return {
            "schema_id": "memo_ready_production_readiness_report_v1",
            "status": "not_applicable",
            "applicable": False,
            "fatal_issues": [],
            "warnings": [],
        }

    hierarchy = _dict(packet.get("analyst_source_hierarchy"))
    hierarchy_report = _dict(packet.get("analyst_source_hierarchy_report"))
    source_judgments = _list(packet.get("analyst_source_weight_judgments"))
    source_judgment_report = _dict(packet.get("analyst_source_weight_judgment_report"))
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    canonical_quality = _dict(packet.get("canonical_decision_writer_packet_quality_report")) or _dict(canonical.get("quality_report"))
    answer_spine = _dict(packet.get("answer_spine"))

    if _missing_source_hierarchy(hierarchy, hierarchy_report):
        fatal_issues.append("missing_or_empty_analyst_source_hierarchy")
    if not source_judgments:
        fatal_issues.append("missing_analyst_source_weight_judgments")
    if _report_has_warning(source_judgment_report):
        warnings.append("analyst_source_weight_judgment_report_warning")
    if _source_weight_projection_fallback_used(canonical):
        fatal_issues.append("writer_role_projection_source_weight_fallback_used")
    if _scaffolded_answer_spine(answer_spine):
        fatal_issues.append("scaffolded_or_truncated_answer_spine")
    if _canonical_quality_blocks(canonical_quality):
        fatal_issues.append("canonical_writer_packet_quality_blocked")
    elif _report_has_warning(canonical_quality):
        warnings.append("canonical_writer_packet_quality_warning")

    fatal_issues = _dedupe(fatal_issues)
    warnings = _dedupe(warnings)
    return {
        "schema_id": "memo_ready_production_readiness_report_v1",
        "status": "blocked" if fatal_issues else ("warning" if warnings else "ready"),
        "applicable": True,
        "fatal_issues": fatal_issues,
        "warnings": warnings,
        "checks": {
            "analyst_source_hierarchy_status": hierarchy_report.get("status"),
            "analyst_source_hierarchy_primary_driver_source_count": hierarchy_report.get("primary_driver_source_count", 0),
            "analyst_source_weight_judgment_count": len(source_judgments),
            "canonical_quality_status": canonical_quality.get("status"),
            "canonical_quality_warnings": _string_list(canonical_quality.get("warnings")),
            "writer_role_projection_source_weight_rows": _writer_projection_row_count(canonical),
        },
    }


def live_synthesis_requires_production_readiness(backend: str) -> bool:
    spec = str(backend or "").strip()
    return spec not in {"", "prompt", "fake"}


def _looks_like_canonical_memo_packet(packet: dict[str, Any]) -> bool:
    return bool(
        packet.get("canonical_decision_writer_packet")
        or packet.get("writer_packet")
        or packet.get("analyst_decision_logic")
        or packet.get("analyst_argument_plan")
        or packet.get("writer_decision_interface")
    )


def _missing_source_hierarchy(hierarchy: dict[str, Any], report: dict[str, Any]) -> bool:
    lanes = _dict(hierarchy.get("lanes"))
    lane_rows = [row for rows in lanes.values() for row in _list(rows)]
    status = str(report.get("status") or "").strip().lower()
    if not hierarchy or not lane_rows:
        return True
    if status in {"", "empty", "missing", "failed", "blocked"}:
        return True
    try:
        primary_count = int(report.get("primary_driver_source_count") or 0)
    except (TypeError, ValueError):
        primary_count = 0
    return primary_count < 1


def _report_has_warning(report: dict[str, Any]) -> bool:
    return str(report.get("status") or "").strip().lower() == "warning" or bool(_list(report.get("warnings")))


def _source_weight_projection_fallback_used(canonical: dict[str, Any]) -> bool:
    return _writer_projection_row_count(canonical) > 0


def _writer_projection_row_count(canonical: dict[str, Any]) -> int:
    frame = _dict(canonical.get("source_weighted_answer_frame"))
    lanes = _dict(frame.get("lanes"))
    count = 0
    for rows in lanes.values():
        count += sum(
            1
            for row in _list(rows)
            if isinstance(row, dict) and str(row.get("source_weight_basis") or "") == "writer_role_projection"
        )
    return count


def _scaffolded_answer_spine(answer_spine: dict[str, Any]) -> bool:
    text = " ".join(
        str(answer_spine.get(key) or "")
        for key in ("default_read", "primary_answer", "full_direct_answer", "why_this_read")
    ).strip()
    if not text:
        return False
    lowered = _norm(text)
    return (
        "scaffold only" in lowered
        or "prompt backend scaffold" in lowered
        or "live global analyst decision modeling was not accepted" in lowered
        or text.endswith(("...", "…"))
    )


def _canonical_quality_blocks(report: dict[str, Any]) -> bool:
    blocking = {
        "truncated_or_scaffolded_direct_answer",
        "missing_source_weight_judgments",
        "source_weight_judgments_warning",
        "source_hierarchy_warning",
    }
    warnings = set(_string_list(report.get("warnings")))
    return bool(warnings.intersection(blocking))
