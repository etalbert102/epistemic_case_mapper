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
