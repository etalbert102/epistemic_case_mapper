from __future__ import annotations

import json

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import (
    build_validated_final_polish_prompt,
    build_validated_final_polish_validation_report,
    run_memo_ready_final_polish,
    run_memo_ready_hybrid_section_final_polish_experiment,
    run_memo_ready_section_final_polish_experiment,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_section_polish import (
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

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

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

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

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


def test_validated_final_polish_uses_backend_override_and_accepts_safe_rewrite(monkeypatch) -> None:
    memo = _memo()
    packet = _packet()
    captured: dict[str, str] = {}

    def fake_backend(prompt: str, backend: str, *args, **kwargs) -> ModelBackendResult:
        captured["backend"] = backend
        assert "Important quantities to keep when relevant" in prompt
        return ModelBackendResult(
            text=memo.replace("Option A may help [s1].", "Use option A when monitoring remains feasible and the 20% evidence applies [s1]."),
            backend=backend,
        )

    monkeypatch.setenv("ECM_FINAL_POLISH_BACKEND", "ollama:strong-polish")
    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_final_polish(memo, packet, backend="ollama:small", backend_timeout=30, backend_retries=0)

    assert captured["backend"] == "ollama:strong-polish"
    assert result["report"]["method"] == "validated_decision_editor_rewrite"
    assert result["report"]["accepted"] is True
    assert "Use option A when monitoring remains feasible" in result["memo"]


def test_validated_final_polish_prompt_asks_for_decision_editor_rewrite() -> None:
    prompt = build_validated_final_polish_prompt(_memo(), _packet())

    assert "expert decision analyst" in prompt
    assert "Optimize for decision usefulness" in prompt
    assert "Integrate source weighting into the argument" in prompt
    assert "Leave source lists, reference definitions, and citation trace formatting to deterministic presentation" in prompt
    assert "## Sources" not in prompt.split("Memo body:", 1)[-1]


def test_validated_final_polish_repairs_missing_priority_quantity(monkeypatch) -> None:
    memo = _memo()
    packet = _packet()
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        if "Validation feedback" in prompt:
            return ModelBackendResult(text=memo, backend=backend)
        return ModelBackendResult(
            text=memo.replace("20% with feasible monitoring", "feasible monitoring"),
            backend=backend,
        )

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_final_polish(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert len(calls) == 2
    assert result["report"]["repair_report"]["status"] == "accepted"
    assert result["report"]["accepted"] is True
    assert "20%" in result["memo"]
    assert "Validation feedback" in result["repair_prompt"]
    assert "20%" in result["repair_raw"]


def test_validated_final_polish_cleanup_fixes_surface_corruption(monkeypatch) -> None:
    memo = _memo().replace("20% with feasible monitoring", "20% with feasible monitoring for one egg per day")
    packet = _packet()
    packet["evidence_items"][0]["reader_claim"] = "Outcome evidence supports option A by 20% with feasible monitoring for one egg per day."

    def fake_backend(prompt: str, backend: str, *args, **kwargs) -> ModelBackendResult:
        candidate = memo.replace("one egg per day", "one egg per 1 day")
        candidate = candidate.replace("Option A may help [s1].", "Option A may help [s1].; This remains bounded.")
        return ModelBackendResult(text=candidate, backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_final_polish(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["accepted"] is True
    assert "one egg per 1 day" not in result["memo"]
    assert "one egg per day" in result["memo"]
    assert ".; This" not in result["memo"]


def test_validated_final_polish_rejects_unsupported_additions(monkeypatch) -> None:
    memo = _memo()
    packet = _packet()

    def fake_backend(prompt: str, backend: str, *args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(
            text=memo.replace(
                "Option A may help [s1].",
                "Option A may help [s1]. It is also a better replacement for high-risk legacy systems [s1].",
            ),
            backend=backend,
        )

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_final_polish(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)
    warning_report = result["report"]["final_validation_report"]["unsupported_additions_report"]

    assert result["report"]["status"] == "rejected_kept_original"
    assert result["report"]["accepted"] is False
    assert result["report"]["applied"] is False
    assert result["memo"] == memo
    assert "legacy systems" not in result["memo"]
    assert "unsupported_additions" in result["report"]["final_validation_report"]["hard_failures"]
    assert warning_report["status"] == "warning"
    assert warning_report["policy"] == "blocking_for_final_editor_acceptance"
    assert warning_report["warnings"][0]["sentence"].startswith("It is also a better replacement")
    assert "legacy" in warning_report["warnings"][0]["new_terms"]


def test_validated_final_polish_validation_detects_duplicate_source_sections() -> None:
    memo = (
        _memo().replace(
            "## Why This Is the Best Current Read",
            "## How to Weight the Evidence\n\nUse Source A for the main read [s1].\n\n## Source Weighting\n\nUse Source A as the driver [s1].\n\n## Why This Is the Best Current Read",
        )
    )

    report = build_validated_final_polish_validation_report(memo, _packet(), original_memo=_memo())

    assert "duplicate_section_structure" in report["issues"]


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
