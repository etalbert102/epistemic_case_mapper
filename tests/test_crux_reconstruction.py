from __future__ import annotations

from epistemic_case_mapper.map_briefing_crux_reconstruction import reconstruct_decision_crux_items


def test_crux_reconstruction_replaces_topical_tension_with_answer_changing_question() -> None:
    items = [
        {
            "item_id": "support",
            "role": "strongest_support",
            "reader_claim": "The default population evidence does not show worse outcomes.",
            "source_labels": ["Support Study"],
            "lineage": {"derived_from_claim_ids": ["c1"], "derived_from_source_ids": ["s1"]},
            "must_use": True,
        },
        {
            "item_id": "counter",
            "role": "strongest_counterweight",
            "reader_claim": "A subgroup study reports higher failure rates under specific conditions.",
            "source_labels": ["Counter Study"],
            "lineage": {"derived_from_claim_ids": ["c2"], "derived_from_source_ids": ["s2"]},
            "must_use": True,
        },
        {
            "item_id": "weak",
            "role": "decision_crux",
            "reader_claim": "Subgroup risk in tension with default evidence.",
            "must_use": True,
        },
    ]

    updated, report = reconstruct_decision_crux_items(items)
    cruxes = [item for item in updated if item["role"] == "decision_crux"]

    assert report["status"] == "changed"
    assert len(cruxes) == 1
    assert cruxes[0]["item_id"] == "reconstructed_crux_001"
    assert "should outweigh" in cruxes[0]["reader_claim"]
    assert "in tension with" not in cruxes[0]["reader_claim"]
    assert cruxes[0]["lineage"]["derived_from_claim_ids"] == ["c1", "c2"]
