from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_polish_diagnostics import (
    build_memo_polish_diagnostics,
    high_confidence_unsupported_additions,
    prose_quality_diagnostics,
)


def test_polish_diagnostics_flags_new_comparison_not_in_memo_or_packet() -> None:
    before = "## Decision Brief\n\nOption A reduces losses by 25% [s1]."
    after = before + "\n\nOption A is also a better replacement for high-risk legacy systems [s1]."
    packet = {
        "decision_question": "Should the city adopt option A?",
        "evidence_items": [{"claim": "Option A reduces losses by 25%.", "source_ids": ["s1"]}],
        "source_trail": [{"source_id": "s1", "source_label": "Outcome Study"}],
    }

    diagnostics = build_memo_polish_diagnostics(before, after, packet)

    assert diagnostics["unsupported_addition_count"] == 1
    assert high_confidence_unsupported_additions(diagnostics)
    warning = diagnostics["unsupported_addition_warnings"][0]
    assert "replacement for" in warning["cues"]
    assert "legacy" in warning["new_terms"]


def test_polish_diagnostics_allows_rephrased_existing_comparison() -> None:
    before = "## Decision Brief\n\nOption A performs better than the legacy system when maintenance is funded [s1]."
    after = "## Decision Brief\n\nWhen maintenance is funded, Option A performs better than the legacy system [s1]."
    packet = {"evidence_items": [{"claim": "Option A performs better than the legacy system."}]}

    diagnostics = build_memo_polish_diagnostics(before, after, packet)

    assert diagnostics["unsupported_addition_count"] == 0


def test_prose_quality_diagnostics_flags_repeated_starts_and_dense_citations() -> None:
    memo = (
        "## Decision Brief\n\n"
        "The evidence shows one result [s1]. The evidence shows another result [s2]. "
        "The evidence shows a third result [s3].\n\n"
        "Dense paragraph [s1] [s2] [s3] [s4] [s5]."
    )

    diagnostics = prose_quality_diagnostics(memo)

    assert diagnostics["status"] == "warning"
    assert "repeated_sentence_starts" in diagnostics["warnings"]
    assert "citation_dense_paragraphs" in diagnostics["warnings"]
