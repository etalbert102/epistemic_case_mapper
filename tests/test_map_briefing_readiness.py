from __future__ import annotations

from epistemic_case_mapper.map_briefing_readiness import (
    build_final_decision_readiness_report,
    build_packet_quality_gate_report,
)


def test_packet_quality_gate_blocks_unparsed_critique_and_missing_packet() -> None:
    report = build_packet_quality_gate_report(
        {
            "decision_briefing_packet": {"evidence_bundles": [], "must_retain_ledger": []},
            "packet_sufficiency_report": {"status": "not_sufficient_for_synthesis", "issues": ["missing_available_roles"]},
            "packet_critique_report": {
                "status": "parse_failed",
                "parse_report": {"errors": [{"path": "bundle_role_checks.0.recommended_role"}]},
            },
        }
    )

    assert report["schema_id"] == "packet_quality_gate_report_v1"
    assert report["status"] == "not_ready"
    assert report["packet_ready_for_synthesis"] is False
    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert "packet_has_no_evidence_bundles" in issue_types
    assert "packet_critique_parse_failed" in issue_types
    parse_issue = next(issue for issue in report["issues"] if issue["issue_type"] == "packet_critique_parse_failed")
    assert parse_issue["severity"] == "warning"


def test_packet_quality_gate_does_not_block_on_parse_failure_alone() -> None:
    report = build_packet_quality_gate_report(
        {
            "decision_briefing_packet": {
                "evidence_bundles": [{"bundle_id": "bundle_001"}],
                "must_retain_ledger": [{"item_id": "retain_001"}],
            },
            "packet_sufficiency_report": {"status": "ready", "issues": []},
            "packet_critique_report": {
                "status": "parse_failed",
                "parse_report": {"errors": [{"path": "misleading_synthesis_risks", "message": "expected array"}]},
            },
            "packet_critique_adjudication_report": {
                "status": "accepted",
                "accepted_count": 0,
                "rejected_count": 0,
                "warning_only_count": 0,
            },
        }
    )

    assert report["status"] == "warning"
    assert report["packet_ready_for_synthesis"] is True
    assert report["issues"][0]["issue_type"] == "packet_critique_parse_failed"


def test_packet_quality_gate_allows_warning_only_adjudication() -> None:
    report = build_packet_quality_gate_report(
        {
            "decision_briefing_packet": {"evidence_bundles": [{"bundle_id": "bundle_001"}], "must_retain_ledger": [{"item_id": "retain_001"}]},
            "packet_sufficiency_report": {"status": "usable_with_warnings", "issues": ["high_priority_omitted_evidence"]},
            "packet_critique_report": {"status": "parsed", "judgment": "needs_repair"},
            "packet_critique_adjudication_report": {"status": "accepted_with_warnings", "accepted_count": 1, "warning_only_count": 1},
        }
    )

    assert report["status"] == "warning"
    assert report["packet_ready_for_synthesis"] is True
    assert report["source_signals"]["accepted_critique_recommendations"] == 1


def test_final_decision_readiness_surfaces_retention_blockers() -> None:
    report = build_final_decision_readiness_report(
        scaffold={"packet_quality_gate_report": {"status": "warning", "issues": [{"issue_type": "packet_sufficiency_warnings"}]}},
        validation_report={"status": "passes_with_warnings", "issues": ["sparse_relation_graph"]},
        memo_coherence_report={"status": "pass", "issues": []},
        packet_retention_report={"status": "critical_warnings", "missing_critical_count": 2, "missing_high_count": 1},
        final_evaluation={"status": "warning", "issues": ["retention gap"]},
    )

    assert report["schema_id"] == "final_decision_readiness_report_v1"
    assert report["status"] == "not_decision_ready"
    assert report["decision_ready"] is False
    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert "critical_packet_evidence_missing_from_memo" in issue_types
    assert "packet_quality_gate_warnings" in issue_types
