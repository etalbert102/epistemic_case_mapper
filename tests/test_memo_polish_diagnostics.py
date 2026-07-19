from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_polish_diagnostics import (
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


def test_polish_diagnostics_allows_packet_supported_editorial_paraphrase() -> None:
    before = "## Decision Brief\n\nDietary cholesterol is not a significant CVD driver for most people [s1]."
    after = (
        "## Decision Brief\n\nDietary cholesterol is not a significant CVD driver for most people, "
        "supporting heart-healthy patterns rather than strict cholesterol-based restrictions [s1]."
    )
    packet = {
        "answer_spine": {
            "scope": "supporting a shift toward heart-healthy patterns",
            "boundary": "a shift in official guidelines back to strict individual cholesterol limits would change the answer",
        },
        "evidence_items": [
            {
                "claim": "People with high LDL-c may still require restriction of saturated fats and dietary cholesterol.",
                "source_ids": ["s1"],
            }
        ],
    }

    diagnostics = build_memo_polish_diagnostics(before, after, packet)

    assert diagnostics["unsupported_addition_count"] == 0
    assert not high_confidence_unsupported_additions(diagnostics)


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


def test_prose_quality_diagnostics_flags_unfinished_sentence_marker() -> None:
    diagnostics = prose_quality_diagnostics("## Memo\n\nThe final implication is LDL...")

    assert diagnostics["status"] == "warning"
    assert "unfinished_sentence_markers" in diagnostics["warnings"]
    assert diagnostics["unfinished_sentence_markers"][0]["paragraph_index"] == 2
