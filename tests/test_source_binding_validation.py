from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import (
    _repair_missing_bound_source_citations,
    build_memo_ready_packet_retention_report,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_section_notes import render_memo_ready_section_markdown_notes
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_bound_evidence import (
    build_source_bound_evidence_atoms,
    source_bound_quantity_phrases,
)


def test_source_bound_atoms_exclude_quantities_not_found_in_local_excerpt() -> None:
    rows = [
        {
            "item_id": "lipid_ratio",
            "claim": "Higher egg intake changed lipid markers.",
            "source_ids": ["li_2020"],
            "quantities": [
                {
                    "value": "MD = 8.14",
                    "interpretation": "Mean Difference of 8.14 in the LDL-c/HDL-c ratio",
                    "source_ids": ["li_2020"],
                    "source_excerpt": "The MEC group had a higher LDL-c/HDL-c ratio than control (MD = 0.14, p = 0.001).",
                },
                {
                    "value": "0.14",
                    "interpretation": "Mean difference in the LDL-c/HDL-c ratio",
                    "source_ids": ["li_2020"],
                    "source_excerpt": "The MEC group had a higher LDL-c/HDL-c ratio than control (MD = 0.14, p = 0.001).",
                },
            ],
        }
    ]

    atoms = build_source_bound_evidence_atoms(rows)

    assert atoms[0]["quantity_tuples"][0]["value"] == "0.14"
    assert atoms[0]["excluded_quantity_tuples"][0]["value"] == "MD = 8.14"
    assert atoms[0]["excluded_quantity_tuples"][0]["warning_type"] == "quantity_not_found_in_source_excerpt"


def test_deterministic_source_citation_repair_only_anchors_retained_claim() -> None:
    memo = "## Why This Is the Best Current Read\n\nA single dose did not impair endothelial function [s_other].\n"
    retention = {
        "issues": [
            {
                "claim_retained": True,
                "source_retained": False,
                "source_ids": ["s_expected"],
                "statement": "A single dose did not impair endothelial function.",
                "validation_terms": ["single", "dose", "impair", "endothelial", "function"],
                "missing_quantities": [],
            }
        ]
    }

    repaired, report = _repair_missing_bound_source_citations(memo, retention)

    assert "function [s_other] [s_expected]." in repaired
    assert report["repair_count"] == 1


def test_source_bound_atoms_preserve_applicability_scope_for_subgroup_quantities() -> None:
    rows = [
        {
            "item_id": "subgroup_effect",
            "claim": "The effect was stronger in participants with baseline risk.",
            "source_ids": ["s1"],
            "source_excerpt": "Among participants with baseline risk, the adjusted HR was 1.25.",
            "quantities": [
                {
                    "value": "1.25",
                    "interpretation": "Adjusted HR in participants with baseline risk",
                    "source_ids": ["s1"],
                    "source_excerpt": "Among participants with baseline risk, the adjusted HR was 1.25.",
                }
            ],
        }
    ]

    atoms = build_source_bound_evidence_atoms(rows)

    assert atoms[0]["applicability_scope"] == "Among participants with baseline risk"
    assert atoms[0]["quantity_tuples"][0]["applicability_scope"] == "in participants with baseline risk"


def test_source_bound_atoms_derive_generic_citation_roles_and_use_limits() -> None:
    rows = [
        {
            "item_id": "boundary_source",
            "claim": "The answer is bounded in high-risk subgroups.",
            "source_ids": ["s_boundary"],
            "main_use": "bounds_answer",
            "memo_weight_sentence": "Use this source to bound the recommendation.",
            "reader_facing_limit": "Do not use as direct support for broad safety.",
        },
        {
            "item_id": "quantity_source",
            "claim": "The estimate calibrates the size of the effect.",
            "source_ids": ["s_quantity"],
            "reader_evidence_role": "calibrates magnitude",
        },
    ]

    atoms = build_source_bound_evidence_atoms(rows)

    assert atoms[0]["citation_role"] == "boundary"
    assert atoms[0]["use_for"] == "Use this source to bound the recommendation."
    assert atoms[0]["do_not_use_for"] == ["Do not use as direct support for broad safety."]
    assert atoms[1]["citation_role"] == "calibration"


def test_section_markdown_notes_render_citation_jobs_for_writer() -> None:
    notes = render_memo_ready_section_markdown_notes(
        {
            "heading": "Why This Is the Best Current Read",
            "section_job": "Explain the support and boundary evidence.",
            "top_context": {"decision_question": "Should option A be adopted?"},
            "source_bound_evidence_atoms": [
                {
                    "claim": "Option A reduced losses in the main study.",
                    "source_ids": ["s1"],
                    "allowed_citations": ["s1"],
                    "citation_role": "direct_support",
                    "use_for": "Use for the main support sentence.",
                },
                {
                    "claim": "The effect may not generalize to high-risk sites.",
                    "source_ids": ["s2"],
                    "allowed_citations": ["s2"],
                    "citation_role": "boundary",
                    "do_not_use_for": ["Do not cite on the broad support sentence."],
                },
            ],
        },
        known_source_ids=["s1", "s2"],
    )

    assert "Citation job: direct support" in notes
    assert "Use for: Use for the main support sentence." in notes
    assert "Citation job: boundary" in notes
    assert "Use limit: Do not cite on the broad support sentence." in notes


def test_retention_report_flags_quantity_without_bound_source_nearby() -> None:
    packet = {
        "source_trail": [
            {"source_id": "s1", "source_label": "Outcome Study"},
            {"source_id": "s2", "source_label": "Context Review"},
        ],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "statement": "Option A reduced losses by 25%.",
                    "source_ids": ["s1"],
                    "quantities": [
                        {
                            "value": "25%",
                            "interpretation": "loss reduction",
                            "source_ids": ["s1"],
                            "source_excerpt": "Option A reduced losses by 25%.",
                        }
                    ],
                }
            ]
        },
    }
    memo = "Option A reduced losses by 25% [s2]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    binding = report["source_binding_report"]
    assert binding["quantity_source_adjacency_warning_count"] == 1
    assert binding["quantity_source_adjacency_warnings"][0]["quantity"] == "25%"
    assert binding["quantity_source_adjacency_warnings"][0]["expected_source_ids"] == ["s1"]
    assert report["status"] == "warning"
    assert report["source_binding_issue_count"] >= 1
    assert report["missing_critical_count"] >= 1
    assert report["missing_mandatory_count"] >= 1
    assert any(
        issue["issue_type"] == "source_binding_mismatch"
        and issue["source_binding_warning_type"] == "quantity_without_bound_source_nearby"
        for issue in report["issues"]
    )


