from __future__ import annotations

import pytest

from epistemic_case_mapper.main_memo_obligations import build_main_memo_obligation_ledger
from epistemic_case_mapper.map_briefing import build_gap_diagnosis, canonicalize_claims_for_briefing
from epistemic_case_mapper.map_briefing_map_utils import _expand_payload_reader_references
from epistemic_case_mapper.model_schemas import DecisionCrux


def test_claim_canonicalization_merges_duplicates_and_drops_fragments() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Moderate exposure was not associated with worse hard outcomes in the main cohort.",
                "source_id": "source_a",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "Moderate exposure was not associated with worse hard outcomes in the cohort.",
                "source_id": "source_b",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c003",
                "claim": "... respectively. In the table note",
                "source_id": "source_c",
                "role": "background",
            },
            {
                "claim_id": "c004",
                "claim": "A subgroup had higher risk at high exposure.",
                "source_id": "source_d",
                "role": "scope_limit",
            },
        ],
        "relations": [
            {"relation_id": "r001", "source_claim": "c002", "target_claim": "c004", "relation_type": "in_tension_with"},
            {"relation_id": "r002", "source_claim": "c003", "target_claim": "c001", "relation_type": "supports"},
        ],
    }

    canonical, report = canonicalize_claims_for_briefing(candidate_map)

    assert report["changed"] is True
    assert report["dropped_fragment_claim_ids"] == ["c003"]
    assert report["merged_duplicate_groups"][0]["representative_claim_id"] == "c001"
    assert report["claim_id_rewrites"] == {"c002": "c001"}
    assert {claim["claim_id"] for claim in canonical["claims"]} == {"c001", "c004"}
    assert canonical["relations"] == [
        {
            "relation_id": "r001",
            "source_claim": "c001",
            "target_claim": "c004",
            "relation_type": "in_tension_with",
            "canonicalized_from_relation_id": "r001",
        }
    ]


def test_gap_telemetry_flags_generic_crux_quality_even_with_relations() -> None:
    candidate_map = {
        "claims": [
            {"claim_id": "c001", "claim": "Implementation capacity determines whether the intervention works.", "role": "crux"},
            {"claim_id": "c002", "claim": "The intervention improves the target outcome.", "role": "conclusion_support"},
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c001",
                "target_claim": "c002",
                "relation_type": "crux_for",
            }
        ],
    }
    scaffold = {
        "decision_synthesis_model": {
            "schema_id": "decision_synthesis_model_v1",
            "evidence_lines": [],
            "central_tensions": [],
            "recommendations": [],
            "cruxes": [
                {
                    "crux": "Decision-changing condition",
                    "current_read": "The current packet treats this condition as relevant.",
                    "would_change_if": "New evidence showed the condition did not matter.",
                }
            ],
        },
        "evidence_weighting_ledger": {"all_evidence": []},
        "map_sufficiency_report": {},
        "quality_issues": [],
    }

    diagnosis = build_gap_diagnosis(
        question="Should the intervention be adopted?",
        candidate_map=candidate_map,
        prioritized_map=candidate_map,
        quality_report={"status": "usable_with_review", "issues": []},
        prioritization_report={},
        scaffold=scaffold,
        briefing_text="**Decision question:** Should the intervention be adopted?\n\nThe intervention may be adopted.",
        validation={"status": "passes_contract", "score": 100, "issues": []},
        polish_report={"status": "polished", "score": 100, "duplicate_sentence_count": 0},
        rewrite_report={"status": "accepted"},
    )

    crux_quality = diagnosis["relation_quality"]["crux_quality"]
    assert crux_quality["status"] == "needs_crux_work"
    assert crux_quality["generic_crux_count"] == 1
    assert any(driver["likely_stage"] == "relation_to_crux_synthesis" for driver in diagnosis["largest_gap_drivers"])


