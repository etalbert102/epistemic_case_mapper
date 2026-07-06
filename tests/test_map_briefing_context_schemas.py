from __future__ import annotations

from epistemic_case_mapper.map_briefing_context_schemas import (
    SOURCE_EVIDENCE_CARD_OWNERSHIP,
    SourceEvidenceCardReport,
    validate_artifact_ownership,
)
from epistemic_case_mapper.map_briefing_context_reports import (
    build_evidence_quality_report,
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
