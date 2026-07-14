from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_repair_prompt,
    build_memo_ready_packet_retention_report,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.map_briefing_source_appraisal import build_source_appraisal_report

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
    assert canonical["source_weighted_answer_frame"]["lanes"]
    assert canonical["evidence_weighted_argument_spine"]["schema_id"] == "evidence_weighted_argument_spine_v1"
    assert canonical["source_weight_judgments"]
    assert canonical["source_weight_judgment_report"]["schema_id"] == "source_weight_judgment_report_v1"
    assert canonical["priority_evidence"]
    assert canonical["organized_evidence_inventory"]["item_count"] == len(packet["evidence_items"])
    assert canonical["counterweight_dispositions"]
    assert canonical["source_weight_notes"]
    assert canonical["mandatory_retention_checklist"]
    assert canonical["citation_registry"]
    assert canonical["quality_report"]["schema_id"] == "canonical_decision_writer_packet_quality_report_v1"
    assert canonical["quality_report"]["answer_shape"] == canonical["decision_answer_classification"]["answer_shape"]
    assert canonical["quality_report"]["source_weighted_lane_count"] >= 1
    assert canonical["quality_report"]["source_weight_judgment_count"] == len(canonical["source_weight_judgments"])
    assert canonical["quality_report"]["argument_spine_step_count"] == len(canonical["evidence_weighted_argument_spine"]["steps"])
    assert all(
        row.get("source_id") or row.get("source_ids")
        for row in canonical["priority_evidence"]
        if row.get("role") in {"strongest_support", "strongest_counterweight", "scope_boundary", "decision_crux"}
    )
    assert canonical["quality_report"]["organized_evidence_count"] == len(packet["evidence_items"])


def test_canonical_packet_front_loads_source_weighted_answer_frame() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    frame = packet["canonical_decision_writer_packet"]["source_weighted_answer_frame"]
    lanes = frame["lanes"]

    assert frame["schema_id"] == "source_weighted_answer_frame_v1"
    assert "Use primary answer drivers" in frame["weighting_thesis"]
    assert lanes["primary_answer_drivers"][0]["source_ids"]
    assert lanes["counterweights_or_tensions"][0]["source_ids"]
    assert lanes["scope_limiters"][0]["source_ids"]
    assert "source_labels" not in str(frame)
    assert any("main answer" in move for move in frame["required_weighting_moves"])


def test_canonical_packet_exposes_source_weight_judgments_with_source_ids() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    judgments = packet["canonical_decision_writer_packet"]["source_weight_judgments"]

    assert judgments
    assert all(row.get("source_ids") for row in judgments)
    assert all(row.get("main_use") for row in judgments)
    assert all(row.get("why_weight_this_way") for row in judgments)
    assert "to drives answer" not in str(judgments)
    assert "Scaffold assignment" not in str(judgments)
    assert "source_labels" not in str(judgments)


def test_canonical_packet_builds_evidence_weighted_argument_spine() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    spine = packet["canonical_decision_writer_packet"]["evidence_weighted_argument_spine"]
    jobs = {step["memo_job"] for step in spine["steps"]}

    assert spine["quality_report"]["schema_id"] == "argument_spine_quality_report_v1"
    assert "answer" in jobs
    assert "primary_driver" in jobs
    assert "counterweight_or_boundary" in jobs
    assert spine["quality_report"]["step_count"] == len(spine["steps"])
    assert "source_labels" not in str(spine)


def test_quality_synthesis_packet_preserves_source_appraisal_for_writer_notes() -> None:
    scaffold = _scaffold()
    scaffold["source_evidence_cards"]["cards"][0]["source_title"] = "Outcome Study"
    scaffold["source_evidence_cards"]["cards"][0]["evidence_type"] = "observational cohort study"
    scaffold["source_evidence_cards"]["cards"][0]["outcome_or_endpoint"] = "final outcome"
    scaffold["evidence_quality_report"] = {
        "schema_id": "evidence_quality_report_v1",
        "quality_components": {"sc0001": {"directness": "direct", "overall": "usable"}},
    }
    scaffold["source_appraisal_report"] = build_source_appraisal_report(
        source_evidence_cards=scaffold["source_evidence_cards"],
        evidence_quality_report=scaffold["evidence_quality_report"],
    )
    built = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    appraised_items = [
        item
        for item in packet["evidence_items"]
        if item.get("source_appraisal", {}).get("status") == "ready"
    ]
    canonical = packet["canonical_decision_writer_packet"]

    assert appraised_items
    assert canonical["quality_report"]["informative_source_weight_note_count"] >= 1
    assert "source_weight_notes_uninformative" not in canonical["quality_report"]["warnings"]
    assert any(
        "association_not_causation" in row.get("not_enough_for", [])
        for row in canonical["source_weight_notes"]
    )


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
