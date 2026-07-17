from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_ready_finalization import build_memo_ready_packet_retention_report
from epistemic_case_mapper.map_briefing_memo_ready_section_notes import render_memo_ready_section_markdown_notes
from epistemic_case_mapper.map_briefing_source_bound_evidence import (
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
