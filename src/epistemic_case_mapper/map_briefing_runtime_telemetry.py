from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_context_schemas import RuntimeBudgetReport


def build_runtime_budget_report(
    *,
    section_rewrite_report: dict[str, Any],
    reader_rewrite_report: dict[str, Any],
    scaffold: dict[str, Any] | None = None,
    packet_plan_report: dict[str, Any] | None = None,
    reader_packet_repair_report: dict[str, Any] | None = None,
    packet_repair_report: dict[str, Any] | None = None,
    editorial_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scaffold = scaffold or {}
    section_attempts = 0
    for section in section_rewrite_report.get("sections", []) if isinstance(section_rewrite_report.get("sections"), list) else []:
        if isinstance(section, dict):
            section_attempts += _int_value(section.get("attempt_count"))
    if reader_rewrite_report.get("status") in {"skipped_after_section_rewrite", "not_run", "skipped_prompt_backend"}:
        reader_model_calls = 0
    else:
        reader_model_calls = max(1, _int_value(reader_rewrite_report.get("pass_count")))
    stages = [
        _runtime_stage_from_report("canonical_decision_spine_arbitration", scaffold.get("canonical_decision_spine_model_arbitration_report")),
        _runtime_stage_from_report("packet_critique", scaffold.get("packet_critique_report")),
        _runtime_stage_from_report("packet_refinement", scaffold.get("decision_briefing_packet_refinement_report")),
        _runtime_stage_from_report("reader_packet_verbalization", _reader_packet_verbalization_runtime_report(packet_plan_report)),
        {"stage": "section_rewrite", "model_call_count": section_attempts},
        {"stage": "reader_memo_rewrite", "model_call_count": reader_model_calls},
        _runtime_stage_from_report("reader_packet_retention_repair", reader_packet_repair_report),
        _runtime_stage_from_report("packet_retention_repair", packet_repair_report),
        _runtime_stage_from_report("decision_memo_editorial", editorial_report),
    ]
    most_expensive = max(stages, key=lambda row: int(row.get("model_call_count", 0)))["stage"] if stages else ""
    return RuntimeBudgetReport(
        scope="late_briefing_stages_only",
        excludes=["claim_extraction", "claim_consolidation", "relation_candidate_selection", "relation_mapping"],
        stages=stages,
        model_call_count=sum(int(stage.get("model_call_count", 0)) for stage in stages),
        degraded_mode_triggers=_runtime_degraded_triggers(
            section_rewrite_report,
            reader_rewrite_report,
            packet_plan_report=packet_plan_report,
            reader_packet_repair_report=reader_packet_repair_report,
            packet_repair_report=packet_repair_report,
            editorial_report=editorial_report,
        ),
        most_expensive_stage=most_expensive,
    ).model_dump()


def build_stage_value_report(
    *,
    scaffold: dict[str, Any],
    section_rewrite_report: dict[str, Any],
    reader_rewrite_report: dict[str, Any],
    packet_retention_report: dict[str, Any],
    final_evaluation: dict[str, Any],
) -> dict[str, Any]:
    packet_critique_adjudication = _dict(scaffold.get("packet_critique_adjudication_report"))
    packet_refinement = _dict(scaffold.get("decision_briefing_packet_refinement_report"))
    source_cards = _dict(scaffold.get("source_evidence_cards"))
    packet = _dict(scaffold.get("decision_briefing_packet"))
    rows = [
        {
            "stage": "source_evidence_cards",
            "status": "useful" if _int_value(source_cards.get("anchored_card_count")) else "weak_or_missing",
            "primary_signal": f"{_int_value(source_cards.get('anchored_card_count'))}/{_int_value(source_cards.get('source_card_count'))} source cards anchored",
        },
        {
            "stage": "decision_briefing_packet",
            "status": "useful" if packet.get("evidence_bundles") else "weak_or_missing",
            "primary_signal": f"{_list_len(packet.get('evidence_bundles'))} evidence bundles; {_list_len(packet.get('must_retain_ledger'))} must-retain items",
        },
        {
            "stage": "packet_critique",
            "status": _value_status_from_counts(
                accepted=_int_value(packet_critique_adjudication.get("accepted_count")),
                warnings=_int_value(packet_critique_adjudication.get("warning_only_count")) + _int_value(packet_critique_adjudication.get("rejected_count")),
                report_status=str(packet_critique_adjudication.get("status", "")),
            ),
            "primary_signal": f"{_int_value(packet_critique_adjudication.get('accepted_count'))} accepted edits; {_issue_count(packet_critique_adjudication)} critique issues retained",
        },
        {
            "stage": "packet_refinement",
            "status": _value_status_from_counts(
                accepted=_int_value(packet_refinement.get("applied_update_count")),
                warnings=_int_value(packet_refinement.get("rejected_update_count")),
                report_status=str(packet_refinement.get("status", "")),
            ),
            "primary_signal": f"{_int_value(packet_refinement.get('applied_update_count'))} applied updates; status={packet_refinement.get('status', 'missing')}",
        },
        {
            "stage": "reader_synthesis",
            "status": "useful" if reader_rewrite_report.get("status") not in {"", "not_run", "skipped_prompt_backend"} else "weak_or_missing",
            "primary_signal": f"reader rewrite status={reader_rewrite_report.get('status', 'missing')}; section status={section_rewrite_report.get('status', 'missing')}",
        },
        {
            "stage": "retention",
            "status": "weak_or_missing" if _int_value(packet_retention_report.get("missing_critical_count")) else "useful",
            "primary_signal": f"{_int_value(packet_retention_report.get('missing_critical_count'))} critical and {_int_value(packet_retention_report.get('missing_high_count'))} high-priority retained-evidence misses",
        },
        {
            "stage": "final_evaluation",
            "status": str(final_evaluation.get("status", "missing")),
            "primary_signal": "; ".join(str(issue) for issue in final_evaluation.get("issues", [])[:3])
            if isinstance(final_evaluation.get("issues"), list)
            else "",
        },
    ]
    weak = [row["stage"] for row in rows if row["status"] in {"weak_or_missing", "fail", "parse_failed"}]
    return {
        "schema_id": "stage_value_report_v1",
        "status": "warning" if weak else "pass",
        "stages": rows,
        "weak_or_missing_stages": weak,
    }


def _runtime_stage_from_report(stage: str, report: Any) -> dict[str, Any]:
    if not isinstance(report, dict) or not report:
        return {"stage": stage, "model_call_count": 0, "status": "missing"}
    status = str(report.get("status", "")).strip() or "unknown"
    return {"stage": stage, "model_call_count": 0 if _is_non_model_status(status) else 1, "status": status}


def _reader_packet_verbalization_runtime_report(packet_plan_report: dict[str, Any] | None) -> dict[str, Any]:
    report = packet_plan_report or {}
    return {"status": report.get("reader_packet_verbalization_status", "missing")}


def _is_non_model_status(status: str) -> bool:
    normalized = status.strip().lower()
    return (
        not normalized
        or normalized in {"missing", "not_needed", "not_run", "skipped", "skipped_after_section_rewrite", "skipped_prompt_backend"}
        or normalized.startswith("skipped_")
        or "prompt_backend" in normalized
    )


def _runtime_degraded_triggers(
    section_rewrite_report: dict[str, Any],
    reader_rewrite_report: dict[str, Any],
    *,
    packet_plan_report: dict[str, Any] | None = None,
    reader_packet_repair_report: dict[str, Any] | None = None,
    packet_repair_report: dict[str, Any] | None = None,
    editorial_report: dict[str, Any] | None = None,
) -> list[str]:
    triggers: list[str] = []
    if section_rewrite_report.get("status") in {"global_validation_failed_fallback", "no_sections_accepted"}:
        triggers.append(str(section_rewrite_report.get("status")))
    for section in section_rewrite_report.get("sections", []) if isinstance(section_rewrite_report.get("sections"), list) else []:
        if isinstance(section, dict) and section.get("structured_fallback"):
            triggers.append(f"structured_fallback:{section.get('title', '')}")
    if reader_rewrite_report.get("status") == "skipped_after_section_rewrite":
        triggers.append("reader_memo_rewrite_skipped")
    if reader_rewrite_report.get("status") == "skipped_prompt_backend":
        triggers.append("reader_memo_rewrite_prompt_backend")
    for stage, report in (
        ("reader_packet_verbalization", packet_plan_report),
        ("reader_packet_retention_repair", reader_packet_repair_report),
        ("packet_retention_repair", packet_repair_report),
        ("decision_memo_editorial", editorial_report),
    ):
        status = str((report or {}).get("status", "")).strip()
        if status and any(token in status for token in ("failed", "fallback", "kept_original", "backend_error")):
            triggers.append(f"{stage}:{status}")
    return triggers


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _list_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _issue_count(report: dict[str, Any]) -> int:
    issue_fields = (
        "answer_frame_issues",
        "misleading_synthesis_risks",
        "insufficiency_warnings",
        "claim_quality_issues",
        "section_routing_issues",
        "missing_decision_functions",
        "section_plan_risks",
    )
    return sum(len(value) for field in issue_fields if isinstance((value := report.get(field)), list))


def _value_status_from_counts(*, accepted: int, warnings: int, report_status: str) -> str:
    if not report_status or report_status == "missing":
        return "weak_or_missing"
    if "parse_failed" in report_status or "failed" in report_status:
        return "parse_failed"
    if accepted or warnings:
        return "useful"
    if "skipped" in report_status:
        return "weak_or_missing"
    return "passive"
