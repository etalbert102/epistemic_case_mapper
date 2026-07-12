from __future__ import annotations

from epistemic_case_mapper.map_briefing_packet_model_view import packet_summary_for_model


def test_packet_summary_for_model_compacts_sections_and_coverage() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "evidence_bundles": [{"bundle_id": "b1", "claim": "Option A helps."}],
        "must_retain_ledger": [],
        "section_views": [
            {
                "section": "Decision Brief",
                "target_bundle_ids": ["b1", "b2"],
                "section_use": "opening",
                "long_internal_notes": "This should not be model-visible.",
            }
        ],
        "coverage_report": {
            "status": "warning",
            "warnings": ["missing_counterweight"],
            "truly_lost_decision_critical_count": 12,
            "truly_lost_decision_critical": [
                {
                    "candidate_card_id": "c1",
                    "decision_role": "counterweight",
                    "priority": 10,
                    "claim": "A very long counterweight claim " * 30,
                    "source_ids": ["s1"],
                },
                *[
                    {"candidate_card_id": f"extra-{index}", "claim": f"Extra {index}"}
                    for index in range(10)
                ],
            ],
            "raw_candidate_pool": [{"claim": "This bulky audit data should not be visible."}],
        },
    }

    view = packet_summary_for_model(packet)
    serialized = str(view)

    assert "section_views" not in view
    assert view["section_summary"] == [{"section": "Decision Brief", "target_count": 2, "section_use": "opening"}]
    assert view["coverage_summary"]["truly_lost_decision_critical_count"] == 12
    assert len(view["coverage_summary"]["truly_lost_decision_critical_examples"]) == 4
    assert "long_internal_notes" not in serialized
    assert "raw_candidate_pool" not in serialized
    assert "extra-9" not in serialized
