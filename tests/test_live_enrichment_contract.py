from __future__ import annotations

import pytest

from epistemic_case_mapper.map_briefing_context_curation import _source_appraisal_timeout
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    _prepare_source_weighted_outline_contract_path,
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

    assert result["memo"] == ""
    assert result["report"]["live_enrichment_required"] is True
    assert result["report"]["accepted"] is False
    assert result["report"]["status"] == "backend_error_live_enrichment_failed"
    assert "live_model_enrichment_failed" in result["report"]["issues"]


def test_live_synthesis_unparseable_output_is_visible_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "answer_spine": {"default_read": "Option A is plausible but bounded."},
        "evidence_items": [],
        "source_trail": [],
    }

    def fake_backend(*args, **kwargs):
        from epistemic_case_mapper.model_backends import ModelBackendResult

        return ModelBackendResult(text='{"unexpected": "shape"}', backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="ollama:test", backend_timeout=30, backend_retries=0)

    assert result["memo"] == ""
    assert result["raw"] == '{"unexpected": "shape"}'
    assert result["report"]["accepted"] is False
    assert result["report"]["status"] == "empty_or_unparseable_live_enrichment_failed"


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


def test_live_synthesis_blocks_scaffolded_canonical_packet_before_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False
    packet = {
        "schema_id": "memo_ready_packet_v1",
        "decision_question": "Should option A be adopted?",
        "answer_spine": {
            "default_read": "Scaffold only; live global analyst decision modeling was not accepted.",
            "why_this_read": "Scaffold only.",
        },
        "analyst_source_hierarchy": {
            "schema_id": "source_weight_hierarchy_v1",
            "hierarchy_thesis": "",
            "lanes": {
                "primary_answer_drivers": [],
                "quantitative_calibrators": [],
                "counterweight_sources": [],
                "scope_boundary_sources": [],
                "contextual_sources": [],
            },
            "source_accounting": [],
        },
        "analyst_source_hierarchy_report": {
            "schema_id": "source_weight_hierarchy_report_v1",
            "status": "empty",
            "primary_driver_source_count": 0,
        },
        "analyst_source_weight_judgments": [],
        "canonical_decision_writer_packet": {
            "schema_id": "canonical_decision_writer_packet_v1",
            "source_weighted_answer_frame": {
                "lanes": {
                    "primary_answer_drivers": [
                        {
                            "item_id": "i1",
                            "source_weight_basis": "writer_role_projection",
                        }
                    ]
                }
            },
        },
        "canonical_decision_writer_packet_quality_report": {
            "schema_id": "canonical_decision_writer_packet_quality_report_v1",
            "status": "warning",
            "warnings": ["truncated_or_scaffolded_direct_answer", "source_hierarchy_warning"],
        },
        "evidence_items": [],
        "source_trail": [],
    }

    def fake_backend(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("backend should not be called for a blocked production packet")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="ollama:test", backend_timeout=30, backend_retries=0)

    assert called is False
    assert result["memo"] == ""
    assert result["report"]["status"] == "production_readiness_blocked"
    assert result["report"]["accepted"] is False
    readiness = result["report"]["production_readiness_report"]
    assert readiness["status"] == "blocked"
    assert "missing_or_empty_analyst_source_hierarchy" in readiness["fatal_issues"]
    assert "missing_analyst_source_weight_judgments" in readiness["fatal_issues"]
    assert "writer_role_projection_source_weight_fallback_used" in readiness["fatal_issues"]


def test_prompt_synthesis_reports_blocked_production_readiness_but_stays_inspectable() -> None:
    packet = {
        "schema_id": "memo_ready_packet_v1",
        "decision_question": "Should option A be adopted?",
        "answer_spine": {"default_read": "Scaffold only; live global analyst decision modeling was not accepted."},
        "analyst_source_hierarchy": {"schema_id": "source_weight_hierarchy_v1", "lanes": {}, "source_accounting": []},
        "analyst_source_hierarchy_report": {"status": "empty", "primary_driver_source_count": 0},
        "analyst_source_weight_judgments": [],
        "canonical_decision_writer_packet": {"schema_id": "canonical_decision_writer_packet_v1"},
        "evidence_items": [],
        "source_trail": [],
    }

    result = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)

    assert result["memo"]
    assert result["report"]["accepted"] is True
    assert result["report"]["production_readiness_report"]["status"] == "blocked"