def test_source_binding_report_flags_role_mismatched_overbundled_citations() -> None:
    packet = {
        "source_trail": [
            {"source_id": "s_support", "source_label": "Support Study"},
            {"source_id": "s_boundary", "source_label": "Boundary Study"},
        ],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "statement": "Option A is not associated with increased risk in the general population.",
                    "source_ids": ["s_support"],
                    "main_use": "drives_answer",
                },
                {
                    "statement": "The answer is bounded in high-risk subgroups.",
                    "source_ids": ["s_boundary"],
                    "main_use": "bounds_answer",
                },
            ]
        },
    }
    memo = "Option A is not associated with increased risk in the general population [s_support, s_boundary]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    care = report["source_binding_report"]["citation_care_report"]
    warning_types = {row["warning_type"] for row in care["warnings"]}
    assert care["status"] == "warning"
    assert "overbundled_or_mixed_role_citation" in warning_types
    assert "citation_role_mismatch" in warning_types
    assert report["status"] == "warning"
    assert report["source_binding_issue_count"] == care["warning_count"]
    assert report["missing_critical_count"] >= care["warning_count"]
    assert any(
        issue["issue_type"] == "source_binding_mismatch"
        and issue["source_binding_warning_type"] == "citation_role_mismatch"
        for issue in report["issues"]
    )


