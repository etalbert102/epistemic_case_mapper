from __future__ import annotations

import re

import pytest

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import run_memo_ready_packet_synthesis
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_evidence_anchoring import (
    build_evidence_expression_contracts,
    build_evidence_reconciliation_report,
    contracts_for_section,
    render_evidence_tagged_memo,
    unknown_evidence_ids_in_text,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_entailment import collect_packet_source_evidence_by_source
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_decision_briefing_packet import _scaffold


def test_evidence_expression_contracts_derive_required_slots() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "must_use": True,
                "obligation_level": "must_include",
                "reader_claim": "Option A reduces losses.",
                "role": "strongest_support",
                "quantities": [{"value": "25%", "interpretation": "loss reduction"}],
                "caveat": "Comparable cities only",
                "source_ids": ["s1"],
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "evidence_item_ids": ["e1"],
                    "source_ids": ["s1"],
                    "statement": "Use Option A support.",
                }
            ],
            "evidence_language_contracts": [
                {
                    "item_id": "e1",
                    "avoid_language": ["proves"],
                    "must_qualify_with": ["observational"],
                    "source_ids": ["s1"],
                }
            ],
        },
    }

    contracts = build_evidence_expression_contracts(packet)

    assert contracts[0]["evidence_id"] == "e1"
    assert contracts[0]["required"] is True
    assert contracts[0]["source_ids"] == ["s1"]
    assert contracts[0]["required_quantity_atoms"][0]["value"] == "25%"
    assert contracts[0]["population_scope"] == "Comparable cities only"
    assert contracts[0]["must_not_imply"] == ["proves"]


def test_evidence_expression_contracts_include_source_specific_excerpt_controls() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "The intervention changed the measured marker.",
                "source_ids": ["s1"],
                "source_excerpt": "The intervention group had a higher marker concentration after two months.",
            }
        ]
    }

    contracts = build_evidence_expression_contracts(packet)

    assert contracts[0]["source_evidence"] == [
        {
            "source_id": "s1",
            "excerpts": ["The intervention group had a higher marker concentration after two months."],
        }
    ]


def test_evidence_expression_contracts_include_numeric_must_preserve_terms() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "Comparator evidence bounds the answer.",
                "role": "strongest_counterweight",
                "source_ids": ["s1"],
                "quantities": [{"value": "1.15", "interpretation": "hazard ratio"}],
                "must_preserve_terms": [
                    "hazard ratio 1.15 with 95% confidence interval 1.05 to 1.27",
                    "secondary estimate 8.14",
                    "observational evidence",
                ],
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "canonical_decision_writer_packet": {},
    }

    contracts = build_evidence_expression_contracts(packet)

    quantities = contracts[0]["required_quantity_atoms"]
    assert any("1.15" in row["value"] and "1.05 to 1.27" in row["value"] for row in quantities)
    assert not any("8.14" in row["value"] for row in quantities)
    assert contracts[0]["must_preserve_terms"][0].startswith("hazard ratio 1.15")


def test_evidence_reconciliation_warns_when_required_quantity_missing_near_tag() -> None:
    contracts = [
        {
            "evidence_id": "e1",
            "required": True,
            "required_quantity_atoms": [{"value": "25%", "interpretation": "loss reduction"}],
        }
    ]

    report = build_evidence_reconciliation_report(
        "## Why\n\nThe study supports the answer {E:e1}.",
        "## Why\n\nThe study supports the answer [s1].",
        contracts,
    )

    assert report["status"] == "warning"
    assert report["quantity_warning_count"] == 1
    assert report["quantity_warnings"][0]["missing_quantity_near_tag"] == "25%"


def test_evidence_reconciliation_accepts_quantity_on_one_repeated_tag_expression() -> None:
    contracts = [
        {
            "evidence_id": "e1",
            "required": True,
            "required_quantity_atoms": [{"value": "1.15", "interpretation": "hazard ratio"}],
        }
    ]

    report = build_evidence_reconciliation_report(
        (
            "## Why\n\n"
            "Comparator evidence reports a hazard ratio of 1.15 {E:e1}. "
            "The same evidence also bounds the recommendation {E:e1}."
        ),
        "rendered",
        contracts,
    )

    assert report["status"] == "ready"
    assert report["quantity_warning_count"] == 0


