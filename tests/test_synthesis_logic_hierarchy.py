from epistemic_case_mapper.pipeline.briefing.map_briefing_synthesis_logic import (
    build_synthesis_constraints,
    expand_reader_abbreviations,
    repair_section_synthesis_logic,
    strip_redundant_post_tag_quantities,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_section_synthesis import (
    _normalize_relative_risk_surface,
)


def test_synthesis_logic_does_not_repeat_exposure_reconciliation_in_support_section() -> None:
    repaired = repair_section_synthesis_logic(
        "## Why This Is the Best Current Read\n\nSupported prose.",
        section_id="answer_evidence",
        contracts=[],
        packet={"synthesis_constraints": {"study_specific_exposure_surfaces": ["<1/day", ">4/week"]}},
    )

    assert "reported exposure ranges" not in repaired.lower()


def test_synthesis_logic_adds_required_evidence_hierarchy_thesis() -> None:
    packet = {
        "synthesis_constraints": {
            "required_decision_effect_sentence": (
                "Because the support is observational, it supports the bounded default but not a stronger conclusion."
            )
        }
    }

    repaired = repair_section_synthesis_logic(
        "## Why This Is the Best Current Read\n\nAn association was reported {E:e1}.",
        section_id="answer_evidence",
        contracts=[],
        packet=packet,
    )

    assert "Because the support is observational" in repaired


def test_relative_risk_surface_labels_hazard_ratio_and_interval() -> None:
    repaired = _normalize_relative_risk_surface(
        "Exposure was associated with a 1.19 (1.16–1.22) higher risk of the outcome."
    )

    assert repaired == "Exposure was associated with higher risk (HR 1.19; 95% CI 1.16–1.22) of the outcome."


def test_redundant_post_tag_quantity_is_removed_when_labeled_form_is_present() -> None:
    markdown = (
        "The outcome was 19% higher (HR 1.19; 95% CI 1.16–1.22) "
        "{E:e1} 1.19 (1.16–1.22)."
    )
    contracts = [{"evidence_id": "e1", "required_quantity_atoms": [{"value": "1.19 (1.16–1.22)"}]}]

    repaired = strip_redundant_post_tag_quantities(markdown, contracts)

    assert repaired == "The outcome was 19% higher (HR 1.19; 95% CI 1.16–1.22) {E:e1}."


def test_counterweight_thesis_marks_related_exposure_as_indirect() -> None:
    constraints = build_synthesis_constraints(
        [
            {"evidence_id": "e1", "claim": "A randomized review found no effect on an intermediate marker for option A."},
            {
                "evidence_id": "e2",
                "claim": "A related exposure was associated with mortality.",
                "must_qualify_with": ["observational evidence"],
            },
        ],
        {"decision_question": "Should option A be treated as neutral?", "confidence": "medium"},
        section_id="counterweights",
    )

    assert constraints["indirect_exposure_evidence_ids"] == ["e2"]
    assert "direct clinical-outcome evidence is observational" in constraints[
        "required_decision_effect_sentence"
    ]
    assert "randomized evidence concerns intermediate markers" in constraints["required_decision_effect_sentence"]


def test_synthesis_logic_qualifies_indirect_evidence_at_the_claim() -> None:
    repaired = repair_section_synthesis_logic(
        "## Bounds\n\nDietary exposure was associated with mortality {E:e2}.",
        section_id="counterweights",
        contracts=[],
        packet={"synthesis_constraints": {"indirect_exposure_evidence_ids": ["e2"]}},
    )

    assert "Indirectly, dietary exposure was associated with mortality {E:e2}." in repaired


def test_reader_abbreviations_expand_on_first_use() -> None:
    memo = "CVD incidence changed. LDL-c concentration changed. MD = 8.14. CVD remained bounded."

    expanded = expand_reader_abbreviations(memo)

    assert expanded == (
        "cardiovascular disease (CVD) incidence changed. LDL cholesterol (LDL-c) concentration changed. "
        "mean difference (MD) = 8.14. CVD remained bounded."
    )


def test_reader_abbreviations_expand_statistical_terms() -> None:
    expanded = expand_reader_abbreviations("Thirteen RCTs reported HR 1.19 with a 95% CI.")

    assert expanded == (
        "Thirteen randomized controlled trials (RCTs) reported hazard ratio (HR) 1.19 with a 95% confidence interval (CI)."
    )


def test_reader_abbreviations_define_the_first_use_when_a_later_definition_exists() -> None:
    expanded = expand_reader_abbreviations(
        "The estimate was HR 0.89. A later result reported hazard ratio (HR) 1.50."
    )

    assert expanded == "The estimate was hazard ratio (HR) 0.89. A later result reported HR 1.50."
