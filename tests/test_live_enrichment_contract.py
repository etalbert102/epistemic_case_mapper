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


def test_live_synthesis_requests_plain_text_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    packet = {
        "decision_question": "Should the city adopt option A?",
        "answer_spine": {"default_read": "Option A is plausible but bounded."},
        "evidence_items": [
            {
                "item_id": "i1",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "Option A reduces losses.",
                "source_label": "Outcome Review",
            }
        ],
        "source_trail": [{"source_label": "Outcome Review"}],
    }

    def fake_backend(*args, **kwargs):
        captured.update(kwargs)
        from epistemic_case_mapper.model_backends import ModelBackendResult

        return ModelBackendResult(
            text="# Decision Memo\n\nOutcome Review says Option A reduces losses.",
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    run_memo_ready_packet_synthesis(packet, backend="ollama:test", backend_timeout=30, backend_retries=0)

    assert captured["json_mode"] is False


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


def test_retention_accepts_semantic_dose_phrasing_and_retention_phrase() -> None:
    packet = {
        "decision_question": "Should adults treat eggs as harmful?",
        "evidence_items": [
            {
                "item_id": "i1",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "Moderate egg consumption was not associated with increased cardiovascular risk.",
                "source_label": "Review A",
                "quantities": [
                    {"value": "up to one egg/day", "interpretation": "decision-relevant dose"},
                    {"value": "more than one egg/day", "interpretation": "high-intake boundary"},
                    {
                        "value": "one serving per day",
                        "retention_phrase": "one whole egg per day",
                        "interpretation": "replacement-model unit",
                    },
                ],
            }
        ],
        "source_trail": [{"source_label": "Review A"}],
    }

    memo = "Review A treats moderate intake as up to one whole egg per day and notes that risk may change at >1/day."
    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["missing_quantity_count"] == 0
    assert report["issues"] == []


def test_retention_accepts_stable_source_id_as_source_alias() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "evidence_items": [
            {
                "item_id": "counter",
                "must_use": True,
                "role": "strongest_counterweight",
                "reader_claim": "Option A increased serious implementation failures.",
                "source_label": "Deep Research Flood Sources Risk Study 2025",
            }
        ],
        "source_trail": [
            {
                "source_id": "deep_research_flood_sources_risk_study_2025",
                "source_label": "Deep Research Flood Sources Risk Study 2025",
            }
        ],
    }
    memo = "Option A increased serious implementation failures [deep_research_flood_sources_risk_study_2025]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["status"] == "ready"


def test_live_source_appraisal_timeout_is_bounded() -> None:
    assert _source_appraisal_timeout("prompt", 240) == 240
    assert _source_appraisal_timeout("ollama:gemma", None) == 90
    assert _source_appraisal_timeout("ollama:gemma", 240) == 90
    assert _source_appraisal_timeout("ollama:gemma", 5) == 20
