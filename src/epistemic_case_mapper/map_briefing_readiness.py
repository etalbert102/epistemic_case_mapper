from __future__ import annotations

from typing import Any


def build_packet_quality_gate_report(scaffold: dict[str, Any]) -> dict[str, Any]:
    packet = _dict(scaffold.get("decision_briefing_packet"))
    sufficiency = _dict(scaffold.get("packet_sufficiency_report"))
    critique = _dict(scaffold.get("packet_critique_report"))
    adjudication = _dict(scaffold.get("packet_critique_adjudication_report"))
    issues: list[dict[str, Any]] = []
    if not packet.get("evidence_bundles"):
        issues.append(_issue("blocker", "packet_has_no_evidence_bundles"))
    if not packet.get("must_retain_ledger"):
        issues.append(_issue("blocker", "packet_has_no_must_retain_ledger"))
    if sufficiency.get("status") == "not_sufficient_for_synthesis":
        issues.append(_issue("blocker", "packet_sufficiency_failed", sufficiency.get("issues", [])))
    elif sufficiency.get("issues"):
        issues.append(_issue("warning", "packet_sufficiency_warnings", sufficiency.get("issues", [])))
    if critique.get("status") == "parse_failed":
        issues.append(_issue("warning", "packet_critique_parse_failed", _parse_errors(critique)))
    elif critique.get("status") in {"skipped", "skipped_prompt_backend"} and not _intentional_packet_critique_skip(critique):
        issues.append(_issue("warning", "packet_critique_not_run", critique.get("status")))
    if _int(adjudication.get("rejected_count")):
        issues.append(_issue("warning", "packet_critique_rejected_recommendations", adjudication.get("rejected_count")))
    if _int(adjudication.get("warning_only_count")):
        issues.append(_issue("warning", "packet_critique_warning_only_recommendations", adjudication.get("warning_only_count")))
    blockers = [issue for issue in issues if issue["severity"] == "blocker"]
    status = "not_ready" if blockers else "warning" if issues else "ready"
    return {
        "schema_id": "packet_quality_gate_report_v1",
        "status": status,
        "packet_ready_for_synthesis": status != "not_ready",
        "issues": issues,
        "source_signals": {
            "packet_sufficiency_status": sufficiency.get("status", "missing"),
            "packet_critique_status": critique.get("status", "missing"),
            "packet_critique_judgment": critique.get("judgment", adjudication.get("judgment", "missing")),
            "accepted_critique_recommendations": _int(adjudication.get("accepted_count")),
            "rejected_critique_recommendations": _int(adjudication.get("rejected_count")),
            "warning_only_critique_recommendations": _int(adjudication.get("warning_only_count")),
        },
    }


def build_final_decision_readiness_report(
    *,
    scaffold: dict[str, Any],
    validation_report: dict[str, Any],
    memo_coherence_report: dict[str, Any],
    packet_retention_report: dict[str, Any],
    final_evaluation: dict[str, Any],
) -> dict[str, Any]:
    packet_gate = _dict(scaffold.get("packet_quality_gate_report"))
    issues: list[dict[str, Any]] = []
    if packet_gate.get("status") == "not_ready":
        issues.append(_issue("blocker", "packet_quality_gate_not_ready", packet_gate.get("issues", [])))
    elif packet_gate.get("status") == "warning":
        issues.append(_issue("warning", "packet_quality_gate_warnings", packet_gate.get("issues", [])))
    if _int(packet_retention_report.get("missing_critical_count")):
        issues.append(_issue("blocker", "critical_packet_evidence_missing_from_memo", packet_retention_report.get("missing_critical_count")))
    if _int(packet_retention_report.get("missing_high_count")):
        issues.append(_issue("warning", "high_priority_packet_evidence_missing_from_memo", packet_retention_report.get("missing_high_count")))
    if str(final_evaluation.get("status")) == "fail":
        issues.append(_issue("blocker", "final_brief_evaluation_failed", final_evaluation.get("issues", [])))
    elif str(final_evaluation.get("status")) == "warning":
        issues.append(_issue("warning", "final_brief_evaluation_warnings", final_evaluation.get("issues", [])))
    if str(memo_coherence_report.get("status")) == "fail":
        issues.append(_issue("blocker", "memo_coherence_failed", memo_coherence_report.get("issues", [])))
    elif str(memo_coherence_report.get("status")) == "warning":
        issues.append(_issue("warning", "memo_coherence_warnings", memo_coherence_report.get("issues", [])))
    if str(validation_report.get("status")) in {"fails", "fail", "failed"}:
        issues.append(_issue("blocker", "briefing_validation_failed", validation_report.get("issues", [])))
    elif "warning" in str(validation_report.get("status", "")).lower():
        issues.append(_issue("warning", "briefing_validation_warnings", validation_report.get("issues", [])))
    blockers = [issue for issue in issues if issue["severity"] == "blocker"]
    status = "not_decision_ready" if blockers else "decision_ready_with_warnings" if issues else "decision_ready"
    return {
        "schema_id": "final_decision_readiness_report_v1",
        "status": status,
        "decision_ready": status == "decision_ready",
        "decision_ready_with_warnings": status in {"decision_ready", "decision_ready_with_warnings"},
        "issues": issues,
        "source_signals": {
            "packet_quality_gate_status": packet_gate.get("status", "missing"),
            "packet_retention_status": packet_retention_report.get("status", "missing"),
            "final_evaluation_status": final_evaluation.get("status", "missing"),
            "memo_coherence_status": memo_coherence_report.get("status", "missing"),
            "briefing_validation_status": validation_report.get("status", "missing"),
        },
    }


