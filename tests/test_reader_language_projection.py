from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_reader_language import project_reader_language_for_model


def test_reader_language_projection_translates_internal_prose_without_mutating_canonical_fields() -> None:
    payload = {
        "role": "strongest_counterweight",
        "source_id": "risk_source",
        "value": "1.25",
        "validation_terms": ["decision read", "counterweight"],
        "statement": "Use this counterweight to bound the decision read.",
        "guidance": ["Avoid checklist rhythm and source-label-as-subject patterns."],
        "nested": {"writing_job": "This must-write card is part of the retention contract."},
    }

    projected = project_reader_language_for_model(payload)

    assert projected["role"] == "strongest_counterweight"
    assert projected["source_id"] == "risk_source"
    assert projected["value"] == "1.25"
    assert projected["validation_terms"] == ["decision read", "counterweight"]
    assert projected["statement"] == "Use this limiting evidence to bound the answer."
    assert projected["guidance"] == ["Avoid list-like rhythm and source names as repeated sentence subjects."]
    assert projected["nested"]["writing_job"] == "This required point is part of the required evidence to preserve."
