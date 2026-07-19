from epistemic_case_mapper.pipeline.briefing.map_briefing_synthesis_logic import (
    build_synthesis_constraints,
    controlling_source_excerpt,
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


def test_source_excerpt_calibrates_observational_causality_and_formatting() -> None:
    excerpt = controlling_source_excerpt(
        {
            "claim_context": {"evidence_design": "Prospective cohort"},
            "source_evidence": [
                {
                    "source_id": "s1",
                    "excerpts": [
                        "In multivariable-adjusted analysis, intake > 4/week led to an increased risk "
                        "(Hazard ratio [HR] = 1.50; 95%CI 1.13–1.99)."
                    ],
                }
            ],
        }
    )

    assert excerpt == (
        "In multivariable-adjusted analysis, intake > 4/week was associated with increased risk "
        "(hazard ratio (HR) 1.50; 95% CI 1.13–1.99)."
    )


def test_source_excerpt_restores_observational_population_scope() -> None:
    excerpt = controlling_source_excerpt(
        {
            "claim_context": {
                "evidence_design": "Prospective cohort study",
                "population": "461,213 Chinese adults aged 30–79 years",
            },
            "must_preserve_terms": ["Chinese adults"],
            "source_evidence": [{"source_id": "s1", "excerpts": ["Daily use was associated with lower risk."]}],
        }
    )

    assert excerpt == "Among Chinese adults, daily use was associated with lower risk."


def test_source_excerpt_restores_distinctive_population_without_preserve_term() -> None:
    excerpt = controlling_source_excerpt(
        {
            "claim_context": {
                "evidence_design": "Cross-sectional study",
                "population": "Greek national representative adult sample",
            },
            "source_evidence": [{"source_id": "s1", "excerpts": ["Frequent use was associated with lower odds."]}],
        }
    )

    assert excerpt == (
        "Among Greek national representative adult sample, frequent use was associated with lower odds."
    )


def test_source_excerpt_restores_trial_population_and_duration() -> None:
    excerpt = controlling_source_excerpt(
        {
            "claim_context": {
                "evidence_design": "Meta-analysis of randomized controlled trials",
                "population": "Healthy subjects without metabolic disease",
                "stated_dose_or_threshold": "> 2 months",
            },
            "must_preserve_terms": ["healthy subjects", "> 2 months"],
            "source_evidence": [
                {"source_id": "s1", "excerpts": ["A meta-analysis of 13 RCTs found that the marker increased."]}
            ],
        }
    )

    assert excerpt == (
        "A meta-analysis of 13 RCTs, conducted in healthy subjects over more than 2 months, "
        "found that the marker increased."
    )


def test_source_excerpt_restores_mean_difference_unit() -> None:
    excerpt = controlling_source_excerpt(
        {
            "must_preserve_terms": ["MD = 8.48 mg/dL"],
            "source_evidence": [
                {"source_id": "s1", "excerpts": ["The marker was higher (MD = 8.14; 95% CI 4.46 to 11.82)."]}
            ],
        }
    )

    assert excerpt == "The marker was higher (MD = 8.14 mg/dL; 95% CI 4.46 to 11.82)."


def test_source_excerpt_calibrates_nonsignificant_effect_wording() -> None:
    excerpt = controlling_source_excerpt(
        {
            "source_evidence": [
                {
                    "source_id": "s1",
                    "excerpts": ["A review found nonsignificant effects of increased use on clinical markers."],
                }
            ]
        }
    )

    assert excerpt == "A review did not detect statistically significant changes in clinical markers from increased use."


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
