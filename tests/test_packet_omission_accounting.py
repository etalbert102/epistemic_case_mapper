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
            "decision_role": "strongest_support",
            "decision_relevance_score": 10,
            "inclusion_recommendation": "main_text",
            "source_grounded": True,
        },
        {
            "candidate_card_id": "ec_context",
            "claim_ids": ["c3"],
            "source_ids": ["s3"],
            "claim": "A narrower subgroup changes applicability.",
            "decision_role": "scope_boundary",
            "decision_relevance_score": 8,
            "inclusion_recommendation": "supporting_context",
            "map_question_fit_statuses": ["narrower_than_question"],
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

    assert report["review_worthy_omitted_count"] == 3
    assert report["high_priority_represented_elsewhere_count"] == 1
    assert report["high_priority_truly_lost_count"] == 2
    assert report["truly_lost_decision_critical_count"] == 1
    assert report["truly_lost_moderate_context_count"] == 1
    assert report["high_priority_represented_elsewhere"][0]["reason"] == "shared_claim_id"
    assert report["high_priority_truly_lost_ids"] == ["ec_lost", "ec_context"]
    assert report["truly_lost_decision_critical"][0]["candidate_card_id"] == "ec_lost"
    assert report["truly_lost_moderate_context"][0]["candidate_card_id"] == "ec_context"
    assert "decision_critical_evidence_lost_after_trimming" in report["warnings"]
    assert "moderate_context_evidence_lost_after_trimming" in report["warnings"]
