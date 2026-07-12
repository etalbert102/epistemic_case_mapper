from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_packet import (
    build_memo_ready_packet_synthesis_prompt,
    build_quality_synthesis_packet_bundle,
)

from test_decision_briefing_packet import _scaffold


def test_memo_ready_packet_includes_general_decision_synthesis_contract() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    contract = packet["decision_synthesis_contract"]

    assert contract["schema_id"] == "decision_synthesis_contract_v1"
    assert "best-supported answer or action stance" in contract["stance_task"]
    assert "strongest evidence" in contract["counterweight_task"]
    assert "subgroups, contexts, or assumptions" in contract["scope_task"]
    assert contract["answer_spine_to_use"]
    assert contract["strongest_support_to_weigh"]
    assert contract["strongest_counterweights_to_weigh"]
    assert contract["quantitative_anchors_to_interpret"]
    assert "egg" not in str(contract).lower()


def test_memo_ready_synthesis_prompt_uses_contract_as_flexible_guidance() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "writer model context" in prompt
    assert "writer_model_context_v1" in prompt
    assert "The writer model context is the complete model-visible evidence and judgment record" in prompt
    assert "Weigh support against counterweights and scope boundaries" in prompt
    assert "quantity_anchors" in prompt


def test_memo_ready_prompt_without_evidence_items_does_not_dump_raw_packet() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "decision_synthesis_contract": {"schema_id": "decision_synthesis_contract_v1"},
        "memo_warning_packet": {"warnings": [{"claim": "Raw warning should not be dumped."}]},
    }

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "synthesis prompt unavailable" in prompt
    assert "Raw warning should not be dumped" not in prompt
    assert "decision_synthesis_contract" not in prompt
