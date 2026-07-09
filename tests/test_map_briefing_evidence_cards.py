from __future__ import annotations

from epistemic_case_mapper.map_briefing_evidence_cards import (
    apply_evidence_cards_to_map,
    build_atomic_evidence_cards,
)


def test_atomic_evidence_cards_preserve_normal_claim_with_abbreviation() -> None:
    claim_text = (
        "Egg intake is a significant source of choline (approx. 140 mg per egg), "
        "which is essential for liver and brain function but can be metabolized into TMAO, "
        "a purported CVD risk factor."
    )
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "source_id": "s1",
                "claim": claim_text,
            }
        ],
        "relations": [],
    }
    evidence_ledger = {
        "all_evidence": [
            {
                "claim_id": "c1",
                "source_id": "s1",
                "source": "Source 1",
                "claim": claim_text,
                "section": "scope_limits",
                "decision_relevance_score": 8,
            }
        ]
    }

    cards = build_atomic_evidence_cards(candidate_map, evidence_ledger, {"s1": "Source 1"})
    card = cards["cards"][0]

    assert card["proposition"] == claim_text
    assert card["raw_claim"] == claim_text
    assert "fragment_or_truncation" not in card["noise_flags"]

    normalized = apply_evidence_cards_to_map(candidate_map, cards)

    assert normalized["claims"][0]["claim"] == claim_text
    assert normalized["claims"][0]["raw_claim"] == claim_text
