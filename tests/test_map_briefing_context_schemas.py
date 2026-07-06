from __future__ import annotations

from epistemic_case_mapper.map_briefing_context_schemas import (
    SOURCE_EVIDENCE_CARD_OWNERSHIP,
    SourceEvidenceCardReport,
    validate_artifact_ownership,
)
from epistemic_case_mapper.map_briefing_context_reports import (
    build_evidence_quality_report,
    build_final_brief_evaluation,
    build_memo_coherence_report,
    build_pipeline_migration_ledger,
    build_runtime_budget_report,
    build_section_context_acceptance_report,
    build_source_evidence_cards,
    build_source_sufficiency_report,
)


def test_source_evidence_card_schema_accepts_exact_anchored_card() -> None:
    report = SourceEvidenceCardReport.model_validate(
        {
            "source_card_count": 1,
            "anchored_card_count": 1,
            "cards": [
                {
                    "source_card_id": "sc0001",
                    "source_id": "s1",
                    "source_title": "Study",
                    "source_span": "10:40",
                    "source_quote_or_excerpt": "A source-backed claim.",
                    "anchor_confidence": "exact",
                }
            ],
        }
    )

    assert report.cards[0].source_id == "s1"


def test_ownership_validation_rejects_model_generated_source_identity() -> None:
    artifact = {
        "source_card_count": 1,
        "cards": [
            {
                "source_card_id": "sc0001",
                "source_id": "s1",
                "source_title": "Study",
                "anchor_confidence": "missing",
            }
        ],
    }

    validation = validate_artifact_ownership(
        "source_evidence_cards",
        artifact,
        schema=SourceEvidenceCardReport,
        field_ownership=SOURCE_EVIDENCE_CARD_OWNERSHIP,
        model_generated_fields=["source_id", "endpoint_match"],
    )

    assert validation["status"] == "invalid"
    assert validation["schema_parse_ok"] is True
    assert validation["deterministic_only_violations"] == [
        {"path": "source_id", "ownership": "deterministic_only"}
    ]
    assert validation["fallback_behavior"] == "quarantine_invalid_artifact"


def test_ownership_validation_reports_schema_errors() -> None:
    validation = validate_artifact_ownership(
        "source_evidence_cards",
        {"cards": [{"source_card_id": "sc0001"}]},
        schema=SourceEvidenceCardReport,
        field_ownership=SOURCE_EVIDENCE_CARD_OWNERSHIP,
    )

    assert validation["status"] == "invalid"
    assert validation["schema_parse_ok"] is False
    assert any(error["path"].endswith("source_id") for error in validation["validation_errors"])


def test_source_sufficiency_and_quality_reports_from_claim_anchors() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "claim": "Moderate use directly changes the decision-relevant outcome.",
                "source_id": "s1",
                "source_span": "10:55",
                "role": "conclusion_support",
                "decision_relevance_score": 8,
                "evidence_family": "cohort_study",
            },
            {
                "claim_id": "c2",
                "claim": "A high-risk subgroup is an important exception.",
                "source_id": "s2",
                "role": "scope_limit",
                "decision_relevance_score": 5,
            },
        ]
    }

    source_cards = build_source_evidence_cards(
        candidate_map,
        source_lookup={"s1": "Source One", "s2": "Source Two"},
        source_urls={"s1": "https://example.org/source-one"},
    )
    sufficiency = build_source_sufficiency_report(
        decision_question="Should moderate use change the decision-relevant outcome?",
        source_evidence_cards=source_cards,
        scaffold={"map_sufficiency_report": {}},
    )
    quality = build_evidence_quality_report(source_cards)

    assert source_cards["schema_id"] == "source_evidence_cards_v1"
    assert source_cards["source_card_count"] == 2
    assert source_cards["anchored_card_count"] == 2
    assert sufficiency["schema_id"] == "source_sufficiency_report_v1"
    assert sufficiency["status"] == "sufficient_for_bounded_answer"
    assert "counterweight_evidence" in sufficiency["missing_source_categories"]
    assert quality["schema_id"] == "evidence_quality_report_v1"
    assert quality["card_count"] == 2
    assert quality["quality_components"]["sc0001"]["directness"] == "direct"


def test_section_context_acceptance_requires_roles_and_reasons() -> None:
    report = build_section_context_acceptance_report(
        [
            {
                "title": "Evidence Carrying the Conclusion",
                "section_job": "Explain the main evidence.",
                "model_packet": {
                    "section_thesis": "The section can explain the main evidence.",
                    "owned_evidence": [
                        {
                            "claim": "Claim one.",
                            "source": "Source",
                            "intended_role": "support",
                            "reason_for_inclusion": "This is the section's support card.",
                        },
                        {
                            "claim": "Claim two.",
                            "source": "Source",
                            "intended_role": "counterweight",
                            "reason_for_inclusion": "This is the section's counterweight card.",
                        },
                        {
                            "claim": "Claim three.",
                            "source": "Source",
                            "intended_role": "scope boundary",
                            "reason_for_inclusion": "This is the section's scope card.",
                        },
                    ],
                },
                "packet": {},
            },
            {
                "title": "Why This Read",
                "section_job": "Explain the read.",
                "model_packet": {"owned_evidence": [{"claim": "Unexplained claim."}]},
                "packet": {},
            },
        ]
    )

    assert report["schema_id"] == "section_context_acceptance_report_v1"
    assert report["status"] == "warning"
    assert report["sections"][0]["status"] == "ready"
    assert report["sections"][1]["card_budget_status"] == "under_budget"
    assert any("missing intended_role" in issue for issue in report["sections"][1]["issues"])


def test_final_diagnostic_reports_are_deterministic() -> None:
    scaffold = {
        "question": "Should the decision change?",
        "source_display_names": {"s1": "Source One"},
        "source_sufficiency_report": {"bounded_answer_required": True},
        "evidence_quality_report": {"weak_or_indirect_count": 1},
    }
    memo = """## Decision Brief

**Decision question:** Should the decision change?

The current map supports a bounded read over the provided documents, with limited evidence quality.

**Confidence:** medium

## Sources

- Source One
"""

    coherence = build_memo_coherence_report(
        memo_markdown=memo,
        decision_question="Should the decision change?",
        scaffold=scaffold,
    )
    migration = build_pipeline_migration_ledger(section_context_acceptance_path="section_context_acceptance_report.json")
    runtime = build_runtime_budget_report(
        section_rewrite_report={"sections": [{"attempt_count": 2}, {"attempt_count": 1}]},
        reader_rewrite_report={"status": "skipped_after_section_rewrite"},
    )
    evaluation = build_final_brief_evaluation(
        memo_markdown=memo,
        memo_path="BRIEFING.md",
        decision_question="Should the decision change?",
        coherence_report=coherence,
        scaffold=scaffold,
    )

    assert coherence["schema_id"] == "memo_coherence_report_v1"
    assert coherence["status"] == "pass"
    assert migration["schema_id"] == "pipeline_migration_ledger_v1"
    assert migration["status"] == "warning"
    assert runtime["schema_id"] == "runtime_budget_report_v1"
    assert runtime["model_call_count"] == 3
    assert runtime["most_expensive_stage"] == "section_rewrite"
    assert evaluation["schema_id"] == "final_brief_evaluation_v1"
    assert evaluation["status"] == "pass"
