from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_retention_report,
    run_memo_ready_presentation_normalization,
)


def test_presentation_normalization_uses_compact_inline_citations_with_full_sources() -> None:
    source = "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis"
    packet = {
        "decision_question": "Should dietary advice treat eggs as neutral?",
        "source_trail": [{"source_id": "bmj_2020_egg_consumption_cvd", "source_label": source}],
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
    assert "[bmj_2020_egg_consumption_cvd]" not in result["memo"]
    assert "* Egg consumption and risk of cardiovascular disease" in result["memo"]
    assert retention["missing_mandatory_count"] == 0


def test_presentation_compact_citations_title_case_short_names() -> None:
    packet = {
        "source_trail": [{"source_id": "li_2020_egg_cholesterol_rct_meta", "source_label": "Long Source"}],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nThe trial evidence changed LDL-c [li_2020_egg_cholesterol_rct_meta]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[Li 2020]" in result["memo"]
    assert "[LI 2020]" not in result["memo"]
