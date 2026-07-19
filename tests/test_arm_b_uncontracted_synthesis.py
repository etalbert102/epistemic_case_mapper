from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_section_synthesis import (
    _deterministic_uncontracted_section,
    _strip_uncontracted_citations,
)


def test_section_synthesis_strips_citations_when_section_has_no_evidence_contract() -> None:
    markdown = "## Practical Implication\n\nApply the bounded answer [SRC_ALPHA] and update later {E:e1}."

    repaired = _strip_uncontracted_citations(markdown)

    assert repaired == "## Practical Implication\n\nApply the bounded answer and update later."


def test_uncontracted_practical_section_is_rendered_without_model_evidence() -> None:
    section = {
        "packet": {
            "decision_anchor": {
                "bounded_answer": "Option A is the current default. However, narrower settings need separate review.",
                "confidence": "medium",
                "scope_boundaries": ["Narrower settings need separate review."],
            }
        }
    }

    markdown = _deterministic_uncontracted_section("Practical Implication", section)

    assert markdown.startswith("## Practical Implication\n")
    assert "Confidence: medium" in markdown
    assert "Update the guidance when direct outcome evidence" in markdown
    assert "[" not in markdown
