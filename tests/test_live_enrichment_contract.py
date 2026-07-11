from __future__ import annotations

import pytest

from epistemic_case_mapper.map_briefing_context_curation import _source_appraisal_timeout
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_retention_report,
    run_memo_ready_packet_synthesis,
)


def test_live_synthesis_backend_failure_is_visible_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "answer_spine": {"default_read": "Option A is plausible but bounded."},
        "evidence_items": [],
        "source_trail": [],
    }

    def fail_backend(*args, **kwargs):
        raise RuntimeError("backend timed out")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fail_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="ollama:test", backend_timeout=30, backend_retries=0)

    assert "Option A is plausible but bounded." in result["memo"]
    assert result["report"]["live_enrichment_required"] is True
    assert result["report"]["accepted"] is False
    assert result["report"]["status"] == "backend_error_live_enrichment_failed"
    assert "live_model_enrichment_failed" in result["report"]["issues"]


def test_retention_requires_decision_quantities_but_not_artifact_dates() -> None:
    packet = {
        "decision_question": "Should adults treat eggs as harmful?",
        "evidence_items": [
            {
                "item_id": "i1",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "The review found no clear cardiovascular risk increase for one egg per day.",
                "source_label": "Review A",
                "quantities": [
                    {"value": "2020-2025", "interpretation": "search window"},
                    {"value": "one egg/day", "interpretation": "decision-relevant dose"},
                    {"value": "95% CI 0.93 to 1.03", "interpretation": "uncertainty interval"},
                ],
            }
        ],
        "source_trail": [{"source_label": "Review A"}],
    }

    memo = "Review A found no clear cardiovascular risk increase for one egg per day."
    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["missing_quantity_count"] == 1
    assert report["issues"][0]["missing_quantities"] == ["95% CI 0.93 to 1.03"]
    assert "2020-2025" not in report["issues"][0]["missing_quantities"]


def test_live_source_appraisal_timeout_is_bounded() -> None:
    assert _source_appraisal_timeout("prompt", 240) == 240
    assert _source_appraisal_timeout("ollama:gemma", None) == 90
    assert _source_appraisal_timeout("ollama:gemma", 240) == 90
    assert _source_appraisal_timeout("ollama:gemma", 5) == 20
