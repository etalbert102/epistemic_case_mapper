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
from test_decision_writer_packet import _decision_usefulness_packet


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
    assert result["report"]["polish_comparison"]["schema_id"] == "memo_ready_final_polish_comparison_v1"
    assert result["report"]["polish_comparison"]["after_missing_mandatory_count"] <= result["report"]["polish_comparison"]["before_missing_mandatory_count"]
    assert result["report"]["polish_comparison"]["unsupported_addition_count"] == 0
    assert "legacy systems" not in result["memo"]


def test_final_polish_rejects_decision_usefulness_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = _decision_usefulness_packet()
    memo = (
        "# Decision Memo: Option A\n\n"
        "**Decision Question:** Should option A be adopted?\n"
        "**Bottom Line:** Adopt option A conditionally.\n\n"
        "## Why This Is the Best Current Read\n"
        "The useful distinction is whether the outcome gain remains worth the implementation burden. "
        "The direct outcome evidence carries the answer, while implementation evidence bounds it. "
        "The key tradeoff is outcome gain versus implementation burden: adopt if burden remains manageable, "
        "but delay if burden rises [s1].\n\n"
        "## What Could Change or Bound the Answer\n"
        "The crux is whether implementation burden stays below the acceptable threshold. "
        "New implementation failure evidence would shift the read from adoption to delay [s1].\n\n"
        "## Practical Implication\n"
        "Proceed only while implementation burden remains manageable.\n"
    )
    regressed = memo.replace(
        "New implementation failure evidence would shift the read from adoption to delay [s1].",
        "Implementation evidence remains worth monitoring [s1].",
    )

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=regressed, backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_final_polish(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "rejected_kept_original"
    assert result["report"]["decision_usefulness_not_worse"] is False
    assert result["memo"] == memo


def _packet_and_memo() -> tuple[dict, str]:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    memo = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]
    return packet, memo
