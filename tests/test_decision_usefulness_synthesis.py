from __future__ import annotations

import pytest

from epistemic_case_mapper.map_briefing_memo_ready_finalization import run_memo_ready_packet_synthesis
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_decision_writer_packet import _decision_usefulness_packet


def test_memo_synthesis_runs_decision_usefulness_repair_when_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = _decision_usefulness_packet()
    calls = {"count": 0}

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls["count"] += 1
        if "Missing decision-support rows" in prompt:
            return ModelBackendResult(
                text=(
                    "# Decision Memo: Option A\n\n"
                    "**Decision Question:** Should option A be adopted?\n"
                    "**Bottom Line:** Adopt option A conditionally.\n\n"
                    "## Why This Is the Best Current Read\n"
                    "The useful distinction is not whether Option A helps at all, but whether the outcome gain remains worth the implementation burden. "
                    "The direct outcome evidence carries the answer, while implementation evidence bounds it. "
                    "The key tradeoff is outcome gain versus implementation burden. Adopt if burden remains manageable, "
                    "but delay if burden rises [s1].\n\n"
                    "## What Could Change or Bound the Answer\n"
                    "The crux is whether implementation burden stays below the acceptable threshold. "
                    "New implementation failure evidence would shift the read from adoption to delay [s1].\n\n"
                    "## Practical Implication\n"
                    "Proceed only while implementation burden remains manageable.\n"
                ),
                backend="fake",
            )
        return ModelBackendResult(
            text=(
                "# Decision Memo: Option A\n\n"
                "**Decision Question:** Should option A be adopted?\n"
                "**Bottom Line:** Adopt option A conditionally.\n\n"
                "## Why This Is the Best Current Read\n"
                "The main outcome improves.\n\n"
                "## What Could Change or Bound the Answer\n"
                "Implementation risk matters.\n\n"
                "## Practical Implication\n"
                "Proceed carefully.\n"
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert calls["count"] == 2
    assert result["report"]["decision_usefulness_repair_report"]["applied"] is True
    assert result["report"]["decision_usefulness_surface_report"]["schema_id"] == "decision_usefulness_surface_report_v1"
    assert result["report"]["analyst_judgment_utilization_report"]["schema_id"] == "analyst_judgment_utilization_report_v1"
    assert "New implementation failure evidence" in result["memo"]
