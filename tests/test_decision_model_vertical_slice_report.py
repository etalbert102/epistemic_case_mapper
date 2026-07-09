from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_vertical_slice_report import build_decision_model_vertical_slice_report

from test_decision_briefing_packet import _scaffold


def test_vertical_slice_report_records_operational_decision_model_signals() -> None:
    built = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    report = build_decision_model_vertical_slice_report(built["decision_briefing_packet"])

    assert report["schema_id"] == "decision_model_vertical_slice_report_v1"
    assert report["status"] == "vertical_slice_operational"
    assert report["signals"]["candidate_answer_count"] >= 1
    assert report["signals"]["source_graph_node_count"] >= 1
    assert report["signals"]["obligation_count"] >= 1
    assert report["signals"]["evidence_answer_matrix_row_count"] >= 1
    assert report["signals"]["decision_slot_count"] >= 1
    assert report["signals"]["quantitative_anchor_bundle_count"] >= 1
    assert built["decision_briefing_packet"]["decision_model_vertical_slice_report"]["status"] == "vertical_slice_operational"