def test_main_memo_obligation_ledger_flags_missing_quantitative_and_baseline_terms() -> None:
    scaffold = {
        "source_display_names": {"source_a": "Meta Analysis 2025"},
        "argument_model": {
            "quantitative_anchors": [
                {
                    "statement": "The pooled estimate was RR 0.98 with 95% CI 0.93 to 1.03 across 1,720,108 participants.",
                    "why_it_matters": "Central quantitative anchor.",
                    "quantities": ["RR 0.98", "95% CI 0.93 to 1.03", "1,720,108 participants"],
                    "source_ids": ["source_a"],
                    "claim_ids": ["c001"],
                    "quantity_ids": ["qc0001"],
                }
            ],
            "scope_boundaries": [
                {
                    "statement": "High-risk subgroup needs separate handling.",
                    "source_ids": ["source_a"],
                    "claim_ids": ["c002"],
                }
            ],
        },
        "quantity_ledger": {
            "evidence_cards": [
                {
                    "card_id": "qc0001",
                    "claim_id": "c001",
                    "source": "Meta Analysis 2025",
                    "claim": "The pooled estimate was RR 0.98 with 95% CI 0.93 to 1.03.",
                    "key_quantities": ["RR 0.98", "95% CI 0.93 to 1.03"],
                    "interpretation_hint": "Interval includes the usual null value.",
                }
            ]
        },
        "evidence_weighting_ledger": {"all_evidence": []},
    }

    ledger = build_main_memo_obligation_ledger(
        scaffold=scaffold,
        briefing_text="The memo says the answer is neutral for the default population.",
        baseline_gap={
            "baseline_available": True,
            "salient_baseline_terms_absent": ["PROSPERITY trial", "ApoB"],
        },
        source_coverage={"baseline_source_like_terms_absent": ["PROSPERITY trial"]},
    )

    assert ledger["missing_from_memo_count"] >= 2
    assert ledger["source_missing_count"] == 1
    assert ledger["missing_by_stage"]["decision_synthesis"] >= 1
    assert any(row["category"] == "quantitative_anchor" for row in ledger["top_missing_obligations"])
    assert any(row["status"] == "source_missing" for row in ledger["obligations"])