def test_evidence_expression_contracts_do_not_hard_require_soft_quantity_obligations() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "The biomarker evidence bounds the answer.",
                "role": "strongest_counterweight",
                "source_ids": ["s1"],
                "lineage": {"covered_evidence_item_ids": ["claim:one"]},
                "quantities": [{"value": "0.14", "interpretation": "primary ratio"}],
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "quantity_obligation_plan": {
            "rows": [
                {
                    "source_evidence_item_id": "claim:one",
                    "value": "8.14",
                    "memo_use": "yes",
                    "must_retain": False,
                    "retention_phrase": "secondary concentration endpoint",
                }
            ]
        },
        "canonical_decision_writer_packet": {},
    }

    contracts = build_evidence_expression_contracts(packet)
    quantities = contracts[0]["required_quantity_atoms"]

    assert any(row["value"] == "0.14" for row in quantities)
    assert not any(row["value"] == "8.14" for row in quantities)


def test_evidence_expression_contracts_dedupe_quantity_obligations_by_assertion_bundle() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "Subgroup risk bounds the answer.",
                "source_ids": ["s1"],
                "quantities": [
                    {
                        "value": "1.40",
                        "evidence_bundle_id": "bundle_a",
                        "assertion_bundle": {
                            "evidence_bundle_id": "bundle_a",
                            "endpoint": "relative risk",
                            "value": "1.40",
                        },
                    }
                ],
            }
        ],
        "quantity_obligation_plan": {
            "quantity_obligations": [
                {
                    "target_item_ids": ["e1"],
                    "value": "1.40",
                    "source_ids": ["s1"],
                    "analyst_quantity_relevance": {"quantity_value": "1.40"},
                }
            ]
        },
    }

    contracts = build_evidence_expression_contracts(packet)
    quantities = contracts[0]["required_quantity_atoms"]

    assert [row.get("value") for row in quantities] == ["1.40"]


def test_evidence_expression_contracts_resolve_source_ids_from_labels() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "A biomarker worsens.",
                "role": "strongest_counterweight",
                "source_labels": ["Biomarker Trial"],
            }
        ],
        "source_trail": [{"source_id": "s_bio", "source_label": "Biomarker Trial"}],
        "canonical_decision_writer_packet": {},
    }

    contracts = build_evidence_expression_contracts(packet)

    assert contracts[0]["source_ids"] == ["s_bio"]
    assert contracts[0]["required"] is True


def test_contracts_for_section_uses_nested_section_local_evidence_ids() -> None:
    packet = {
        "evidence_items": [
            {"item_id": "decision_writer_item_001", "reader_claim": "Primary answer support.", "source_ids": ["s1"], "must_use": True},
            {"item_id": "decision_writer_item_002", "reader_claim": "Answer calibration.", "source_ids": ["s2"]},
            {"item_id": "decision_writer_item_007", "reader_claim": "Practical monitoring boundary.", "source_ids": ["s3"]},
            {"item_id": "decision_writer_item_011", "reader_claim": "Practical guidance.", "source_ids": ["s4"], "must_use": True},
        ],
        "source_trail": [
            {"source_id": "s1", "source_label": "Source One"},
            {"source_id": "s2", "source_label": "Source Two"},
            {"source_id": "s3", "source_label": "Source Three"},
            {"source_id": "s4", "source_label": "Source Four"},
        ],
        "canonical_decision_writer_packet": {},
    }
    section_packet = {
        "section_id": "practical_implication",
        "heading": "Practical Implication",
        "decision_usefulness_moves": {
            "recommended_stance": {"evidence_item_ids": ["decision_writer_item_001", "decision_writer_item_002"]},
            "tradeoffs": [{"evidence_item_ids": ["decision_writer_item_007"]}],
        },
        "evidence_context": [{"item_id": "decision_writer_item_011"}],
    }

    contracts = contracts_for_section(section_packet, "Practical Implication", build_evidence_expression_contracts(packet))

    assert [row["evidence_id"] for row in contracts] == [
        "decision_writer_item_001",
        "decision_writer_item_002",
        "decision_writer_item_007",
        "decision_writer_item_011",
    ]
    by_id = {row["evidence_id"]: row for row in contracts}
    assert by_id["decision_writer_item_001"]["required"] is False
    assert by_id["decision_writer_item_011"]["required"] is True