def test_source_binding_report_accepts_boundary_source_on_boundary_sentence() -> None:
    packet = {
        "source_trail": [{"source_id": "s_boundary", "source_label": "Boundary Study"}],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "statement": "The answer is bounded in high-risk subgroups.",
                    "source_ids": ["s_boundary"],
                    "main_use": "bounds_answer",
                }
            ]
        },
    }
    memo = "The answer is bounded in high-risk subgroups [s_boundary]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    care = report["source_binding_report"]["citation_care_report"]
    assert care["warning_count"] == 0
    assert report["source_binding_issue_count"] == 0
    assert report["status"] == "ready"


def test_source_binding_report_uses_section_heading_for_boundary_role() -> None:
    packet = {
        "source_trail": [{"source_id": "s_boundary", "source_label": "Boundary Study"}],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [{"source_ids": ["s_boundary"], "main_use": "bounds_answer"}],
            "mandatory_retention_checklist": [
                {
                    "statement": "Higher exposure was associated with worse outcomes in one population.",
                    "source_ids": ["s_boundary"],
                    "main_use": "bounds_answer",
                }
            ],
        },
    }
    memo = "## What Could Change or Bound the Answer\n\nHigher exposure was associated with worse outcomes [s_boundary]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["source_binding_report"]["citation_care_report"]["warning_count"] == 0


def test_source_binding_report_preserves_heading_role_for_later_paragraph_sentences() -> None:
    packet = {
        "source_trail": [{"source_id": "s_boundary", "source_label": "Boundary Study"}],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [{"source_ids": ["s_boundary"], "main_use": "bounds_answer"}],
            "mandatory_retention_checklist": [
                {
                    "statement": "Positive markers were observed in one population.",
                    "source_ids": ["s_boundary"],
                    "main_use": "bounds_answer",
                }
            ],
        },
    }
    memo = (
        "## What Could Change or Bound the Answer\n\n"
        "The recommendation depends on the population. "
        "Positive markers were observed in one population [s_boundary]."
    )

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["source_binding_report"]["citation_care_report"]["warning_count"] == 0


def test_source_binding_flags_citation_without_source_specific_quantity_support() -> None:
    packet = {
        "source_trail": [
            {"source_id": "s_trial", "source_label": "Trial"},
            {"source_id": "s_cohort", "source_label": "Cohort"},
            {"source_id": "s_review", "source_label": "Review"},
        ],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                        "statement": "Endothelial function changed by 0.4 ± 1.9 vs. 0.4 ± 2.4%.",
                        "source_ids": ["s_trial", "s_cohort", "s_review"],
                    "source_excerpts": [
                        {
                            "source_ids": ["s_trial"],
                            "source_excerpt": "Endothelial function changed by 0.4 ± 1.9 vs. 0.4 ± 2.4% after the intervention.",
                        },
                        {
                            "source_ids": ["s_cohort"],
                            "source_excerpt": "Daily exposure was associated with an HR of 0.89 for cardiovascular disease.",
                        },
                        {
                            "source_ids": ["s_review"],
                            "source_excerpt": "Diet quality varied across the included observational studies.",
                        },
                    ],
                }
            ]
        },
    }
    memo = "Endothelial function changed by 0.4 ± 1.9 vs. 0.4 ± 2.4% [s_trial, s_cohort, s_review]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    warnings = report["source_binding_report"]["citation_care_report"]["warnings"]
    entailment = [row for row in warnings if row["warning_type"] == "citation_claim_entailment_mismatch"]
    assert [row["source_id"] for row in entailment] == ["s_cohort", "s_review"]
    assert entailment[0]["unmatched_quantities"] == ["0.4 ± 2.4%", "0.4 ± 1.9"]
    assert "endothelial function" in entailment[0]["citation_clause"].lower()
    assert entailment[0]["citation_clause"].endswith("2.4%")


def test_source_binding_flags_qualitative_citation_without_distinctive_term_support() -> None:
    packet = {
        "source_trail": [
            {"source_id": "s_tmao", "source_label": "TMAO Review"},
            {"source_id": "s_lipids", "source_label": "Lipid Trial"},
        ],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "statement": "Egg intake caused a temporary TMAO spike.",
                    "source_ids": ["s_tmao", "s_lipids"],
                    "source_excerpts": [
                        {"source_ids": ["s_tmao"], "source_excerpt": "Egg intake increased plasma TMAO after ingestion."},
                        {"source_ids": ["s_lipids"], "source_excerpt": "Plasma triacylglycerol increased after whole eggs."},
                    ],
                }
            ]
        },
    }
    memo = "Egg intake caused a temporary TMAO spike [s_tmao, s_lipids]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    warnings = report["source_binding_report"]["citation_care_report"]["warnings"]
    entailment = [row for row in warnings if row["warning_type"] == "citation_claim_entailment_mismatch"]
    assert [row["source_id"] for row in entailment] == ["s_lipids"]


