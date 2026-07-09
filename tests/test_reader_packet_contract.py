from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_packet_memo import (
    build_packet_memo_plan,
    build_reader_facing_packet_synthesis_prompt,
)

from tests.test_decision_briefing_packet import _scaffold


def test_reader_packet_includes_general_decision_synthesis_contract() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    reader_packet = build_packet_memo_plan(built["decision_briefing_packet"])["reader_facing_packet"]

    contract = reader_packet["decision_synthesis_contract"]

    assert contract["schema_id"] == "decision_synthesis_contract_v1"
    assert "best-supported answer or action stance" in contract["stance_task"]
    assert "strongest evidence" in contract["counterweight_task"]
    assert "subgroups, contexts, or assumptions" in contract["scope_task"]
    assert contract["strongest_support_to_weigh"]
    assert contract["strongest_counterweights_to_weigh"]
    assert contract["quantitative_anchors_to_interpret"]
    assert "egg" not in str(contract).lower()


def test_reader_packet_synthesis_prompt_uses_contract_as_writing_plan() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    reader_packet = build_packet_memo_plan(built["decision_briefing_packet"])["reader_facing_packet"]

    prompt = build_reader_facing_packet_synthesis_prompt(reader_packet)

    assert "decision_synthesis_contract" in prompt
    assert "Use that contract as the writing plan" in prompt
    assert "Do not merely summarize or list evidence" in prompt
    assert "## Why This Is the Best Current Read" in prompt
    assert "## What Could Change the Answer" in prompt
