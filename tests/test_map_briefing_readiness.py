from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_readiness import (
    build_final_decision_readiness_report,
    build_final_lineage_report,
    build_memo_semantic_acceptance_report,
    build_packet_quality_gate_report,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_final_outputs import _memo_ready_synthesis_failed


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


def test_packet_quality_gate_treats_intentional_auto_skip_as_clean() -> None:
    report = build_packet_quality_gate_report(
        {
            "decision_briefing_packet": {
                "evidence_bundles": [{"bundle_id": "bundle_001"}],
                "must_retain_ledger": [{"item_id": "retain_001"}],
            },
            "packet_sufficiency_report": {"status": "ready", "issues": []},
            "packet_critique_report": {
                "status": "skipped",
                "reason": "auto_skipped_lightweight_guidance_default",
            },
            "packet_critique_adjudication_report": {
                "status": "skipped",
                "accepted_count": 0,
                "rejected_count": 0,
                "warning_only_count": 0,
            },
        }
    )

    assert report["status"] == "ready"
    assert not report["issues"]


def test_packet_quality_gate_still_warns_on_prompt_backend_skip() -> None:
    report = build_packet_quality_gate_report(
        {
            "decision_briefing_packet": {
                "evidence_bundles": [{"bundle_id": "bundle_001"}],
                "must_retain_ledger": [{"item_id": "retain_001"}],
            },
            "packet_sufficiency_report": {"status": "ready", "issues": []},
            "packet_critique_report": {"status": "skipped_prompt_backend"},
            "packet_critique_adjudication_report": {
                "status": "skipped_prompt_backend",
                "accepted_count": 0,
                "rejected_count": 0,
                "warning_only_count": 0,
            },
        }
    )

    assert report["status"] == "warning"
    assert report["issues"][0]["issue_type"] == "packet_critique_not_run"


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
        lineage_report={"status": "accepted", "accepted": True, "reader_output_available": True},
    )

    assert report["schema_id"] == "final_decision_readiness_report_v1"
    assert report["status"] == "not_decision_ready"
    assert report["decision_ready"] is False
    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert "critical_packet_evidence_missing_from_memo" in issue_types
    assert "packet_quality_gate_warnings" in issue_types


def test_final_lineage_fails_closed_for_unaccepted_or_unknown_memo_stages() -> None:
    common = {
        "scaffold": {
            "packet_quality_gate_report": {
                "schema_id": "packet_quality_gate_report_v1",
                "status": "ready",
                "packet_ready_for_synthesis": True,
            }
        },
        "synthesis_report": {"schema_id": "synthesis_v1", "status": "accepted", "accepted": True},
        "repair_report": {"schema_id": "repair_v1", "status": "not_needed", "accepted": False},
        "polish_report": {"schema_id": "polish_v1", "status": "accepted", "accepted": True},
        "presentation_report": {"schema_id": "presentation_v1", "status": "no_changes", "accepted": True},
        "reader_output_available": True,
    }

    accepted = build_final_lineage_report(**common)
    assert accepted["status"] == "accepted"
    assert accepted["reader_output_available"] is True

    for stage, report in (
        ("synthesis", {"status": "production_readiness_blocked", "accepted": False}),
        ("synthesis", {"status": "novel_unknown_status"}),
        ("repair", {"status": "partial_retention_improvement_applied_with_warnings", "accepted": False}),
        ("polish", {"status": "rejected_kept_original", "accepted": False}),
    ):
        inputs = dict(common)
        inputs[f"{stage}_report"] = report
        lineage = build_final_lineage_report(**inputs)
        assert lineage["status"] == "blocked"
        assert f"{stage}_not_accepted" in lineage["fatal_issues"]


def test_final_readiness_keeps_reader_availability_separate_from_decision_readiness() -> None:
    lineage = build_final_lineage_report(
        scaffold={"packet_quality_gate_report": {"status": "ready", "packet_ready_for_synthesis": True}},
        synthesis_report={"status": "production_readiness_blocked", "accepted": False},
        repair_report={"status": "not_needed", "accepted": False},
        polish_report={"status": "accepted", "accepted": True},
        presentation_report={"status": "changed", "accepted": True},
        reader_output_available=True,
    )
    report = build_final_decision_readiness_report(
        scaffold={"packet_quality_gate_report": {"status": "ready"}},
        validation_report={"status": "passes", "issues": []},
        memo_coherence_report={"status": "pass", "issues": []},
        packet_retention_report={"status": "ready", "missing_critical_count": 0, "missing_high_count": 0},
        final_evaluation={"status": "pass", "issues": []},
        lineage_report=lineage,
    )

    assert report["reader_output_available"] is True
    assert report["decision_ready"] is False
    assert report["status"] == "not_decision_ready"
    assert "final_lineage_not_accepted" in {issue["issue_type"] for issue in report["issues"]}


def test_synthesis_path_stops_on_any_report_without_explicit_acceptance() -> None:
    assert _memo_ready_synthesis_failed({"report": {"status": "production_readiness_blocked", "accepted": False}}) is True
    assert _memo_ready_synthesis_failed({"report": {"status": "unknown_future_status"}}) is True
    assert _memo_ready_synthesis_failed({"report": {"status": "accepted_with_warnings", "accepted": True}}) is False


def test_memo_semantic_acceptance_flags_polished_but_not_decision_ready() -> None:
    report = build_memo_semantic_acceptance_report(
        final_readiness_report={
            "status": "not_decision_ready",
            "issues": [{"severity": "blocker", "issue_type": "critical_packet_evidence_missing_from_memo"}],
        },
        memo_quality_report={"status": "polished", "score": 95},
        polish_report={"status": "polished", "score": 92},
        validation_report={"status": "passes"},
        packet_retention_report={"status": "critical_warnings", "missing_critical_count": 1},
        final_evaluation={"status": "warning"},
    )

    assert report["schema_id"] == "memo_semantic_acceptance_report_v1"
    assert report["status"] == "not_accepted"
    assert report["accepted_for_decision_use"] is False
    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert "polished_but_not_decision_ready" in issue_types
    assert "critical_evidence_missing_from_final_memo" in issue_types


def test_memo_semantic_acceptance_allows_ready_with_warnings() -> None:
    report = build_memo_semantic_acceptance_report(
        final_readiness_report={
            "status": "decision_ready_with_warnings",
            "issues": [{"severity": "warning", "issue_type": "briefing_validation_warnings"}],
        },
        memo_quality_report={"status": "usable_with_review", "score": 82},
        polish_report={"status": "polished_with_warnings", "score": 82},
        validation_report={"status": "passes_with_warnings"},
        packet_retention_report={"status": "ready", "missing_critical_count": 0},
        final_evaluation={"status": "warning"},
    )

    assert report["status"] == "accepted_with_warnings"
    assert report["accepted_for_decision_use"] is True
    assert report["high_confidence_blockers"] == []
