from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_citation_trace_markdown,
    build_memo_ready_packet_retention_report,
    run_memo_ready_presentation_normalization,
)


def test_presentation_normalization_uses_compact_inline_citations_with_full_sources() -> None:
    source = "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis"
    packet = {
        "decision_question": "Should dietary advice treat eggs as neutral?",
        "source_trail": [
            {
                "source_id": "bmj_2020_egg_consumption_cvd",
                "source_label": source,
                "source_url": "https://example.test/bmj-2020",
            }
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "One egg per day was not associated with higher cardiovascular risk.",
                "source_label": source,
                "quantities": [{"value": "one egg per day"}],
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nOne egg per day was not associated with higher cardiovascular risk [bmj_2020_egg_consumption_cvd]."

    result = run_memo_ready_presentation_normalization(memo, packet)
    retention = build_memo_ready_packet_retention_report(result["memo"], packet)

    assert "[BMJ 2020]" in result["memo"]
    assert "[[BMJ 2020](CITATION_TRACE.md#bmj-2020)]" in result["memo"]
    assert "[bmj_2020_egg_consumption_cvd]" not in result["memo"]
    assert "* [BMJ 2020](https://example.test/bmj-2020)" in result["memo"]
    assert "](https://example.test/bmj-2020)" in result["memo"]
    assert retention["missing_mandatory_count"] == 0


def test_presentation_prefers_citation_label_over_long_display_label() -> None:
    long_title = (
        "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, "
        "systematic review, and updated meta-analysis"
    )
    packet = {
        "decision_question": "Should dietary advice treat eggs as neutral?",
        "source_trail": [
            {
                "source_id": "bmj_2020_egg_consumption_cvd",
                "source_label": "Drouin-Chartier et al. 2020",
                "citation_label": "Drouin-Chartier et al. 2020",
                "display_label": long_title,
                "source_url": "https://example.test/bmj-2020",
            }
        ],
        "evidence_items": [],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Moderate egg intake was not associated with cardiovascular risk [bmj_2020_egg_consumption_cvd]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    trace = build_citation_trace_markdown(result["memo"], packet)

    assert "[[Drouin-Chartier et al. 2020](CITATION_TRACE.md#drouin-chartier-et-al-2020)]" in result["memo"]
    assert "* [Drouin-Chartier et al. 2020](https://example.test/bmj-2020)" in result["memo"]
    assert "[bmj_2020_egg_consumption_cvd]" not in result["memo"]
    assert long_title not in result["memo"]
    assert f"- Source title: {long_title}" in trace


def test_presentation_compact_citations_title_case_short_names() -> None:
    packet = {
        "source_trail": [{"source_id": "li_2020_egg_cholesterol_rct_meta", "source_label": "Long Source"}],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nThe trial evidence changed LDL-c [li_2020_egg_cholesterol_rct_meta]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[[Li 2020](CITATION_TRACE.md#li-2020)]" in result["memo"]
    assert "[LI 2020]" not in result["memo"]


def test_presentation_normalizes_malformed_source_id_and_evidence_item_citations() -> None:
    packet = {
        "source_trail": [
            {
                "source_id": "li_2020_egg_cholesterol_rct_meta",
                "source_label": "Li et al. 2020",
                "citation_label": "Li et al. 2020",
                "source_url": "https://example.test/li",
            },
            {
                "source_id": "nnr_2023_eggs_scoping_review",
                "source_label": "NNR 2023",
                "citation_label": "NNR 2023",
                "source_url": "https://example.test/nnr",
            },
        ],
        "evidence_items": [
            {
                "item_id": "analyst_item_004",
                "source_ids": ["nnr_2023_eggs_scoping_review"],
                "source_labels": ["NNR 2023"],
                "reader_claim": "Moderate egg intake did not increase stroke risk.",
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "LDL markers moved [Li et2020_egg_cholesterol_rct_meta]. "
        "Stroke evidence was neutral [analyst_item_004]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[Li et2020_egg_cholesterol_rct_meta]" not in result["memo"]
    assert "[analyst_item_004]" not in result["memo"]
    assert "[[Li et al. 2020](CITATION_TRACE.md#li-et-al-2020)]" in result["memo"]
    assert "[[NNR 2023](CITATION_TRACE.md#nnr-2023)]" in result["memo"]


def test_presentation_compacts_crowded_inline_citations_without_losing_sources() -> None:
    packet = {
        "decision_question": "Should eggs be treated as neutral?",
        "source_trail": [
            {"source_id": "nnr_2023_eggs_scoping_review", "source_label": "Eggs - a scoping review for Nordic Nutrition Recommendations 2023"},
            {"source_id": "bmj_2020_egg_consumption_cvd", "source_label": "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis"},
            {"source_id": "aha_2023_dietary_cholesterol_news", "source_label": "Here's the latest on dietary cholesterol and how it fits in with a healthy diet"},
            {"source_id": "aha_2019_dietary_cholesterol_pubmed", "source_label": "Dietary Cholesterol and Cardiovascular Risk: A Science Advisory From the American Heart Association"},
            {"source_id": "jama_2019_dietary_cholesterol_eggs", "source_label": "Associations of Dietary Cholesterol or Egg Consumption With Incident Cardiovascular Disease and Mortality"},
            {"source_id": "dga_2020_2025_pmc_summary", "source_label": "Dietary Guidelines for Americans, 2020-2025"},
        ],
        "evidence_items": [],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Moderate intake is neutral [nnr_2023_eggs_scoping_review, bmj_2020_egg_consumption_cvd, "
        "aha_2023_dietary_cholesterol_news, aha_2019_dietary_cholesterol_pubmed, "
        "jama_2019_dietary_cholesterol_eggs, dga_2020_2025_pmc_summary]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert (
        "[[NNR 2023](CITATION_TRACE.md#nnr-2023); "
        "[BMJ 2020](CITATION_TRACE.md#bmj-2020); +4 sources][^sources-1]"
    ) in result["memo"]
    assert (
        "[^sources-1]: Additional sources: [AHA 2023](CITATION_TRACE.md#aha-2023); "
        "[AHA 2019](CITATION_TRACE.md#aha-2019); [JAMA 2019](CITATION_TRACE.md#jama-2019); "
        "[DGA 2020](CITATION_TRACE.md#dga-2020)."
    ) in result["memo"]
    assert result["memo"].index("[^sources-1]:") < result["memo"].index("## Sources")
    assert "[NNR 2023, BMJ 2020, AHA 2023" not in result["memo"]
    assert "* NNR 2023" in result["memo"]
    assert "* BMJ 2020" in result["memo"]
    assert "* AHA 2023" in result["memo"]
    assert "* AHA 2019" in result["memo"]
    assert "* JAMA 2019" in result["memo"]
    assert "* DGA 2020" in result["memo"]
    assert "compacted_crowded_citations" in result["report"]["changes"]


def test_citation_trace_records_packet_evidence_without_replacing_source_urls() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [
            {
                "source_id": "outcome_2025",
                "source_label": "Outcome Study 2025",
                "source_url": "https://example.test/outcome",
            }
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "role": "scope_boundary",
                "reader_claim": "The effect is limited to the studied population.",
                "source_labels": ["Outcome Study 2025"],
                "quantities": [{"value": "42%", "interpretation": "event rate in the studied group"}],
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nThe effect is limited to the studied population [outcome_2025]."

    result = run_memo_ready_presentation_normalization(memo, packet)
    trace = build_citation_trace_markdown(result["memo"], packet)

    assert "[[Outcome 2025](CITATION_TRACE.md#outcome-2025)]" in result["memo"]
    assert "* [Outcome 2025](https://example.test/outcome)" in result["memo"]
    assert "## Outcome 2025" in trace
    assert "- Source ID: `outcome_2025`" in trace
    assert "- External URL: https://example.test/outcome" in trace
    assert "`item_001` (scope_boundary): The effect is limited to the studied population." in trace
    assert "42%: event rate in the studied group" in trace


def test_presentation_links_parenthetical_citations_and_records_memo_contexts() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [
            {
                "source_id": "bmj_2020_egg_consumption_cvd",
                "source_label": "Egg consumption and risk of cardiovascular disease",
                "source_url": "https://example.test/bmj",
            },
            {
                "source_id": "nnr_2023_eggs_scoping_review",
                "source_label": "Nordic Nutrition Recommendations evidence review authors 2023",
                "source_url": "https://example.test/nnr",
            },
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "role": "strongest_support",
                "reader_claim": "Moderate egg consumption was not associated with higher cardiovascular risk.",
                "source_label": "Egg consumption and risk of cardiovascular disease",
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Moderate intake was not associated with higher cardiovascular risk (BMJ 2020). "
        "The replacement-food question remains important (BMJ 2020; NNR 2023). "
        "The BMJ 2020 authors also framed this as a replacement-food problem."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    trace = build_citation_trace_markdown(result["memo"], packet)

    assert "([BMJ 2020](CITATION_TRACE.md#bmj-2020))" in result["memo"]
    assert "([BMJ 2020](CITATION_TRACE.md#bmj-2020); [NNR 2023](CITATION_TRACE.md#nnr-2023))" in result["memo"]
    assert "- Memo citation contexts:" in trace
    assert "Moderate intake was not associated with higher cardiovascular risk ([BMJ 2020](CITATION_TRACE.md#bmj-2020))." in trace
    assert "The replacement-food question remains important ([BMJ 2020](CITATION_TRACE.md#bmj-2020); [NNR 2023](CITATION_TRACE.md#nnr-2023))." in trace
    assert "authors also framed this" not in trace
    assert "* [BMJ 2020](https://example.test/bmj)" in result["memo"]
