from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_repair_prompt,
    build_memo_ready_packet_retention_report,
)
from tests.test_decision_writer_packet import _global_model, _ledger


def test_decision_writer_packet_repair_prompt_carries_originating_evidence_context() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )
    weak_memo = "## Decision Brief\n\nOption A is plausible.\n"
    before = build_memo_ready_packet_retention_report(weak_memo, packet)

    prompt = build_memo_ready_packet_repair_prompt(weak_memo, packet, before)

    assert '"contract_mode": "strict_writer_packet"' in prompt
    assert "This is the main support." in prompt
    assert "This bounds adoption." in prompt
