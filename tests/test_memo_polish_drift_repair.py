from __future__ import annotations

import pytest

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    run_memo_ready_final_polish,
    run_memo_ready_packet_synthesis,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_decision_briefing_packet import _scaffold


def test_final_polish_rejects_unsupported_addition_when_repair_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    packet, memo = _packet_and_memo()
    drift = memo + "\nOption A is also a better replacement for high-risk legacy systems [s1].\n"

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=drift, backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_final_polish(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "rejected_unsupported_additions_kept_original"
    assert result["report"]["drift_repair_report"]["status"] == "rejected_kept_polish_candidate_for_rejection"
    assert result["memo"] == memo


def test_final_polish_accepts_targeted_repair_that_removes_unsupported_addition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, memo = _packet_and_memo()
    drift = memo + "\nOption A is also a better replacement for high-risk legacy systems [s1].\n"
    repaired = memo.replace("Option A", "Option A", 1)
    calls = {"count": 0}

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls["count"] += 1
        if "Repair a polished decision memo" in prompt:
            return ModelBackendResult(text=repaired, backend="fake")
        return ModelBackendResult(text=drift, backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_final_polish(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert calls["count"] == 2
    assert result["report"]["status"] == "accepted"
    assert result["report"]["drift_repair_report"]["status"] == "accepted"
    assert "legacy systems" not in result["memo"]


def _packet_and_memo() -> tuple[dict, str]:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    memo = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]
    return packet, memo
