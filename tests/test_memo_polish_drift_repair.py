from __future__ import annotations

import json

import pytest

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    run_memo_ready_final_polish,
    run_memo_ready_json_final_polish_experiment,
    run_memo_ready_packet_synthesis,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_decision_briefing_packet import _scaffold
from test_decision_writer_packet import _decision_usefulness_packet


def test_final_polish_skips_json_edit_that_adds_unsupported_side_point(monkeypatch: pytest.MonkeyPatch) -> None:
    packet, memo = _packet_and_memo()
    payload = {
        "edits": [
            {
                "target_text": "## Sources",
                "replacement_text": "Option A is also a better replacement for high-risk legacy systems [s1].\n\n## Sources",
                "reason": "add practical comparison",
                "intended_improvement": "clarity",
            }
        ]
    }

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_json_final_polish_experiment(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "no_safe_json_edits_kept_original"
    assert result["report"]["rejected_edits"][0]["issue"] == "unsupported_addition"
    assert result["memo"] == memo


def test_final_polish_accepts_json_edit_that_removes_existing_unsupported_side_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, memo = _packet_and_memo()
    unsupported_sentence = "Option A is also a better replacement for high-risk legacy systems [s1]."
    memo_with_drift = memo + "\n" + unsupported_sentence + "\n"
    payload = {
        "edits": [
            {
                "target_text": unsupported_sentence,
                "replacement_text": "",
                "reason": "remove unsupported side comparison",
                "intended_improvement": "unsupported_side_point",
            }
        ]
    }

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_json_final_polish_experiment(memo_with_drift, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "accepted"
    assert result["report"]["accepted_edit_count"] == 1
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
    payload = {
        "edits": [
            {
                "target_text": "New implementation failure evidence would shift the read from adoption to delay [s1].",
                "replacement_text": "Implementation evidence remains worth monitoring [s1].",
                "reason": "shorten update trigger",
                "intended_improvement": "clarity",
            }
        ]
    }

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_json_final_polish_experiment(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "no_safe_json_edits_kept_original"
    assert result["report"]["rejected_edits"][0]["issue"] == "decision_usefulness_regression"
    assert result["report"]["decision_usefulness_not_worse"] is True
    assert result["memo"] == memo


def test_production_final_polish_uses_validated_whole_memo_polish(monkeypatch: pytest.MonkeyPatch) -> None:
    packet, memo = _packet_and_memo()
    prompts: list[str] = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        if "Repair a polished decision memo" in prompt:
            return ModelBackendResult(text=memo, backend="fake")
        assert "Memo to polish:" in prompt
        return ModelBackendResult(
            text=memo.replace(
                "Recommendation: use the option with the better benefit-burden profile.",
                "Recommendation: use the option when the cited benefit evidence is still strong enough to justify the burden.",
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    memo_with_truncation = memo.replace("## Practical Implication", "## Practical Implication").rstrip() + "\n"
    if "..." not in memo_with_truncation:
        memo_with_truncation = memo_with_truncation.replace("## Sources", "The recommendation should be applied...\n\n## Sources")
    result = run_memo_ready_final_polish(memo_with_truncation, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert "Priority quantity contracts:" in prompts[0]
    assert any("Repair a polished decision memo" in prompt for prompt in prompts)
    assert result["report"]["schema_id"] == "memo_ready_final_polish_report_v1"
    assert result["report"]["method"] == "validated_whole_memo_polish"
    assert "polished_validation_report" in result["report"]
    assert "section_proposal_report" not in result["report"]


def _heading_for_prompt(prompt: str) -> str:
    marker = "Section heading:"
    for line in prompt.splitlines():
        if line.startswith(marker):
            return line.removeprefix(marker).strip()
    return "Opening"


def _section_markdown_for_heading(memo: str, heading: str) -> str:
    if heading == "Opening":
        first_heading = memo.find("\n## ")
        return memo[:first_heading].strip() if first_heading >= 0 else memo.strip()
    marker = f"## {heading}"
    if marker not in memo:
        return f"{marker}\n\n"
    tail = memo.split(marker, 1)[1]
    next_heading = tail.find("\n## ")
    body = tail[:next_heading] if next_heading >= 0 else tail
    return f"{marker}{body}".strip()


def _packet_and_memo() -> tuple[dict, str]:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    memo = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]
    return packet, memo