def test_gap_telemetry_includes_main_memo_obligation_summary() -> None:
    candidate_map = {
        "sources": ["source_a"],
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The pooled estimate was RR 0.98 with 95% CI 0.93 to 1.03.",
                "source_id": "source_a",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    scaffold = {
        "source_display_names": {"source_a": "Meta Analysis 2025"},
        "argument_model": {
            "quantitative_anchors": [
                {
                    "statement": "The pooled estimate was RR 0.98 with 95% CI 0.93 to 1.03.",
                    "quantities": ["RR 0.98", "95% CI 0.93 to 1.03"],
                    "source_ids": ["source_a"],
                    "claim_ids": ["c001"],
                    "quantity_ids": ["qc0001"],
                }
            ],
        },
        "quantity_ledger": {"evidence_cards": []},
        "evidence_weighting_ledger": {"all_evidence": []},
        "decision_synthesis_model": {
            "schema_id": "decision_synthesis_model_v1",
            "evidence_lines": [],
            "central_tensions": [],
            "recommendations": [],
            "cruxes": [],
        },
        "map_sufficiency_report": {},
        "quality_issues": [],
    }

    diagnosis = build_gap_diagnosis(
        question="Should the option be treated as neutral?",
        candidate_map=candidate_map,
        prioritized_map=candidate_map,
        quality_report={"status": "usable_with_review", "issues": []},
        prioritization_report={},
        scaffold=scaffold,
        briefing_text="**Decision question:** Should the option be treated as neutral?\n\nThe option is neutral.",
        validation={"status": "passes_contract", "score": 100, "issues": []},
        polish_report={"status": "polished", "score": 100, "duplicate_sentence_count": 0},
        rewrite_report={"status": "accepted"},
        baseline_path="baseline.md",
        baseline_text="The baseline discusses Meta Analysis 2025 and ApoB.",
    )

    summary = diagnosis["main_memo_obligation_summary"]
    assert summary["schema_id"] == "main_memo_obligation_ledger_v1"
    assert summary["missing_from_memo_count"] >= 1
    assert "main_memo_obligation_ledger" in diagnosis
    assert any(driver["gap"] == "Main memo drops required decision-support obligations" for driver in diagnosis["largest_gap_drivers"])


def test_reader_reference_expansion_preserves_decision_crux_id_fields() -> None:
    payload = {
        "cruxes": [
            {
                "crux": "Whether the key uncertainty changes the recommendation",
                "supporting_claim_ids": ["c001"],
                "challenging_claim_ids": ["c002"],
                "current_read": "Claim c001 supports the default while Claim c002 limits it.",
            }
        ]
    }
    candidate_map = {
        "claims": [
            {"claim_id": "c001", "claim": "Support claim text."},
            {"claim_id": "c002", "claim": "Challenge claim text."},
        ],
        "relations": [],
    }

    expanded = _expand_payload_reader_references(payload, candidate_map)

    crux = expanded["cruxes"][0]
    assert crux["supporting_claim_ids"] == ["c001"]
    assert crux["challenging_claim_ids"] == ["c002"]
    assert "Support claim text" in crux["current_read"]


def test_decision_crux_schema_rejects_overlapping_support_and_challenge_ids() -> None:
    with pytest.raises(ValueError, match="overlap"):
        DecisionCrux.model_validate(
            {
                "crux": "Whether implementation capacity changes the recommendation",
                "uncertainty": "Whether implementation capacity changes the recommendation",
                "current_read": "The evidence depends on implementation capacity being present.",
                "decision_effect": "This determines whether the recommendation travels to the target setting.",
                "would_change_if": "The recommendation would change if capacity were absent.",
                "supporting_claim_ids": ["c001"],
                "challenging_claim_ids": ["c001"],
                "relation_ids": [],
                "crux_type": "scope_boundary",
            }
        )


def test_crux_telemetry_separates_explicit_invalid_and_weak_anchors() -> None:
    candidate_map = {
        "claims": [
            {"claim_id": "c001", "claim": "Maintenance capacity determines whether the intervention works."},
            {"claim_id": "c002", "claim": "The intervention improves hard outcomes."},
        ],
        "relations": [{"relation_id": "r001", "source_claim": "c001", "target_claim": "c002", "relation_type": "crux_for"}],
    }
    scaffold = {
        "decision_synthesis_model": {
            "cruxes": [
                {
                    "crux": "Whether maintenance capacity changes the recommendation",
                    "current_read": "Maintenance capacity determines whether the intervention works.",
                    "would_change_if": "The recommendation would change if maintenance capacity were absent.",
                    "supporting_claim_ids": ["c001"],
                    "challenging_claim_ids": ["missing_claim"],
                    "relation_ids": ["missing_relation"],
                },
                {
                    "crux": "Whether hard outcome gains transfer to the target setting",
                    "current_read": "The intervention improves hard outcomes in the mapped evidence.",
                    "would_change_if": "The recommendation would change if hard outcome gains did not transfer.",
                    "supporting_claim_ids": [],
                    "challenging_claim_ids": [],
                    "relation_ids": [],
                },
            ]
        },
        "evidence_weighting_ledger": {"all_evidence": []},
        "map_sufficiency_report": {},
        "quality_issues": [],
    }

    diagnosis = build_gap_diagnosis(
        question="Should the intervention be adopted?",
        candidate_map=candidate_map,
        prioritized_map=candidate_map,
        quality_report={"status": "usable_with_review", "issues": []},
        prioritization_report={},
        scaffold=scaffold,
        briefing_text="**Decision question:** Should the intervention be adopted?",
        validation={"status": "passes_contract", "score": 100, "issues": []},
        polish_report={"status": "polished", "score": 100, "duplicate_sentence_count": 0},
        rewrite_report={"status": "accepted"},
    )

    crux_quality = diagnosis["relation_quality"]["crux_quality"]
    assert crux_quality["explicit_claim_anchor_count"] == 1
    assert crux_quality["explicit_relation_anchor_count"] == 0
    assert crux_quality["weak_text_anchor_count"] == 1
    assert crux_quality["invalid_reference_count"] == 2
    assert "known map IDs" in crux_quality["recommended_intervention"]
