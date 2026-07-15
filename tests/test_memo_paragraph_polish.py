from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_memo_paragraph_polish import (
    collect_parallel_paragraph_memo_polish_proposals,
    split_memo_into_polishable_paragraphs,
)
from epistemic_case_mapper.map_briefing_memo_polish_experiments import run_memo_ready_paragraph_final_polish_experiment
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_split_memo_into_polishable_paragraphs_skips_sources_and_flags_issues() -> None:
    memo = (
        "# Memo\n\n"
        "**Decision Question:** Should option A be adopted?\n\n"
        "Supporting this is a result that needs cleanup [s1].\n\n"
        "## Practical Implication\n\n"
        "Use option A when monitoring...\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )

    rows = split_memo_into_polishable_paragraphs(memo)

    assert [row["section_heading"] for row in rows] == ["Opening", "Opening", "Practical Implication"]
    assert "stock_phrase" in rows[1]["issues"]
    assert "unfinished" in rows[2]["issues"]
    assert all("Source A" not in row["markdown"] for row in rows)


def test_split_memo_into_polishable_paragraphs_tracks_heading_with_paragraph_body() -> None:
    memo = (
        "# Memo\n\n"
        "Opening text [s1].\n\n"
        "## Why This Matters\n"
        "Supporting this is a result [s1].\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )

    rows = split_memo_into_polishable_paragraphs(memo)

    assert rows[1]["section_heading"] == "Why This Matters"


def test_paragraph_polish_collects_only_flagged_paragraphs() -> None:
    memo = _memo()
    packet = _packet()
    prompts: list[str] = []

    def fake_runner(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        return ModelBackendResult(
            text=json.dumps(
                {
                    "paragraph_markdown": "Use option A when monitoring remains feasible [s1].",
                    "reason": "finished truncation",
                }
            ),
            backend="fake",
        )

    result = collect_parallel_paragraph_memo_polish_proposals(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_model=fake_runner,
    )

    assert len(prompts) == 1
    assert result["report"]["selected_paragraph_count"] == 1
    assert result["report"]["accepted_candidate_count"] == 1


def test_paragraph_polish_prioritizes_unfinished_over_stock_phrases() -> None:
    memo = (
        "# Memo\n\n"
        "**Decision Question:** Should option A be adopted?\n\n"
        "Supporting this is first evidence [s1].\n\n"
        "Supporting this is second evidence [s1].\n\n"
        "## Practical Implication\n\n"
        "Use option A when monitoring...\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )
    packet = _packet()
    prompts: list[str] = []

    def fake_runner(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        return ModelBackendResult(
            text=json.dumps(
                {
                    "paragraph_markdown": "Use option A when monitoring remains feasible [s1].",
                    "reason": "finished truncation",
                }
            ),
            backend="fake",
        )

    result = collect_parallel_paragraph_memo_polish_proposals(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        max_paragraphs=1,
        run_model=fake_runner,
    )

    selected = result["report"]["selected_paragraphs"]
    assert selected[0]["issues"] == ["unfinished"]
    assert "Use option A when monitoring..." in prompts[0]


def test_paragraph_final_polish_applies_safe_replacement(monkeypatch) -> None:
    memo = _memo()
    packet = _packet()

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(
            text=json.dumps(
                {
                    "paragraph_markdown": "Use option A when monitoring remains feasible [s1].",
                    "reason": "finished truncation",
                }
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_polish_experiments.run_model_backend", fake_backend)

    result = run_memo_ready_paragraph_final_polish_experiment(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted"
    assert "monitoring remains feasible" in result["memo"]
    assert "..." not in result["memo"]


def _memo() -> str:
    return (
        "# Memo\n\n"
        "**Decision Question:** Should option A be adopted?\n\n"
        "**Bottom Line:** Adopt option A when monitoring remains feasible [s1].\n\n"
        "## Practical Implication\n\n"
        "Use option A when monitoring...\n\n"
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
                "reader_claim": "Outcome evidence supports option A with feasible monitoring.",
                "source_ids": ["s1"],
                "source_label": "Source A",
                "must_use": True,
            }
        ],
    }