def test_contracts_for_section_treats_decision_argument_section_as_allowed_context() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "support",
                "reader_claim": "Primary answer support.",
                "role": "strongest_support",
                "source_ids": ["s1"],
                "must_use": True,
            },
            {
                "item_id": "counterweight",
                "reader_claim": "Biomarker evidence bounds the answer.",
                "role": "strongest_counterweight",
                "source_ids": ["s2"],
                "must_use": True,
            },
        ],
        "source_trail": [
            {"source_id": "s1", "source_label": "Outcome Study"},
            {"source_id": "s2", "source_label": "Biomarker Trial"},
        ],
        "canonical_decision_writer_packet": {},
    }
    section_packet = {
        "section_id": "answer_evidence",
        "heading": "Why This Is the Best Current Read",
        "evidence_context": [{"item_id": "support"}],
        "decision_argument_section": {
            "required_evidence_item_ids": ["support", "counterweight"],
            "owned_moves": [
                {"move_id": "primary_support", "evidence_item_ids": ["support"]},
                {"move_id": "quantity_calibration", "evidence_item_ids": ["counterweight"]},
            ],
        },
    }

    contracts = contracts_for_section(
        section_packet,
        "Why This Is the Best Current Read",
        build_evidence_expression_contracts(packet),
    )
    by_id = {row["evidence_id"]: row for row in contracts}

    assert by_id["support"]["required"] is True
    assert by_id["counterweight"]["required"] is False


def test_render_evidence_tags_to_source_citations_and_trace() -> None:
    rendered = render_evidence_tagged_memo(
        "## Why\n\nOption A reduced losses {E:e1}. Option B is bounded {e1, e2}. Source-level context {s2}.\n",
        [
            {"evidence_id": "e1", "source_ids": ["s1"], "claim": "Option A reduces losses."},
            {"evidence_id": "e2", "source_ids": ["s2"], "claim": "Option B is bounded."},
        ],
    )

    assert "{E:e1}" not in rendered["memo"]
    assert "{e1, e2}" not in rendered["memo"]
    assert "{s2}" not in rendered["memo"]
    assert "[s1]" in rendered["memo"]
    assert "[s1, s2]" in rendered["memo"]
    assert "[s2]" in rendered["memo"]
    assert rendered["trace"][0]["evidence_id"] == "e1"
    assert rendered["trace"][0]["source_ids"] == ["s1"]


def test_render_evidence_tags_normalizes_zero_padded_evidence_ids() -> None:
    rendered = render_evidence_tagged_memo(
        "## Why\n\nThe boundary matters {E:decision_writer_item_11}.\n",
        [{"evidence_id": "decision_writer_item_011", "source_ids": ["s1"], "claim": "Boundary claim."}],
    )

    assert "{E:" not in rendered["memo"]
    assert "[s1]" in rendered["memo"]
    assert rendered["trace"][0]["evidence_id"] == "decision_writer_item_011"


def test_unknown_evidence_id_detector_flags_demoted_brace_tags() -> None:
    contracts = [{"evidence_id": "decision_writer_item_052", "source_ids": ["s1"], "claim": "Boundary claim."}]
    memo = "## Why\n\nKnown evidence {decision_writer_item_052}. Demoted evidence {decision_writer_item_021}. Source context {s1}."

    unknown = unknown_evidence_ids_in_text(memo, contracts, known_source_ids={"s1"})

    assert unknown == ["decision_writer_item_021"]


def test_unknown_evidence_id_detector_flags_source_id_inside_evidence_tag() -> None:
    contracts = [{"evidence_id": "e1", "source_ids": ["SRC_A"], "claim": "Known claim."}]
    memo = "## Why\n\nThe writer confused a source ID for an evidence tag {E:SRC_A}. Source context {SRC_A}."

    unknown = unknown_evidence_ids_in_text(memo, contracts, known_source_ids={"SRC_A"})

    assert unknown == ["SRC_A"]


def test_reconciliation_flags_adjacent_source_evidence_mismatch() -> None:
    contracts = [
        {"evidence_id": "e_support", "source_ids": ["s_support"], "claim": "Support claim.", "required": True},
        {"evidence_id": "e_boundary", "source_ids": ["s_boundary"], "claim": "Boundary claim.", "required": True},
    ]
    tagged = "## Why\n\nThe boundary estimate belongs to the boundary source {E:e_support} [s_boundary]. Boundary claim {E:e_boundary}."

    report = build_evidence_reconciliation_report(tagged, tagged, contracts)

    assert report["status"] == "warning"
    assert report["source_mismatch_warning_count"] == 1
    assert report["source_mismatch_warnings"][0]["evidence_ids"] == ["e_support"]


