from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_section_synthesis import (
    _deterministic_uncontracted_section,
    _section_has_blocking_failure,
    _strip_uncontracted_citations,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_citation_validation import (
    section_citation_validation_issues,
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
    assert "Option A is the current default" not in markdown
    assert "Do not turn study-specific exposure signals into a universal cutoff" in markdown
    assert "Update the guidance when direct outcome evidence" in markdown
    assert "[" not in markdown


def test_section_citation_validation_blocks_composite_endpoint_overreach() -> None:
    contracts = [
        {
            "evidence_id": "e1",
            "source_ids": ["s1"],
            "citation_source_ids": ["s1"],
            "role": "strongest_support",
            "required_quantity_atoms": [{"value": "13%", "source_ids": ["s1"]}],
            "source_evidence": [
                {"source_id": "s1", "excerpts": ["The odds of dyslipidemia were 13% lower."]}
            ],
        }
    ]
    tagged = (
        "## Why This Is the Best Current Read\n\n"
        "Endothelial function improved and dyslipidemia odds were 13% lower {E:e1}."
    )

    issues = section_citation_validation_issues(tagged, contracts)

    assert issues == ["citation_claim_entailment_mismatch:s1"]
    assert _section_has_blocking_failure({"issues": issues}) is True
