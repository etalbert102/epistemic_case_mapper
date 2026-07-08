from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.map_briefing_artifacts import write_scaffold_artifacts
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle


def _scaffold() -> dict:
    return {
        "question": "Should the city adopt option A for flood protection?",
        "source_display_names": {
            "s1": "Outcome Study",
            "s2": "Counter Study",
            "s3": "Boundary Report",
        },
        "candidate_evidence_cards": {
            "cards": [
                {
                    "candidate_card_id": "ec0001",
                    "source_card_ids": ["sc0001"],
                    "claim_ids": ["c1"],
                    "source_ids": ["s1"],
                    "source_titles": ["Outcome Study"],
                    "claim": "Option A reduced flood losses by 25% in comparable river cities.",
                    "role": "support",
                    "evidence_roles": ["support"],
                    "decision_relevance_score": 10,
                    "inclusion_recommendation": "main_text",
                    "inclusion_reason": "Direct outcome evidence.",
                    "anchor_confidence": "exact",
                    "quantity_values": ["25%"],
                    "section_candidates": ["Evidence Carrying the Conclusion"],
                },
                {
                    "candidate_card_id": "ec0002",
                    "source_card_ids": ["sc0002"],
                    "claim_ids": ["c2"],
                    "source_ids": ["s2"],
                    "source_titles": ["Counter Study"],
                    "claim": "Option A failed when maintenance budgets were cut.",
                    "role": "counterweight",
                    "evidence_roles": ["counterweight"],
                    "decision_relevance_score": 9,
                    "inclusion_recommendation": "main_text",
                    "inclusion_reason": "Important contrary evidence.",
                    "anchor_confidence": "exact",
                    "section_candidates": ["Decision Cruxes"],
                },
                {
                    "candidate_card_id": "ec0003",
                    "source_card_ids": ["sc0003"],
                    "claim_ids": ["c3"],
                    "source_ids": ["s3"],
                    "source_titles": ["Boundary Report"],
                    "claim": "The result only applies where pump capacity exceeds expected peak flow.",
                    "role": "scope",
                    "evidence_roles": ["scope"],
                    "decision_relevance_score": 8,
                    "inclusion_recommendation": "main_text",
                    "inclusion_reason": "Scope boundary.",
                    "anchor_confidence": "exact",
                    "section_candidates": ["Practical Scope and Exceptions"],
                },
            ]
        },
        "source_evidence_cards": {
            "cards": [
                {
                    "source_card_id": "sc0001",
                    "claim_ids": ["c1"],
                    "source_id": "s1",
                    "source_quote_or_excerpt": "Option A reduced flood losses by 25% in comparable river cities.",
                    "quantity_values": ["25%"],
                    "anchor_confidence": "exact",
                },
                {
                    "source_card_id": "sc0002",
                    "claim_ids": ["c2"],
                    "source_id": "s2",
                    "source_quote_or_excerpt": "Option A failed when maintenance budgets were cut.",
                    "anchor_confidence": "exact",
                },
                {
                    "source_card_id": "sc0003",
                    "claim_ids": ["c3"],
                    "source_id": "s3",
                    "source_quote_or_excerpt": "The result only applies where pump capacity exceeds expected peak flow.",
                    "anchor_confidence": "exact",
                },
            ]
        },
        "quantity_ledger": {
            "evidence_cards": [
                {
                    "card_id": "qc0001",
                    "atomic_evidence_card_id": "ec0001",
                    "claim_id": "c1",
                    "claim": "Option A reduced flood losses by 25% in comparable river cities.",
                    "context": "Option A reduced flood losses by 25%.",
                    "key_quantities": ["25%"],
                    "effect_estimates": ["25%"],
                    "card_score": 32,
                    "interpretation_hint": "Direct outcome estimate.",
                }
            ],
            "top_quantitative_anchors": [
                {
                    "quantity_id": "q0001",
                    "claim_id": "c1",
                    "claim": "Option A reduced flood losses by 25% in comparable river cities.",
                    "quantity_text": "25%",
                    "source": "s1",
                }
            ],
        },
        "argument_model": {
            "confidence": "medium",
            "proposed_answer": "Option A is promising but maintenance-dependent.",
            "strongest_support": [
                {
                    "statement": "Option A reduced flood losses by 25%.",
                    "source_ids": ["s1"],
                    "claim_ids": ["c1"],
                    "quantities": ["25%"],
                    "why_it_matters": "Direct outcome evidence.",
                }
            ],
            "strongest_counterarguments": [
                {
                    "statement": "Maintenance cuts can erase the benefit.",
                    "source_ids": ["s2"],
                    "claim_ids": ["c2"],
                    "why_it_matters": "This is a decision crux.",
                }
            ],
            "scope_boundaries": [],
            "cruxes": [],
            "quantitative_anchors": [],
        },
    }


def test_decision_briefing_packet_retains_roles_sources_and_quantities() -> None:
    result = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = result["decision_briefing_packet"]
    sufficiency = result["packet_sufficiency_report"]

    roles = {row["decision_role"] for row in packet["evidence_bundles"]}
    assert {"counterweight", "scope_boundary", "quantitative_anchor"} <= roles
    assert any("25%" in row.get("required_terms", []) for row in packet["must_retain_ledger"])
    assert any(row["source_label"] == "Counter Study" for row in packet["source_trail"])
    assert sufficiency["role_coverage"]["missing_available_roles"] == []
    assert sufficiency["quantity_retention"]["missing_top_quantities"] == []


def test_packet_sufficiency_reports_high_priority_compression_loss() -> None:
    scaffold = _scaffold()
    for index in range(20):
        scaffold["candidate_evidence_cards"]["cards"].append(
            {
                "candidate_card_id": f"extra{index:02d}",
                "claim_ids": [f"cx{index}"],
                "source_ids": [f"sx{index}"],
                "source_titles": [f"Extra Source {index}"],
                "claim": f"Extra high priority support claim {index} with unique value {index}%.",
                "role": "support",
                "evidence_roles": ["support"],
                "decision_relevance_score": 10,
                "inclusion_recommendation": "main_text",
                "anchor_confidence": "exact",
                "quantity_values": [f"{index}%"],
            }
        )

    result = build_decision_briefing_packet_bundle(scaffold, question="Should the city adopt option A for flood protection?")
    sufficiency = result["packet_sufficiency_report"]

    assert sufficiency["high_priority_omitted_evidence"]
    assert "high_priority_omitted_evidence" in sufficiency["issues"]


def test_scaffold_artifacts_write_packet_reports(tmp_path: Path) -> None:
    scaffold = _scaffold()
    scaffold.update(build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"]))

    paths = write_scaffold_artifacts(
        artifacts=tmp_path,
        prompt="prompt",
        prioritized_map={"claims": []},
        prioritization_report={},
        erosion_audit={},
        scaffold=scaffold,
    )

    assert paths["decision_briefing_packet"].exists()
    assert paths["decision_briefing_packet_report"].exists()
    assert paths["packet_sufficiency_report"].exists()