def build_memo_semantic_acceptance_report(
    *,
    final_readiness_report: dict[str, Any],
    memo_quality_report: dict[str, Any],
    polish_report: dict[str, Any],
    validation_report: dict[str, Any],
    packet_retention_report: dict[str, Any],
    final_evaluation: dict[str, Any],
) -> dict[str, Any]:
    readiness_status = str(final_readiness_report.get("status") or "missing")
    readiness_issues = [
        issue
        for issue in final_readiness_report.get("issues", [])
        if isinstance(issue, dict)
    ]
    blockers = [issue for issue in readiness_issues if issue.get("severity") == "blocker"]
    issues = _acceptance_issues(
        blockers=blockers,
        readiness_status=readiness_status,
        memo_quality_report=memo_quality_report,
        polish_report=polish_report,
        packet_retention_report=packet_retention_report,
    )
    status = _acceptance_status(readiness_status, blockers, issues)
    return {
        "schema_id": "memo_semantic_acceptance_report_v1",
        "status": status,
        "accepted_for_decision_use": status in {"accepted", "accepted_with_warnings"},
        "report_mode": "report_only",
        "issues": issues,
        "high_confidence_blockers": blockers,
        "source_signals": {
            "final_readiness_status": readiness_status,
            "memo_quality_status": memo_quality_report.get("status", "missing"),
            "memo_quality_score": memo_quality_report.get("score", "missing"),
            "polish_status": polish_report.get("status", "missing"),
            "briefing_validation_status": validation_report.get("status", "missing"),
            "packet_retention_status": packet_retention_report.get("status", "missing"),
            "missing_critical_count": _int(packet_retention_report.get("missing_critical_count")),
            "final_evaluation_status": final_evaluation.get("status", "missing"),
        },
    }


def _issue(severity: str, issue_type: str, detail: Any = "") -> dict[str, Any]:
    return {"severity": severity, "issue_type": issue_type, "detail": detail}


def _acceptance_issues(
    *,
    blockers: list[dict[str, Any]],
    readiness_status: str,
    memo_quality_report: dict[str, Any],
    polish_report: dict[str, Any],
    packet_retention_report: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if blockers:
        issues.append(_issue("blocker", "final_readiness_blockers", [issue.get("issue_type") for issue in blockers]))
    if _int(packet_retention_report.get("missing_critical_count")):
        issues.append(_issue("blocker", "critical_evidence_missing_from_final_memo", packet_retention_report.get("missing_critical_count")))
    if readiness_status == "not_decision_ready" and str(memo_quality_report.get("status")) == "polished":
        issues.append(_issue("blocker", "polished_but_not_decision_ready", memo_quality_report.get("score", "")))
    if readiness_status == "not_decision_ready" and str(polish_report.get("status", "")).startswith("polished"):
        issues.append(_issue("warning", "reader_polish_does_not_imply_decision_acceptance", polish_report.get("score", "")))
    return issues


def _acceptance_status(
    readiness_status: str,
    blockers: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> str:
    if blockers or any(issue.get("severity") == "blocker" for issue in issues) or readiness_status == "not_decision_ready":
        return "not_accepted"
    if readiness_status == "decision_ready_with_warnings" or issues:
        return "accepted_with_warnings"
    return "accepted"


def _parse_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    parse_report = report.get("parse_report")
    if not isinstance(parse_report, dict):
        return []
    errors = parse_report.get("errors")
    return errors if isinstance(errors, list) else []


def _intentional_packet_critique_skip(report: dict[str, Any]) -> bool:
    return str(report.get("reason") or "").startswith("auto_skipped_")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