def test_renderer_selects_source_specific_support_for_composite_evidence_tag() -> None:
    contracts = [
        {
            "evidence_id": "e_composite",
            "source_ids": ["s_cohort", "s_trial"],
            "citation_source_ids": ["s_cohort"],
            "claim": "The evidence includes both cohort outcomes and an endothelial trial.",
        }
    ]
    tagged = (
        "A single dose did not change endothelial function "
        "(0.4 ± 1.9 vs. 0.4 ± 2.4%, p = 0.99) {E:e_composite}."
    )

    rendered = render_evidence_tagged_memo(
        tagged,
        contracts,
        source_evidence_by_source={
            "s_cohort": ["Daily exposure was associated with an HR of 0.89 for cardiovascular disease."],
            "s_trial": ["A single dose did not change endothelial function compared with control (p = 0.99)."],
        },
    )

    assert "[s_trial]" in rendered["memo"]
    assert "[s_cohort]" not in rendered["memo"]
    assert rendered["trace"][0]["citation_selection_basis"] == "source_specific_claim_support"


def test_renderer_prefers_exact_quantity_source_over_broad_endpoint_overlap() -> None:
    contracts = [
        {
            "evidence_id": "e_composite",
            "source_ids": ["s_exact", "s_broad"],
            "citation_source_ids": ["s_broad"],
            "claim": "Composite cardiovascular evidence.",
        }
    ]
    tagged = "Daily exposure was associated with lower cardiovascular risk (HR 0.89) {E:e_composite}."

    rendered = render_evidence_tagged_memo(
        tagged,
        contracts,
        source_evidence_by_source={
            "s_exact": ["Daily exposure was associated with lower CVD risk (HR 0.89)."],
            "s_broad": ["Overall cardiovascular markers did not worsen in the intervention group."],
        },
    )

    assert "[s_exact]" in rendered["memo"]
    assert "[s_broad]" not in rendered["memo"]


def test_renderer_prefers_distinctive_endpoint_over_generic_word_overlap() -> None:
    contracts = [
        {
            "evidence_id": "e_composite",
            "source_ids": ["s_plaque", "s_development"],
            "citation_source_ids": ["s_development"],
            "claim": "Composite observational evidence.",
        }
    ]
    tagged = "Moderate exposure was associated with an 11% reduction in plaque development {E:e_composite}."

    rendered = render_evidence_tagged_memo(
        tagged,
        contracts,
        source_evidence_by_source={
            "s_plaque": ["Increasing exposure was inversely associated with plaque presence and area."],
            "s_development": ["The intervention supported healthy development in the overall cohort."],
        },
    )

    assert "[s_plaque]" in rendered["memo"]
    assert "[s_development]" not in rendered["memo"]


def test_renderer_keeps_contract_fallback_without_source_specific_evidence() -> None:
    contracts = [
        {
            "evidence_id": "e1",
            "source_ids": ["s1", "s2"],
            "citation_source_ids": ["s2"],
            "claim": "A supported claim.",
        }
    ]

    rendered = render_evidence_tagged_memo("A supported claim {E:e1}.", contracts)

    assert "[s2]" in rendered["memo"]
    assert rendered["trace"][0]["citation_selection_basis"] == "contract_fallback"


def test_reconciliation_allows_adjacent_source_lists_that_overlap_the_evidence_contract() -> None:
    contracts = [
        {"evidence_id": "e_support", "source_ids": ["s_support"], "claim": "Support claim.", "required": True},
        {"evidence_id": "e_boundary", "source_ids": ["s_boundary"], "claim": "Boundary claim.", "required": True},
    ]
    tagged = (
        "## Why\n\n"
        "The support claim is discussed with nearby context {E:e_support} [s_support, s_boundary]. "
        "Boundary claim {E:e_boundary}."
    )

    report = build_evidence_reconciliation_report(tagged, tagged, contracts)

    assert report["source_mismatch_warning_count"] == 0


def test_reconciliation_flags_unsupported_quantity_near_evidence_tag() -> None:
    contracts = [
        {
            "evidence_id": "e_moderate",
            "source_ids": ["s_moderate"],
            "claim": "Moderate egg consumption up to one egg/day is not associated with cardiovascular disease risk.",
            "required": True,
        }
    ]
    tagged = "## Why\n\nEach additional 300 mg of cholesterol was associated with risk {E:e_moderate}."

    report = build_evidence_reconciliation_report(tagged, tagged, contracts)

    assert report["status"] == "warning"
    assert report["unsupported_quantity_warning_count"] == 1
    assert report["unsupported_quantity_warnings"][0]["unsupported_quantities"] == ["300 mg"]


