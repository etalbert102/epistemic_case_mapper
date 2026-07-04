from __future__ import annotations

from epistemic_case_mapper.map_briefing import build_gap_diagnosis, canonicalize_claims_for_briefing
from epistemic_case_mapper.map_briefing_map_utils import _expand_payload_reader_references


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