def test_source_binding_skips_entailment_when_source_specific_evidence_is_unavailable() -> None:
    packet = {
        "source_trail": [{"source_id": "s1", "source_label": "Study"}],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {"statement": "The intervention improved outcomes by 25%.", "source_ids": ["s1"]}
            ]
        },
    }

    report = build_memo_ready_packet_retention_report("The intervention improved outcomes by 25% [s1].", packet)

    warnings = report["source_binding_report"]["citation_care_report"]["warnings"]
    assert not any(row["warning_type"] == "citation_claim_entailment_mismatch" for row in warnings)


def test_prioritized_source_role_overrides_stale_canonical_role() -> None:
    packet = {
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "prioritized_source_roles": {"s1": ["direct_support"]},
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [{"source_ids": ["s1"], "main_use": "bounds_answer"}],
            "mandatory_retention_checklist": [
                {"statement": "Option A supports the current answer.", "source_ids": ["s1"], "main_use": "drives_answer"}
            ],
        },
    }
    memo = "## Why This Is the Best Current Read\n\nStudy One supports the current answer [s1]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["source_binding_report"]["citation_care_report"]["warning_count"] == 0


def test_source_binding_report_accepts_plain_language_counterweights_and_scope_boundaries() -> None:
    packet = {
        "source_trail": [
            {"source_id": "s_counter", "source_label": "Counter Study"},
            {"source_id": "s_boundary", "source_label": "Boundary Study"},
        ],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "statement": "Option A failed when maintenance budgets were cut.",
                    "source_ids": ["s_counter"],
                    "main_use": "bounds_answer",
                },
                {
                    "statement": "The result only applies where pump capacity exceeds expected peak flow.",
                    "source_ids": ["s_boundary"],
                    "main_use": "bounds_answer",
                },
            ]
        },
    }
    memo = (
        "- Option A failed when maintenance budgets were cut. [Counter Study]\n"
        "- The result only applies where pump capacity exceeds expected peak flow. [Boundary Study]\n"
    )

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["source_binding_report"]["citation_care_report"]["warning_count"] == 0
    assert report["source_binding_issue_count"] == 0
    assert report["status"] == "ready"


def test_citation_care_prefers_analyst_source_weight_role_over_mixed_atom_roles() -> None:
    packet = {
        "source_trail": [{"source_id": "s1", "source_label": "Support Study"}],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["s1"],
                    "main_use": "drives_answer",
                    "why_weight_this_way": "Use as direct support for the current answer.",
                }
            ],
            "mandatory_retention_checklist": [
                {
                    "statement": "Option A is not associated with increased risk in the general population.",
                    "source_ids": ["s1"],
                    "main_use": "drives_answer",
                },
                {
                    "statement": "The same source also describes a subgroup boundary.",
                    "source_ids": ["s1"],
                    "main_use": "bounds_answer",
                },
            ],
        },
    }
    memo = "Option A is not associated with increased risk in the general population [s1]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    care = report["source_binding_report"]["citation_care_report"]
    assert care["warning_count"] == 0


def test_retention_report_accepts_quantity_with_bound_source_nearby() -> None:
    packet = {
        "source_trail": [{"source_id": "s1", "source_label": "Outcome Study"}],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "statement": "Option A reduced losses by 25%.",
                    "source_ids": ["s1"],
                    "quantities": [
                        {
                            "value": "25%",
                            "interpretation": "loss reduction",
                            "source_ids": ["s1"],
                            "source_excerpt": "Option A reduced losses by 25%.",
                        }
                    ],
                }
            ]
        },
    }
    memo = "Option A reduced losses by 25% [s1]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["source_binding_report"]["quantity_source_adjacency_warning_count"] == 0