def test_reconciliation_flags_unsupported_untagged_quantity_in_tagged_section() -> None:
    contracts = [
        {
            "evidence_id": "e_moderate",
            "source_ids": ["s_moderate"],
            "claim": "Moderate egg consumption up to one egg/day is not associated with cardiovascular disease risk.",
            "required": True,
        }
    ]
    tagged = (
        "## Why\n\n"
        "Each additional 300 mg of cholesterol was associated with risk. "
        "Moderate intake up to one egg/day was not associated with risk {E:e_moderate}."
    )

    report = build_evidence_reconciliation_report(tagged, tagged, contracts)

    assert report["status"] == "warning"
    assert report["untagged_unsupported_quantity_warning_count"] == 1
    assert report["untagged_unsupported_quantity_warnings"][0]["unsupported_quantities"] == ["300 mg"]


def test_reconciliation_allows_quantity_supported_by_another_tag_in_sentence() -> None:
    contracts = [
        {
            "evidence_id": "e_dose",
            "source_ids": ["s_dose"],
            "claim": "Increased egg intake greater than 1 egg/day may increase LDL cholesterol.",
            "required": True,
        },
        {
            "evidence_id": "e_subgroup",
            "source_ids": ["s_subgroup"],
            "claim": "High egg consumption was associated with higher cardiovascular disease risk in people with type 2 diabetes.",
            "required": True,
        },
    ]
    tagged = "## Bounds\n\nIncreased intake greater than 1 egg/day may increase LDL {E:e_dose}, and diabetes changes subgroup risk {E:e_subgroup}."

    report = build_evidence_reconciliation_report(tagged, tagged, contracts)

    assert report["unsupported_quantity_warning_count"] == 0


def test_reconciliation_allows_quantity_from_controlling_source_excerpt() -> None:
    contracts = [
        {
            "evidence_id": "e_profile",
            "source_ids": ["s_profile"],
            "claim": "Higher intake was associated with a better lipid profile.",
            "source_evidence": [
                {"source_id": "s_profile", "excerpts": ["Participants consumed up to 1 egg per week."]}
            ],
            "required": True,
        }
    ]
    tagged = "## Evidence\n\nParticipants consuming up to 1 egg per week had a better lipid profile {E:e_profile}."

    report = build_evidence_reconciliation_report(tagged, tagged, contracts)

    assert report["unsupported_quantity_warning_count"] == 0


def test_source_evidence_collector_accepts_verbatim_assertion_bundle_quote() -> None:
    packet = {
        "quantity": {
            "source_ids": ["s1"],
            "source_quote": "Each additional 300 mg/day was associated with HR 1.19.",
        }
    }

    evidence = collect_packet_source_evidence_by_source(packet)

    assert evidence == {"s1": ["Each additional 300 mg/day was associated with HR 1.19."]}


def test_reconciliation_does_not_parse_type_2_diabetes_as_quantity() -> None:
    contracts = [
        {
            "evidence_id": "e_subgroup",
            "source_ids": ["s_subgroup"],
            "claim": "Risk differed in people with type 2 diabetes.",
            "required": True,
        }
    ]
    tagged = "## Bounds\n\nRisk differed in people with type 2 diabetes {E:e_subgroup}."

    report = build_evidence_reconciliation_report(tagged, tagged, contracts)

    assert report["unsupported_quantity_warning_count"] == 0


def test_memo_ready_synthesis_uses_unified_evidence_tag_path(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    prompts: list[str] = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        heading = _heading_from_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        if ids:
            tags = " ".join(f"{{E:{evidence_id}}}" for evidence_id in ids)
            body = f"The section makes its decision-relevant point with a 25% anchored effect {tags}."
        else:
            body = "Weight Outcome Study most while using Counter Study and Boundary Report to bound the answer [s1, s2, s3]."
        return ModelBackendResult(text=f"## {heading}\n\n{body}\n", backend="fake")

    import epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization as finalization

    monkeypatch.setattr(finalization, "run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["synthesis_mode"] == "unified_section_synthesis"
    assert result["report"]["used_default_path"] is False
    assert result["evidence_expression_contracts"]
    assert result["evidence_trace"]
    assert result["evidence_tag_section_reports"]
    assert any("### Evidence expression contracts" in prompt for prompt in prompts)
    assert any("section-local evidence contracts" in prompt for prompt in prompts)
    assert any("### Source weighting notes" in prompt for prompt in prompts if "### Evidence expression contracts" in prompt)
    assert "{E:" not in result["memo"]
    assert result["report"]["evidence_reconciliation_report"]["used_evidence_id_count"] >= 1


def _heading_from_prompt(prompt: str) -> str:
    match = re.search(r"exactly(?: with)?: ## (.+)", prompt)
    if not match:
        match = re.search(r"Output starts exactly with: ## (.+)", prompt)
    return match.group(1).strip() if match else "Why This Is the Best Current Read"
