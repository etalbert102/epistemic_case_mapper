from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    run_memo_ready_hybrid_section_final_polish_experiment,
    run_memo_ready_section_final_polish_experiment,
)
from epistemic_case_mapper.map_briefing_memo_section_polish import (
    collect_parallel_hybrid_section_memo_polish_proposals,
    collect_parallel_section_memo_polish_proposals,
    score_section_polish_candidate,
    split_memo_into_polish_sections,
)
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_split_memo_into_polish_sections_includes_opening_and_skips_sources() -> None:
    memo = (
        "# Memo\n\n"
        "**Decision Question:** Should option A be adopted?\n\n"
        "**Bottom Line:** Adopt option A [s1].\n\n"
        "## Why\n\n"
        "Evidence supports option A [s1].\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )

    sections = split_memo_into_polish_sections(memo)

    assert [section["section_id"] for section in sections] == ["opening", "why"]
    assert sections[0]["heading"] == "Opening"
    assert sections[1]["markdown"].startswith("## Why")


def test_section_polish_collects_one_prompt_per_polishable_section() -> None:
    memo = _memo()
    packet = _packet()
    prompts: list[str] = []

    def fake_runner(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        heading = _heading_for_prompt(prompt)
        markdown = _section_markdown_for_heading(memo, heading)
        return ModelBackendResult(text=json.dumps({"section_markdown": markdown, "reason": "unchanged"}), backend="fake")

    result = collect_parallel_section_memo_polish_proposals(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_model=fake_runner,
    )

    assert len(prompts) == 4
    assert result["report"]["section_count"] == 4
    assert result["report"]["accepted_candidate_count"] == 4
    assert all("Current section markdown" in prompt for prompt in prompts)
    assert all("evidence_language_contracts" in prompt for prompt in prompts)


def test_section_final_polish_experiment_accepts_section_replacement(monkeypatch) -> None:
    memo = _memo()
    packet = _packet()

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_for_prompt(prompt)
        if heading == "Practical Implication":
            markdown = "## Practical Implication\n\nUse option A when monitoring remains feasible [s1]."
        else:
            markdown = _section_markdown_for_heading(memo, heading)
        return ModelBackendResult(text=json.dumps({"section_markdown": markdown, "reason": "section polish"}), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_section_final_polish_experiment(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted"
    assert result["report"]["accepted_section_count"] == 1
    assert "Use option A when monitoring remains feasible [s1]." in result["memo"]
    assert "## Sources" in result["memo"]


def test_section_candidate_scoring_penalizes_shaky_expansion() -> None:
    section = {"section_id": "practical_implication", "markdown": "## Practical Implication\n\nUse option A [s1]."}

    concise = score_section_polish_candidate(
        section,
        "## Practical Implication\n\nUse option A when monitoring remains feasible [s1].",
        issues=[],
    )
    shaky = score_section_polish_candidate(
        section,
        "## Practical Implication\n\nUse option A because mortality improves through a causal mechanism [s1].",
        issues=[],
    )

    assert concise["score"] > shaky["score"]


def test_hybrid_section_polish_falls_through_to_next_candidate(monkeypatch) -> None:
    memo = _memo()
    packet = _packet()
    calls: dict[str, int] = {}

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_for_prompt(prompt)
        mode = _mode_for_prompt(prompt)
        calls[f"{heading}:{mode}"] = calls.get(f"{heading}:{mode}", 0) + 1
        markdown = _section_markdown_for_heading(memo, heading)
        if heading == "Practical Implication" and mode == "concise_safe":
            markdown = "## Practical Implication\n\nUse option A because a new mortality mechanism is proven [s1]."
        elif heading == "Practical Implication" and mode == "decision_grade":
            markdown = "## Practical Implication\n\nUse option A when monitoring remains feasible [s1]."
        return ModelBackendResult(text=json.dumps({"section_markdown": markdown, "reason": mode}), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_hybrid_section_final_polish_experiment(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted"
    assert "Use option A when monitoring remains feasible [s1]." in result["memo"]
    assert "mortality mechanism" not in result["memo"]


def test_section_polish_rejects_new_forbidden_language_from_contract() -> None:
    memo = _memo()
    packet = _packet()

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_for_prompt(prompt)
        markdown = _section_markdown_for_heading(memo, heading)
        if heading == "Why This Is the Best Current Read":
            markdown = "## Why This Is the Best Current Read\n\nOutcome evidence proves option A causes better results by 20% [s1]."
        return ModelBackendResult(text=json.dumps({"section_markdown": markdown, "reason": "too strong"}), backend="fake")

    result = collect_parallel_section_memo_polish_proposals(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_model=fake_backend,
    )

    why = [row for row in result["section_reports"] if row["section_id"] == "why_this_is_the_best_current_read"][0]
    assert why["accepted_candidate"] is False
    assert any("unsupported_language_for_sources:s1" in issue for issue in why["issues"])


def test_hybrid_section_polish_adds_completion_only_for_unfinished_sections() -> None:
    memo = _memo().replace("Option A may help [s1].", "Option A may help when monitoring...")
    packet = _packet()
    prompts: list[str] = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        heading = _heading_for_prompt(prompt)
        mode = _mode_for_prompt(prompt)
        markdown = _section_markdown_for_heading(memo, heading)
        if heading == "Practical Implication" and mode == "completion_only":
            markdown = "## Practical Implication\n\nOption A may help when monitoring remains feasible [s1]."
        elif heading == "Practical Implication":
            markdown = "## Practical Implication\n\nOption A may help because a new causal mortality mechanism is proven [s1]."
        return ModelBackendResult(text=json.dumps({"section_markdown": markdown, "reason": mode}), backend="fake")

    result = collect_parallel_hybrid_section_memo_polish_proposals(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_model=fake_backend,
    )

    practical = [
        row for row in result["section_reports"]
        if row["section_id"] == "practical_implication"
    ][0]
    assert any("mode_id: completion_only" in prompt for prompt in prompts)
    assert practical["selected_mode_id"] == "completion_only"
    assert practical["accepted_candidate"] is True
    assert "monitoring remains feasible" in practical["replacement_markdown"]


def _memo() -> str:
    return (
        "# Memo\n\n"
        "**Decision Question:** Should option A be adopted?\n\n"
        "**Bottom Line:** Adopt option A when monitoring remains feasible [s1].\n\n"
        "## Why This Is the Best Current Read\n\n"
        "Outcome evidence supports option A by 20% with feasible monitoring [s1].\n\n"
        "## What Could Change or Bound the Answer\n\n"
        "The read would change if monitoring became infeasible [s1].\n\n"
        "## Practical Implication\n\n"
        "Option A may help [s1].\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )


def _packet() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "source_trail": [{"source_id": "s1", "source_label": "Source A"}],
        "evidence_items": [
            {
                "item_id": "item_1",
                "reader_claim": "Outcome evidence supports option A by 20% with feasible monitoring.",
                "source_ids": ["s1"],
                "source_label": "Source A",
                "quantities": [{"value": "20%"}],
                "must_use": True,
            }
        ],
        "canonical_decision_writer_packet": {
            "evidence_language_contracts": [
                {
                    "contract_id": "language_contract_001",
                    "source_ids": ["s1"],
                    "evidence_design": "observational",
                    "allowed_language": ["is associated with", "suggests"],
                    "avoid_language": ["proves", "proven", "causes"],
                    "wording_rule": "Phrase as association or suggestive evidence unless another source supplies causal support.",
                }
            ]
        },
    }


def _heading_for_prompt(prompt: str) -> str:
    marker = "Section heading:"
    for line in prompt.splitlines():
        if line.startswith(marker):
            return line.removeprefix(marker).strip()
    return "Opening"


def _mode_for_prompt(prompt: str) -> str:
    marker = "- mode_id:"
    for line in prompt.splitlines():
        if line.startswith(marker):
            return line.removeprefix(marker).strip()
    return ""


def _section_markdown_for_heading(memo: str, heading: str) -> str:
    if heading == "Opening":
        return memo.split("## Why This Is the Best Current Read", 1)[0].strip()
    marker = f"## {heading}"
    tail = memo.split(marker, 1)[1]
    next_heading = tail.find("\n## ")
    body = tail[:next_heading] if next_heading >= 0 else tail
    return f"{marker}{body}".strip()
