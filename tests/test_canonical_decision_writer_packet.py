from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle

from test_decision_briefing_packet import _scaffold


def test_memo_ready_packet_includes_canonical_decision_writer_packet() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    canonical = packet["canonical_decision_writer_packet"]

    assert canonical["schema_id"] == "canonical_decision_writer_packet_v1"
    assert canonical["decision_question"] == "Should the city adopt option A for flood protection?"
    assert canonical["decision_brief_skeleton"]["direct_answer"]
    assert canonical["decision_brief_skeleton"]["main_reason"]
    assert canonical["priority_evidence"]
    assert canonical["counterweight_dispositions"]
    assert canonical["source_weight_notes"]
    assert canonical["mandatory_retention_checklist"]
    assert canonical["citation_registry"]
    assert canonical["quality_report"]["schema_id"] == "canonical_decision_writer_packet_quality_report_v1"
    assert all(
        row.get("source_id") or row.get("source_ids")
        for row in canonical["priority_evidence"]
        if row.get("role") in {"strongest_support", "strongest_counterweight", "scope_boundary", "decision_crux"}
    )
