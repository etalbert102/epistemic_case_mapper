from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_full_memo_polish import build_full_memo_warning_repair_prompt
from epistemic_case_mapper.map_briefing_warning_repair import run_full_memo_warning_repair
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_warning_repair_prompt_requests_natural_integrated_edits() -> None:
    prompt = build_full_memo_warning_repair_prompt(
        "## Decision Brief\n\nThe answer is bounded.\n",
        ["polish dropped required evidence: The estimate was 0.96."],
        {"suggested_insertions": ["The estimate was 0.96."], "final_source_list": ["Study A"]},
    )

    assert "natural edit in the most relevant existing sentence or paragraph" in prompt
    assert "Do not paste checklist fragments mechanically" in prompt
    assert "Prefer replacing the surrounding sentence or short paragraph" in prompt


def test_warning_repair_rejects_warning_reduction_that_worsens_readability(monkeypatch) -> None:
    original = _memo("The evidence supports a bounded read.")
    ugly_repair = _memo(
        "The evidence supports a bounded read, and the repair also inserts a required estimate of 0.96 by adding a very long sentence that keeps going through multiple qualifications and caveats and additional contextual phrases until it is hard for a human reader to parse cleanly in a decision memo."
    )

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        return ModelBackendResult(text=ugly_repair, backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_warning_repair.run_model_backend", fake_backend)

    result = run_full_memo_warning_repair(
        original,
        ["polish dropped required number: 0.96"],
        original_memo=original,
        evidence_appendix="",
        scaffold={},
        candidate_map={},
        contract=_contract(),
        obligation_packet={"required_numbers": ["0.96"], "required_sources": ["Study A"]},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        repair_candidate=lambda markdown, _scaffold, _contract: markdown,
        validate_candidate=lambda *_args: [],
        preservation_issues_fn=lambda *_args, **_kwargs: [],
        judge_fn=lambda **_kwargs: {"payload": {"accepted": True}},
        judge_issues_fn=lambda _payload: [],
    )

    assert result["accepted"] is False
    assert result["memo"] == original
    assert result["report"]["status"] == "warning_repair_readability_regression_kept_original"
    assert "warning repair increased long sentence count" in result["report"]["issues"]


def test_warning_repair_accepts_fluent_warning_reduction(monkeypatch) -> None:
    original = _memo("The evidence supports a bounded read.")
    fluent_repair = _memo("The evidence supports a bounded read. The key estimate was 0.96.")

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        return ModelBackendResult(text=fluent_repair, backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_warning_repair.run_model_backend", fake_backend)

    result = run_full_memo_warning_repair(
        original,
        ["polish dropped required number: 0.96"],
        original_memo=original,
        evidence_appendix="",
        scaffold={},
        candidate_map={},
        contract=_contract(),
        obligation_packet={"required_numbers": ["0.96"], "required_sources": ["Study A"]},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        repair_candidate=lambda markdown, _scaffold, _contract: markdown,
        validate_candidate=lambda *_args: [],
        preservation_issues_fn=lambda *_args, **_kwargs: [],
        judge_fn=lambda **_kwargs: {"payload": {"accepted": True}},
        judge_issues_fn=lambda _payload: [],
    )

    assert result["accepted"] is True
    assert result["report"]["status"] == "accepted"
    assert "The key estimate was 0.96." in result["memo"]


def _contract() -> dict[str, Any]:
    return {
        "question": "Should this be treated as decision-ready?",
        "confidence": "medium",
    }


def _memo(body: str) -> str:
    return (
        "## Decision Brief\n\n"
        "**Decision question:** Should this be treated as decision-ready?\n\n"
        f"{body}\n\n"
        "**Confidence:** medium\n\n"
        "## Sources\n\n"
        "- Study A\n"
    )
