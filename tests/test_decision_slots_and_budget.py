from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_slots import build_decision_slot_inventory
from epistemic_case_mapper.pipeline.briefing.map_briefing_packet_budget import (
    build_packet_budget_allocation_report,
    build_packet_compression_report,
)

from test_decision_briefing_packet import _scaffold


def test_decision_slots_are_derived_from_obligations_and_matrix() -> None:
    built = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )

    slots = build_decision_slot_inventory(
        decision_obligation_graph=built["decision_obligation_graph"],
        evidence_answer_matrix=built["evidence_answer_matrix"],
    )
    slot_types = {row["slot_type"] for row in slots["slots"]}

    assert slots["schema_id"] == "decision_slot_inventory_v1"
    assert {"answer_support", "counterevidence", "quantitative_anchor"} <= slot_types
    assert all(row["obligation_ids"] for row in slots["slots"])


def test_packet_budget_and_compression_reports_are_obligation_aware() -> None:
    built = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    budget = build_packet_budget_allocation_report(
        candidate_answer_set=built["candidate_answer_set"],
        decision_slot_inventory=built["decision_slots"],
        evidence_answer_matrix=built["evidence_answer_matrix"],
    )
    compression = build_packet_compression_report(
        decision_slot_inventory=built["decision_slots"],
        evidence_answer_matrix=built["evidence_answer_matrix"],
    )

    buckets = {row["bucket"]: row for row in budget["allocations"]}
    assert budget["schema_id"] == "packet_budget_allocation_report_v1"
    assert buckets["answer_frame_and_candidate_answers"]["candidate_answer_count"] >= 1
    assert buckets["quantitative_anchors"]["matrix_row_count"] >= 1
    assert "exact_quantity_text" in compression["protected_invariants"]
    assert compression["schema_id"] == "packet_compression_report_v1"


def test_decision_packet_embeds_slots_budget_and_compression_reports() -> None:
    result = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    packet = result["decision_briefing_packet"]

    assert result["decision_slots"]["schema_id"] == "decision_slot_inventory_v1"
    assert result["packet_budget_allocation_report"]["schema_id"] == "packet_budget_allocation_report_v1"
    assert result["packet_compression_report"]["schema_id"] == "packet_compression_report_v1"
    assert packet["decision_slots"] == result["decision_slots"]
    assert packet["packet_budget_allocation_report"] == result["packet_budget_allocation_report"]
    assert packet["packet_compression_report"] == result["packet_compression_report"]