def test_source_binding_validation_does_not_conflate_same_quantity_across_scopes() -> None:
    packet = {
        "source_trail": [
            {"source_id": "s_bmi", "source_label": "BMI Study"},
            {"source_id": "s_diabetes", "source_label": "Diabetes Study"},
        ],
        "analyst_quantity_binding_report": {
            "approved_bindings": [
                {
                    "candidate_id": "bmi_125",
                    "value": "1.25 (HR)",
                    "interpretation": "Risk increase in participants with lower BMI",
                    "memo_use": "yes",
                    "source_claim": "The association was stronger in participants with lower BMI.",
                    "source_excerpt": "In participants with lower BMI, the adjusted HR was 1.25.",
                    "source_ids": ["s_bmi"],
                },
                {
                    "candidate_id": "diabetes_125",
                    "value": "1.25",
                    "interpretation": "Relative risk in people with type 2 diabetes",
                    "memo_use": "yes",
                    "source_claim": "Risk was elevated in people with type 2 diabetes.",
                    "source_excerpt": "In people with type 2 diabetes, the relative risk was 1.25.",
                    "source_ids": ["s_diabetes"],
                },
            ]
        },
    }
    memo = "In people with type 2 diabetes, the relative risk was 1.25 [s_diabetes]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["source_binding_report"]["quantity_source_adjacency_warning_count"] == 0


def test_source_binding_validation_ignores_bare_numbers_inside_intervals() -> None:
    packet = {
        "source_trail": [
            {"source_id": "s_lipid", "source_label": "Lipid Trial"},
            {"source_id": "s_substitution", "source_label": "Substitution Study"},
        ],
        "analyst_quantity_binding_report": {
            "approved_bindings": [
                {
                    "candidate_id": "hdl_127",
                    "value": "1.27",
                    "interpretation": "HDL-c level",
                    "memo_use": "yes",
                    "source_claim": "Egg consumption did not significantly increase HDL-c levels.",
                    "source_excerpt": "The pooled HDL-c estimate was 1.27.",
                    "source_ids": ["s_lipid"],
                }
            ]
        },
    }

    interval_memo = (
        "Replacing one egg per day with processed red meat was associated with a hazard "
        "ratio of 1.15 (1.05 to 1.27) [s_substitution]."
    )
    standalone_memo = "The HDL-c estimate was 1.27 [s_substitution]."

    interval_report = build_memo_ready_packet_retention_report(interval_memo, packet)
    standalone_report = build_memo_ready_packet_retention_report(standalone_memo, packet)

    assert interval_report["source_binding_report"]["quantity_source_adjacency_warning_count"] == 0
    assert standalone_report["source_binding_report"]["quantity_source_adjacency_warning_count"] == 1


def test_source_bound_quantity_phrases_pair_estimates_with_confidence_intervals() -> None:
    row = {
        "claim": "Moderate exposure was not associated with adverse outcomes.",
        "source_ids": ["s1"],
        "quantities": [
            {
                "value": "0.93",
                "interpretation": "Hazard ratio for at least one exposure per day vs less than one exposure per month",
                "source_evidence_item_id": "claim:outcome",
                "source_ids": ["s1"],
            },
            {
                "value": "0.82 to 1.05",
                "interpretation": "Confidence interval for the hazard ratio",
                "source_evidence_item_id": "claim:outcome",
                "source_ids": ["s1"],
            },
        ],
    }

    phrases = source_bound_quantity_phrases(row)

    assert phrases == [
        "HR 0.93 (95% CI 0.82 to 1.05) for at least one exposure per day vs less than one exposure per month"
    ]


def test_source_bound_quantity_phrases_do_not_render_interval_as_estimate() -> None:
    row = {
        "claim": "The lipid marker increased.",
        "source_ids": ["s1"],
        "quantities": [
            {
                "value": "0.05 to 0.22",
                "interpretation": "Confidence interval for the mean difference",
                "source_evidence_item_id": "claim:lipid",
                "source_ids": ["s1"],
            }
        ],
    }

    phrases = source_bound_quantity_phrases(row)

    assert phrases == ["95% CI 0.05 to 0.22"]
