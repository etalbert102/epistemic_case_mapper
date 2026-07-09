from __future__ import annotations

from epistemic_case_mapper.map_briefing_packet_coverage import build_packet_coverage_report


def test_high_priority_omission_accounting_distinguishes_represented_from_lost() -> None:
    candidate_pool = [
        {
            "candidate_card_id": "ec_represented",
            "claim_ids": ["c1"],
            "source_ids": ["s1"],
            "claim": "Option A reduced losses by 25 percent.",
            "decision_relevance_score": 10,
            "source_grounded": True,
        },
        {
            "candidate_card_id": "ec_lost",
            "claim_ids": ["c2"],
            "source_ids": ["s2"],
            "claim": "Maintenance failures change the decision.",
            "decision_relevance_score": 10,
            "source_grounded": True,
        },
    ]
    bundles = [
        {
            "bundle_id": "bundle_001",
            "candidate_card_ids": ["ec_other"],
            "claim_ids": ["c1"],
            "source_ids": ["s1"],
            "claim": "Option A reduced losses by 25 percent.",
        }
    ]

    report = build_packet_coverage_report(candidate_pool, bundles, retain_ledger=[], source_trail=[])

    assert report["high_priority_omitted_count"] == 2
    assert report["high_priority_represented_elsewhere_count"] == 1
    assert report["high_priority_truly_lost_count"] == 1
    assert report["high_priority_represented_elsewhere"][0]["reason"] == "shared_claim_id"
    assert report["high_priority_truly_lost_ids"] == ["ec_lost"]
    assert "high_priority_truly_lost_after_trimming" in report["warnings"]
