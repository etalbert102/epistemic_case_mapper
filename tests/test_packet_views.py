from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_packet_views import build_decision_packet_views

from test_decision_briefing_packet import _scaffold


def test_packet_views_project_distinct_synthesis_audit_trace_and_qa_views() -> None:
    built = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    packet = built["decision_briefing_packet"]
    views = build_decision_packet_views(packet)

    assert views["schema_id"] == "decision_packet_views_v1"
    assert set(views) >= {"synthesis_packet", "audit_packet", "source_trace_packet", "qa_packet"}
    assert views["synthesis_packet"]["decision_question"] == packet["decision_question"]
    assert views["synthesis_packet"]["candidate_answers"] == packet["candidate_answer_set"]["candidate_answers"]
    assert any(
        row["decision_role"] == "quantitative_anchor"
        for row in views["synthesis_packet"]["evidence_bundles"]
    )
    assert views["audit_packet"]["decision_obligation_graph"] == packet["decision_obligation_graph"]
    assert views["source_trace_packet"]["source_trail"] == packet["source_trail"]
    assert views["qa_packet"]["coverage_report"] == packet["coverage_report"]


def test_packet_builder_embeds_and_returns_packet_views() -> None:
    built = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    packet = built["decision_briefing_packet"]

    assert built["packet_views"]["schema_id"] == "decision_packet_views_v1"
    assert packet["packet_views"] == built["packet_views"]
    assert packet["packet_views"]["qa_packet"]["vertical_slice_report"]["status"] == "vertical_slice_operational"
