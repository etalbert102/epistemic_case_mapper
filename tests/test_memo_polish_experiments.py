from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_polish_experiments import (
    deterministic_reader_quality_report,
    render_memo_polish_experiment_matrix_markdown,
    run_memo_polish_experiment_matrix,
)


def test_deterministic_reader_quality_penalizes_unfinished_stock_prose() -> None:
    clean = "# Memo\n\n**Bottom Line:** Use option A [s1].\n\n## Practical Implication\n\nUse option A when monitoring remains feasible [s1]."
    rough = "# Memo\n\n**Bottom Line:** Use option A [s1].\n\n## Practical Implication\n\nSupporting this is evidence that option A..."
    packet = {"decision_question": "Should option A be adopted?", "source_trail": [{"source_id": "s1"}]}

    clean_report = deterministic_reader_quality_report(clean, packet)
    rough_report = deterministic_reader_quality_report(rough, packet)

    assert clean_report["reader_quality_score"] > rough_report["reader_quality_score"]
    assert rough_report["has_unfinished_marker"] is True
    assert rough_report["stock_phrase_count"] == 1


def test_polish_experiment_matrix_runs_prompt_backend() -> None:
    memo = "# Memo\n\n**Decision Question:** Should option A be adopted?\n\n**Bottom Line:** Use option A [s1]."
    packet = {"decision_question": "Should option A be adopted?", "source_trail": [{"source_id": "s1"}]}

    result = run_memo_polish_experiment_matrix(
        memo,
        packet,
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
        variants=["baseline_no_polish", "presentation_only"],
    )

    summary = result["summary"]
    assert summary["variant_count"] == 2
    assert [row["variant"] for row in summary["variants"]] == ["baseline_no_polish", "presentation_only"]
    assert "promotion_candidates" in summary


def test_polish_experiment_matrix_markdown_renders_table() -> None:
    markdown = render_memo_polish_experiment_matrix_markdown(
        {
            "backend": "prompt",
            "variants": [
                {
                    "variant": "baseline_no_polish",
                    "accepted": True,
                    "reader_quality_score": 70,
                    "missing_mandatory_count": 0,
                    "missing_quantity_count": 0,
                    "prose_warning_count": 0,
                    "stock_phrase_count": 0,
                    "has_unfinished_marker": False,
                    "promotion_candidate": True,
                }
            ],
            "promotion_candidates": [{"variant": "baseline_no_polish", "reader_quality_score": 70}],
        }
    )

    assert "| Variant | Accepted | Reader score |" in markdown
    assert "`baseline_no_polish`" in markdown


def test_polish_experiment_matrix_promotion_gate_allows_moderate_warnings() -> None:
    memo = "# Memo\n\n**Decision Question:** Should option A be adopted?\n\n**Bottom Line:** Use option A [s1].\n\n## Practical Implication\n\nUse option A when monitoring remains feasible [s1]."
    packet = {"decision_question": "Should option A be adopted?", "source_trail": [{"source_id": "s1"}]}

    result = run_memo_polish_experiment_matrix(
        memo,
        packet,
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
        variants=["baseline_no_polish"],
    )

    row = result["summary"]["variants"][0]
    assert row["high_unsupported_addition_count"] == 0
    assert row["promotion_candidate"] is True
