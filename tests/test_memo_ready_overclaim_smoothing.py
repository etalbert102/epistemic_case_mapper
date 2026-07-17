from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    run_memo_ready_presentation_normalization,
)


def test_presentation_softens_generic_overclaim_language() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [{"source_id": "outcome_2025", "source_label": "Outcome Study 2025"}],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\n"
        "**Bottom Line:** Adopt option A conditionally.\n\n"
        "Moderate use does not increase cardiovascular risk [outcome_2025]. "
        "The evidence defines the \"safe\" threshold for action [outcome_2025]. "
        "Other evidence establishes the boundaries of \"safe\" limits and a dose-dependent boundary for safety."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "does not increase cardiovascular risk" not in result["memo"]
    assert "is not associated with increased cardiovascular risk" in result["memo"]
    assert 'safe" threshold' not in result["memo"]
    assert 'boundaries of "safe" limits' not in result["memo"]
    assert "dose-dependent boundary for safety" not in result["memo"]
    assert "working boundary" in result["memo"]
    assert "working intake boundaries" in result["memo"]
    assert "dose-dependent boundary for risk" in result["memo"]
    assert "[Outcome 2025]" in result["memo"]
    assert "smoothed_stock_phrasing" in result["report"]["changes"]


def test_presentation_smooths_stiff_source_weighting_language() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "driver_2025", "source_label": "Driver Study 2025"},
            {"source_id": "limit_2024", "source_label": "Limit Review 2024"},
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\n"
        "The evidence hierarchy is anchored by cohort studies, which establish a neutral stance [driver_2025]. "
        "The primary recommendation is driven by evidence suggesting that option A is acceptable [driver_2025]. "
        "While these driver sources establish the baseline, other evidence calibrates the specific limits of this recommendation. "
        "These sources do not overturn the neutral stance for moderate intake but instead establish practical boundaries [limit_2024]. "
        "While a neutral conclusion applies to moderate intake, evidence suggests a dose-dependent boundary for safety. "
        "That read holds because the evidence suggests that while high-volume use may correlate with elevated lipid ratios, moderate intake does not. "
        "For healthy adults, the neutral read still depends on the fact that comparator context is stable. "
        "However, this recommendation is not universal and requires specific exceptions for high-risk populations."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "The evidence hierarchy is anchored by" not in result["memo"]
    assert "which establish a neutral stance" not in result["memo"]
    assert "The primary recommendation is driven by evidence suggesting that" not in result["memo"]
    assert "driver sources establish the baseline" not in result["memo"]
    assert "do not overturn the neutral conclusion" not in result["memo"]
    assert "While a neutral conclusion applies" not in result["memo"]
    assert "boundary is dose-dependent a dose-dependent boundary" not in result["memo"]
    assert "depends on the fact that" not in result["memo"]
    assert "Put most weight on" in result["memo"]
    assert "The core evidence says" in result["memo"]
    assert "The limits come from a second layer of evidence" in result["memo"]
    assert "do not change the answer for moderate intake; they set" in result["memo"]
    assert "For moderate intake, the read is neutral; risk becomes more relevant as intake rises" in result["memo"]
    assert "may correlate with elevated lipid ratios, but moderate intake" in result["memo"]
    assert "the important caveat is that comparator context is stable" in result["memo"]
    assert "This advice does not apply equally to everyone for" not in result["memo"]
    assert "This advice has important exceptions for high-risk populations" in result["memo"]
    assert "[Driver 2025]" in result["memo"]
    assert "Limit Review 2024" in result["memo"]
