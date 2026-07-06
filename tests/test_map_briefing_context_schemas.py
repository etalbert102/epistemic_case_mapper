from __future__ import annotations

from epistemic_case_mapper.map_briefing_context_schemas import (
    SOURCE_EVIDENCE_CARD_OWNERSHIP,
    SourceEvidenceCardReport,
    validate_artifact_ownership,
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

