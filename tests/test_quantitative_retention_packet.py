from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_packet_memo import build_packet_memo_plan


def test_reader_packet_groups_unbundled_top_quantity_anchors() -> None:
    scaffold = {
        "question": "Should the city adopt option A?",
        "source_display_names": {"s1": "Outcome Study"},
        "source_citation_labels": {"s1": "Outcome Study"},
        "candidate_evidence_cards": {
            "cards": [
                {
                    "candidate_card_id": "ec1",
                    "claim_ids": ["c1"],
                    "source_ids": ["s1"],
                    "claim": "Option A reduced losses by 25%.",
                    "role": "support",
                    "evidence_roles": ["support"],
                    "decision_relevance_score": 10,
                    "inclusion_recommendation": "main_text",
                    "quantity_values": ["25%"],
                    "anchor_confidence": "exact",
                }
            ]
        },
        "source_evidence_cards": {
            "cards": [
                {
                    "source_card_id": "sc1",
                    "claim_ids": ["c1"],
                    "source_id": "s1",
                    "source_quote_or_excerpt": "Option A reduced losses by 25%.",
                    "anchor_confidence": "exact",
                }
            ]
        },
        "quantity_ledger": {
            "evidence_cards": [],
            "top_quantitative_anchors": [
                {
                    "quantity_id": "q_hr",
                    "claim_id": "c2",
                    "claim": "Replacing option A with option B was associated with higher downstream risk.",
                    "quantity_text": "hazard ratio 1.15",
                    "source": "Outcome Study",
                },
                {
                    "quantity_id": "q_ci",
                    "claim_id": "c2",
                    "claim": "Replacing option A with option B was associated with higher downstream risk.",
                    "quantity_text": "95% confidence interval 1.05 to 1.27",
                    "source": "Outcome Study",
                },
            ],
        },
        "argument_model": {
            "confidence": "medium",
            "proposed_answer": "Option A is promising.",
            "strongest_support": [],
            "strongest_counterarguments": [],
            "scope_boundaries": [],
            "cruxes": [],
            "quantitative_anchors": [],
        },
    }

    built = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    packet = built["decision_briefing_packet"]
    grouped_items = [
        row
        for row in packet["must_retain_ledger"]
        if row.get("statement") == "Replacing option A with option B was associated with higher downstream risk."
    ]

    assert len(grouped_items) == 1
    assert "hazard ratio 1.15" in grouped_items[0]["required_terms"]
    assert "95% confidence interval 1.05 to 1.27" in grouped_items[0]["required_terms"]

    reader_packet = build_packet_memo_plan(packet)["reader_facing_packet"]
    grouped_cards = [
        card
        for card in reader_packet["quantitative_anchors"]
        if card.get("statement") == "Replacing option A with option B was associated with higher downstream risk."
    ]

    assert len(grouped_cards) == 1
    assert grouped_cards[0]["quantities"] == ["hazard ratio 1.15", "95% confidence interval 1.05 to 1.27"]
    assert grouped_cards[0]["required_in_memo"] is True
