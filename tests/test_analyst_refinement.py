from __future__ import annotations

import json

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_refinement import (
    build_analyst_packet_refinement_parse_report,
    build_analyst_packet_refinement_prompt,
    run_analyst_packet_refinement,
)
from epistemic_case_mapper.model_backends import ModelBackendResult


def _synthesis_packet() -> dict:
    return {
        "schema_id": "analyst_synthesis_packet_v1",
        "decision_question": "Should option A be adopted?",
        "bottom_line": "Synthesize the answer from the adjudicated evidence hierarchy.",
        "primary_reasoning_chain": [
            {
                "group_id": "g1",
                "proposition": "Option A reduced losses.",
                "memo_role": "load_bearing_primary_support",
                "source_labels": ["Outcome Study"],
                "quantity_values": ["25% reduction"],
                "rationale": "Main support.",
            }
        ],
        "main_counterweights": [
            {
                "group_id": "g2",
                "proposition": "Option A shifts operating risk.",
                "memo_role": "load_bearing_counterweight",
                "source_labels": ["Risk Review"],
                "rationale": "Main counterweight.",
            }
        ],
    }


def _warning_packet() -> dict:
    return {
        "schema_id": "memo_warning_packet_v1",
        "warnings": [
            {
                "warning_id": "memo_warning_001",
                "severity": "critical",
                "warning_type": "omitted_decision_critical_evidence",
                "source_labels": ["Risk Review"],
                "claim": "Raw excerpt: operating costs were unexpectedly high in subgroup tables.",
            }
        ],
    }


def test_refinement_prompt_contains_warning_ids_and_answer_task() -> None:
    prompt = build_analyst_packet_refinement_prompt(
        synthesis_packet=_synthesis_packet(),
        warning_packet=_warning_packet(),
    )

    assert "Produce a direct answer frame" in prompt
    assert "decision_logic" in prompt
    assert "counterweight_weighting" in prompt
    assert "natural analyst guidance" in prompt
    assert "calibrated language" in prompt
    assert "memo_warning_001" in prompt
    assert "strict JSON" in prompt


def test_refinement_accepts_valid_live_backend(monkeypatch) -> None:
    payload = {
        "schema_id": "analyst_packet_refinement_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only if operating risk is bounded.",
        "answer_rationale": "Outcome gains are real, but operating risk limits adoption.",
        "decision_logic": {
            "bounded_bottom_line": "Adopt option A only when operating risk is bounded.",
            "support_summary": "Outcome gains support adoption.",
            "strongest_counterweight": "Operating risk can erase the benefit.",
            "counterweight_weighting": "The counterweight bounds implementation rather than overturning the effect.",
            "reconciled_cruxes": ["The decision changes if operating risk cannot be bounded."],
            "scope_boundaries": ["Applies where maintenance capacity is reliable."],
            "practical_implications": ["Adopt with an operating-risk condition."],
            "do_not_overstate": ["Do not claim unconditional adoption."],
        },
        "warning_obligations": [
            {
                "warning_id": "memo_warning_001",
                "memo_action": "bound_scope_or_confidence",
                "obligation": "Mention that operating-cost risk bounds confidence in adoption.",
                "rationale": "The warning affects implementation risk rather than the core effect.",
                "source_labels": ["Risk Review"],
                "key_terms": ["operating-cost", "confidence"],
            }
        ],
        "argument_plan": [
            {
                "step_id": "counterweight",
                "section": "Why This Is the Best Current Read",
                "writing_goal": "Acknowledge the operating-risk counterweight before stating the final recommendation.",
                "required_points": ["Operating risk bounds adoption."],
                "evidence_item_ids": ["memo_warning_001"],
                "source_labels": ["Risk Review"],
                "transition_from_previous": "Contrast support with implementation risk.",
            }
        ],
    }

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_refinement.run_model_backend", fake_backend)

    result = run_analyst_packet_refinement(
        synthesis_packet=_synthesis_packet(),
        warning_packet=_warning_packet(),
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["analyst_packet_refinement_report"]["status"] == "accepted"
    assert result["analyst_packet_refinement"]["direct_answer"].startswith("Adopt option A")
    assert result["analyst_packet_refinement"]["decision_logic"]["counterweight_weighting"].startswith("The counterweight")
    assert result["analyst_packet_refinement"]["argument_plan"][0]["step_id"] == "counterweight"


def test_refinement_parse_report_flags_missing_warning_ids() -> None:
    payload = {
        "schema_id": "analyst_packet_refinement_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only if operating risk is bounded.",
        "answer_rationale": "Outcome gains are real, but operating risk limits adoption.",
        "warning_obligations": [],
    }

    report = build_analyst_packet_refinement_parse_report(payload, _warning_packet())

    assert report["status"] == "warning"
    assert report["missing_warning_ids"] == ["memo_warning_001"]