def test_source_weighted_outline_contract_path_rebuilds_active_packet_from_outline(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "evidence_items": [
            {
                "item_id": "support",
                "must_use": True,
                "obligation_level": "must_include",
                "role": "strongest_support",
                "claim": "Option A reduced flood losses by 20%.",
                "source_ids": ["study_a"],
                "quantities": [{"value": "20%", "interpretation": "loss reduction"}],
            },
            {
                "item_id": "residue",
                "must_use": True,
                "obligation_level": "must_include",
                "role": "strongest_support",
                "claim": "Appendix-only extraction with low atomicity or low decision relevance; use only as source context.",
                "source_ids": ["study_b"],
                "quantities": [{"value": "999 mg", "interpretation": "residue"}],
            },
        ],
        "source_trail": [
            {"source_id": "study_a", "source_label": "Study A"},
            {"source_id": "study_b", "source_label": "Study B"},
        ],
        "canonical_decision_writer_packet": {
            "schema_id": "canonical_decision_writer_packet_v1",
            "decision_question": "Should the city adopt option A?",
            "decision_brief_skeleton": {
                "primary_answer": "Adopt option A where implementation capacity is adequate.",
                "confidence": "medium",
            },
            "bluf_contract": {
                "recommended_read": "Adopt option A where implementation capacity is adequate.",
                "secondary_detail": "The strongest evidence is direct loss reduction.",
            },
            "source_weight_judgments": [
                {
                    "source_ids": ["study_a"],
                    "weight_role": "driver",
                    "rationale": "Study A directly measures the decision outcome.",
                }
            ],
            "priority_evidence": [
                {
                    "item_id": "support",
                    "claim": "Option A reduced flood losses by 20%.",
                    "source_ids": ["study_a"],
                    "quantities": [{"value": "20%", "interpretation": "loss reduction"}],
                    "why_it_matters": "This sizes the main benefit.",
                }
            ],
            "mandatory_retention_checklist": [
                {
                    "obligation_id": "support_obligation",
                    "evidence_item_ids": ["support"],
                    "statement": "Retain the main loss-reduction claim.",
                },
                {
                    "obligation_id": "residue_obligation",
                    "evidence_item_ids": ["residue"],
                    "statement": "Retain residue.",
                },
            ],
            "evidence_weighted_argument_spine": {
                "section_plan": [
                    {
                        "section_id": "answer_evidence",
                        "heading": "Why This Is the Best Current Read",
                        "primary_section": True,
                    }
                ],
                "steps": [
                    {
                        "step_id": "step_1",
                        "section_id": "answer_evidence",
                        "claim": "Option A reduced flood losses by 20%.",
                        "evidence_item_ids": ["support"],
                        "source_ids": ["study_a"],
                    }
                ],
            },
        },
    }

    def fake_backend(*args, **kwargs):
        from epistemic_case_mapper.model_backends import ModelBackendResult

        return ModelBackendResult(
            text=(
                '{"schema_id":"source_weighted_narrative_outline_v1",'
                '"answer_order":["Adopt option A where implementation capacity is adequate."],'
                '"source_weighting_thesis":"Study A carries the answer because it measures the decision outcome.",'
                '"narrative_arc":[{"paragraph_role":"answer","main_point":"Study A carries the answer.",'
                '"source_ids":["study_a"],"evidence_ids":["support"]}],'
                '"section_guidance":[{"section_id":"answer_evidence","main_job":"Explain the loss reduction.",'
                '"owned_evidence_ids":["support"]}]}'
            ),
            backend="fake",
        )

    monkeypatch.setenv("ECM_SOURCE_WEIGHTED_OUTLINE_CONTRACTS", "1")
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = _prepare_source_weighted_outline_contract_path(
        packet,
        backend="ollama:test",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["accepted"] is True
    active_items = {row["item_id"]: row for row in result["memo_ready_packet"]["evidence_items"]}
    assert active_items["support"]["must_use"] is True
    assert "residue" not in active_items
    assert result["report"]["integration_report"]["demoted_required_count"] == 1
    assert result["section_plan"]["source_weighted_narrative_outline"]["source_weighting_thesis"].startswith("Study A")


def test_whole_memo_synthesis_uses_larger_output_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    packet = {
        "decision_question": "Should the city adopt option A?",
        "answer_spine": {"default_read": "Option A is plausible but bounded."},
        "evidence_items": [],
        "source_trail": [],
    }

    def fake_backend(*args, **kwargs):
        captured.update(kwargs)
        from epistemic_case_mapper.model_backends import ModelBackendResult

        return ModelBackendResult(text="# Decision Memo\n\nOption A is plausible but bounded.", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="ollama:test", backend_timeout=30, backend_retries=0)

    assert result["report"]["used_default_path"] is False
    assert captured["json_mode"] is False
    assert captured["num_predict"] == 8192


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
