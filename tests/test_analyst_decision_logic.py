from __future__ import annotations

from epistemic_case_mapper.map_briefing_analyst_decision_logic import (
    analyst_decision_logic,
    naturalize_decision_logic_payload,
)


def test_decision_logic_naturalizes_artifact_and_overstrong_language() -> None:
    logic = {
        "bounded_bottom_line": "Daily use is a crux for the recommendation.",
        "support_summary": "The result identifies cholesterol as the primary driver of risk.",
        "strongest_counterweight": "The association may be a byproduct of total exposure.",
        "counterweight_weighting": "This is not an inherent property of the intervention.",
        "reconciled_cruxes": ["These findings are consistently neutralized after adjustment."],
        "scope_boundaries": ["The subgroup is a crux for transportability."],
        "practical_implications": ["This fundamentally changing implementation advice."],
        "do_not_overstate": ["Do not say the signal was neutralized."],
    }

    result = naturalize_decision_logic_payload(logic)
    flattened = " ".join(
        [
            result["bounded_bottom_line"],
            result["support_summary"],
            result["strongest_counterweight"],
            result["counterweight_weighting"],
            *result["reconciled_cruxes"],
            *result["scope_boundaries"],
            *result["practical_implications"],
            *result["do_not_overstate"],
        ]
    ).lower()

    assert "crux for" not in flattened
    assert "primary driver" not in flattened
    assert "byproduct of" not in flattened
    assert "inherent property" not in flattened
    assert "consistently neutralized" not in flattened
    assert "fundamentally changing" not in flattened
    assert "plausible important driver" in flattened
    assert "partly explained by" in flattened
    assert "less decisive after adjustment" in flattened


def test_analyst_decision_logic_naturalizes_refined_output() -> None:
    result = analyst_decision_logic(
        refinement={
            "decision_logic": {
                "bounded_bottom_line": "Proceed only in the scoped population.",
                "support_summary": "The support identifies a primary driver of benefit.",
                "counterweight_weighting": "The counterweight is a byproduct of comparator choice.",
                "reconciled_cruxes": ["Comparator choice is a crux for the answer."],
            }
        },
        answer_frame={"must_not_overstate": ["Do not imply an inherent property of the intervention."]},
        groups=[],
        warning_obligations=[],
    )

    assert result["schema_id"] == "analyst_decision_logic_v1"
    assert "primary driver" not in result["support_summary"].lower()
    assert "byproduct of" not in result["counterweight_weighting"].lower()
    assert "crux for" not in result["reconciled_cruxes"][0].lower()
    assert "inherent property" not in result["do_not_overstate"][0].lower()
