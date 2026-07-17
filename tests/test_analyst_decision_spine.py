from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)
from epistemic_case_mapper.map_briefing_memo_ready_prompt import build_memo_ready_packet_synthesis_prompt
from epistemic_case_mapper.map_briefing_writer_decision_interface import (
    build_writer_decision_interface,
    build_writer_decision_interface_quality_report,
)
from tests.test_decision_writer_packet import _global_model, _ledger


def test_memo_ready_packet_exposes_analyst_decision_spine_to_writer() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    analyst_model = {
        "schema_id": "analyst_decision_model_v1",
        "decision_logic": {
            "bounded_bottom_line": "Adopt option A only where the narrower setting is not decisive.",
            "support_summary": "Outcome Review carries the main outcome finding.",
            "counterweight_weighting": "Scope Review bounds the answer rather than overturning it.",
            "practical_implications": ["Adopt option A only in settings matching the outcome evidence."],
        },
        "source_weight_judgments": [
            {
                "judgment_id": "analyst_source_weight_001",
                "source_ids": ["s1"],
                "main_use": "drives_answer",
                "why_weight_this_way": "Outcome Review carries the answer because it covers the main outcome.",
                "memo_weight_sentence": "Outcome Review carries the main answer.",
                "method": "parallel_global_analyst_source_weighting",
                "evidence_item_ids": ["item:support"],
            },
            {
                "judgment_id": "analyst_source_weight_002",
                "source_ids": ["s2"],
                "main_use": "defines_scope",
                "why_weight_this_way": "Scope Review defines where the result stops applying.",
                "memo_weight_sentence": "Scope Review bounds application to matching settings.",
                "method": "parallel_global_analyst_source_weighting",
                "evidence_item_ids": ["item:limit"],
            },
        ],
        "source_weight_judgment_report": {"schema_id": "parallel_global_source_weight_judgment_report_v1", "status": "ready"},
    }

    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
        analyst_decision_model=analyst_model,
    )

    interface_spine = packet["writer_decision_interface"]["analyst_decision_spine"]
    canonical_spine = packet["canonical_decision_writer_packet"]["analyst_decision_spine"]
    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert interface_spine["schema_id"] == "analyst_decision_spine_v1"
    assert interface_spine["quality_report"]["source_weight_move_count"] == 2
    assert any(move["move_id"] == "source_weighting" for move in interface_spine["decision_moves"])
    assert canonical_spine["source_weight_moves"][0]["point"] == "Outcome Review carries the main answer."
    assert "analyst_decision_spine" in prompt
    assert "controlling reasoning plan" in prompt


def test_writer_interface_quantity_anchors_include_rescued_context() -> None:
    packet = {
        "schema_id": "memo_ready_packet_v1",
        "decision_question": "Should option A be adopted?",
        "answer_spine": {"default_read": "Adopt option A where the evidence applies.", "confidence": "medium"},
        "evidence_items": [
            {
                "item_id": "main",
                "role": "strongest_support",
                "reader_claim": "Option A improves the main outcome.",
                "source_labels": ["Outcome Review"],
                "obligation_level": "must_include",
                "must_use": True,
                "importance_rank": 1,
            },
            {
                "item_id": "calibrator",
                "role": "strongest_support",
                "reader_claim": "The effect size calibrates the decision.",
                "source_labels": ["Outcome Review"],
                "obligation_level": "should_include",
                "quantities": [{"value": "20% improvement", "interpretation": "effect size for the main outcome"}],
                "importance_rank": 2,
            },
        ],
        "source_trail": [{"source_label": "Outcome Review"}],
    }

    interface = build_writer_decision_interface(packet)

    assert interface["decision_evidence_table"][0]["item_id"] == "main"
    assert any(row["item_id"] == "calibrator" for row in interface["rescued_context_table"])
    assert interface["quantity_anchors"][0]["value"] == "20% improvement"
    assert "missing_quantity_anchors" not in build_writer_decision_interface_quality_report(interface)["warnings"]
