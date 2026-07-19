from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle

from test_decision_briefing_packet import _scaffold


def test_decision_packet_reports_low_question_fit_primary_evidence_without_suppressing() -> None:
    scaffold = _scaffold()
    scaffold["candidate_evidence_cards"]["cards"].append(
        {
            "candidate_card_id": "off_question_support",
            "claim_ids": ["off_question_claim"],
            "source_ids": ["s4"],
            "source_titles": ["Adjacent Outcome Study"],
            "claim": "Cancer screening participation increased in unrelated clinic settings.",
            "role": "support",
            "evidence_roles": ["support"],
            "decision_relevance_score": 10,
            "inclusion_recommendation": "main_text",
            "anchor_confidence": "exact",
        }
    )
    scaffold["source_display_names"]["s4"] = "Adjacent Outcome Study"

    result = build_decision_briefing_packet_bundle(scaffold, question="Should the city adopt option A for flood protection?")
    packet = result["decision_briefing_packet"]
    off_question = next(row for row in packet["evidence_bundles"] if row.get("candidate_card_ids") == ["off_question_support"])

    assert off_question["decision_relevance_assessment"]["question_relevance_status"] == "low_question_overlap"
    assert "primary_bundles_low_question_fit" in packet["coverage_report"]["warnings"]
    assert off_question["bundle_id"] in packet["coverage_report"]["low_question_fit_primary_bundle_ids"]
