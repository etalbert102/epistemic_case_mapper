from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_presentation import run_memo_ready_presentation_normalization


def test_presentation_removes_model_authored_sources_before_deterministic_sources() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "active_2025", "source_label": "Active Study 2025", "source_url": "https://example.test/active"}
        ],
        "evidence_items": [],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\n"
        "**Bottom Line:** Option A is supported [active_2025].; This should read cleanly.\n\n"
        "***\n\n"
        "**Sources**\n"
        "* **Active 2025** - model-authored duplicate source text.\n"
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert result["memo"].count("## Sources") == 1
    assert "**Sources**" not in result["memo"]
    assert "model-authored duplicate" not in result["memo"]
    assert ".; This" not in result["memo"]
    assert ". This should read cleanly." in result["memo"]
    assert "* [Active 2025](https://example.test/active)" in result["memo"]
    assert "Active Study 2025" in result["memo"].split("## Sources", maxsplit=1)[-1]
