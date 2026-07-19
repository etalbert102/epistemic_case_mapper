from __future__ import annotations

from epistemic_case_mapper.model_backends import ModelBackendResult
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_retention_report,
    run_memo_ready_packet_repair,
    run_memo_ready_packet_synthesis,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_obligations import build_memo_obligation_packet

from test_decision_briefing_packet import _scaffold


def test_memo_ready_repair_anchors_bound_source_before_model_calls(monkeypatch) -> None:
    packet = {
        "decision_question": "Should option A be used?",
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "evidence_items": [
            {
                "item_id": "item_1",
                "reader_claim": "Option A improves the measured outcome in the target population.",
                "source_ids": ["s1"],
                "must_use": True,
                "role": "strongest_support",
            }
        ],
    }
    packet["memo_obligations"] = build_memo_obligation_packet(packet["evidence_items"])
    memo = "# Decision Memo\n\nOption A improves the measured outcome in the target population.\n"
    before = build_memo_ready_packet_retention_report(memo, packet)

    def fail_backend(*args, **kwargs):
        raise AssertionError("semantic repair should not run")

    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend",
        fail_backend,
    )

    result = run_memo_ready_packet_repair(
        memo,
        packet,
        before,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["accepted"] is True
    assert result["report"]["acceptance_basis"] == "deterministic_source_citation_repair"
    assert result["report"]["semantic_attempt_count"] == 0
    assert "[s1]" in result["memo"]


def test_memo_ready_repair_retries_one_semantic_non_improvement(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    weak_memo = "## Decision Brief\n\nOption A may help.\n"
    before = build_memo_ready_packet_retention_report(weak_memo, packet)
    repaired = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]
    responses = iter([weak_memo, repaired])

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=next(responses), backend="fake")

    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend",
        fake_backend,
    )

    result = run_memo_ready_packet_repair(
        weak_memo,
        packet,
        before,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["accepted"] is True
    assert result["report"]["semantic_attempt_count"] == 2
    assert result["report"]["semantic_attempt_statuses"] == ["no_retention_improvement_kept_original", "accepted"]
