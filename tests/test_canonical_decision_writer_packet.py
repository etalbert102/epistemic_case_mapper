from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_repair_prompt,
    build_memo_ready_packet_retention_report,
)
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
    assert canonical["decision_answer_classification"]["answer_shape"]
    assert canonical["analyst_reasoning_frame"]
    assert canonical["priority_evidence"]
    assert canonical["organized_evidence_inventory"]["item_count"] == len(packet["evidence_items"])
    assert canonical["counterweight_dispositions"]
    assert canonical["source_weight_notes"]
    assert canonical["mandatory_retention_checklist"]
    assert canonical["citation_registry"]
    assert canonical["quality_report"]["schema_id"] == "canonical_decision_writer_packet_quality_report_v1"
    assert canonical["quality_report"]["answer_shape"] == canonical["decision_answer_classification"]["answer_shape"]
    assert all(
        row.get("source_id") or row.get("source_ids")
        for row in canonical["priority_evidence"]
        if row.get("role") in {"strongest_support", "strongest_counterweight", "scope_boundary", "decision_crux"}
    )
    assert canonical["quality_report"]["organized_evidence_count"] == len(packet["evidence_items"])


def test_canonical_retention_routes_missing_items_to_targeted_repair() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    memo = "## Decision Memo\n\n**Decision Question:** Should the city adopt option A for flood protection?\n\nOption A reduced flood losses by 25% [s1]."

    retention = build_memo_ready_packet_retention_report(memo, packet)
    repair_prompt = build_memo_ready_packet_repair_prompt(memo, packet, retention)

    assert retention["validation_basis"] == "canonical_decision_writer_packet"
    assert retention["canonical_packet_validation"] == "warning"
    assert any(issue.get("issue_type") == "missing_canonical_retention_item" for issue in retention["issues"])
    assert "missing_canonical_items" in repair_prompt
    assert "Repair missing canonical items" in repair_prompt
