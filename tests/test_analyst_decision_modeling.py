from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_analyst_decision_modeling import (
    build_analyst_decision_context,
    build_analyst_decision_model_prompt,
    run_analyst_decision_model,
)
from epistemic_case_mapper.model_backends import ModelBackendResult


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "bundle:support",
                "claim_id": "support",
                "claim": "Option A reduced losses in the main outcome study.",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
                "quantity_values": ["25% reduction"],
                "relation_context": [
                    {
                        "relation_type": "in_tension_with",
                        "other_claim_id": "risk",
                        "other_claim": "Option A shifts risk to operations.",
                    }
                ],
            },
            {
                "evidence_item_id": "bundle:support_duplicate",
                "claim_id": "support_duplicate",
                "claim": "The main outcome study found that option A reduced losses.",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
            },
            {
                "evidence_item_id": "bundle:risk",
                "claim_id": "risk",
                "claim": "Option A shifts risk to the operating budget.",
                "source_ids": ["s2"],
                "source_labels": ["Risk Review"],
            },
        ],
    }


def _adjudication() -> dict:
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "bundle:support",
                "memo_use": "load_bearing_primary_support",
                "importance_rank": 1,
                "rationale": "Main support.",
            },
            {
                "evidence_item_id": "bundle:support_duplicate",
                "memo_use": "covered_by_group",
                "importance_rank": 2,
                "rationale": "Covered by the main support.",
                "covered_by": ["bundle:support"],
            },
            {
                "evidence_item_id": "bundle:risk",
                "memo_use": "load_bearing_counterweight",
                "importance_rank": 3,
                "rationale": "Main limitation.",
            },
        ],
    }


def test_decision_context_includes_ml_hints_and_adjudication_labels() -> None:
    context = build_analyst_decision_context(ledger=_ledger(), adjudication=_adjudication())

    assert context["schema_id"] == "analyst_decision_context_v1"
    assert context["row_count"] == 3
    assert context["model_hints"]["top_central_evidence_item_ids"]
    assert context["evidence_rows"][0]["adjudicated_memo_use"] == "load_bearing_primary_support"


def test_decision_model_prompt_asks_for_global_groups() -> None:
    prompt = build_analyst_decision_model_prompt(build_analyst_decision_context(ledger=_ledger(), adjudication=_adjudication()))

    assert "global evidence organization" in prompt
    assert "evidence_groups" in prompt
    assert "evidence_dispositions" in prompt
    assert "model_hints" in prompt


def test_run_analyst_decision_model_accepts_valid_backend(monkeypatch) -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only if operating risk is bounded.",
        "confidence": "medium",
        "overall_rationale": "The outcome signal supports adoption but risk bounds it.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Outcome evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["bundle:support", "bundle:support_duplicate"],
                "rationale": "Both rows represent the same support proposition.",
                "evidence_strength": "moderate",
                "answer_impact": "Supports adoption.",
                "uncertainty_type": "implementation",
            },
            {
                "group_id": "risk_group",
                "proposition": "Operating-budget risk bounds the recommendation.",
                "memo_role": "load_bearing_counterweight",
                "importance_rank": 2,
                "covered_evidence_item_ids": ["bundle:risk"],
                "rationale": "Risk could erase benefits.",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "bundle:support", "disposition": "foreground", "group_id": "support_group"},
            {"evidence_item_id": "bundle:support_duplicate", "disposition": "covered_by_group", "group_id": "support_group"},
            {"evidence_item_id": "bundle:risk", "disposition": "foreground", "group_id": "risk_group"},
        ],
        "quantitative_anchors": ["25% reduction"],
        "what_would_change_the_answer": ["If operating risk cannot be bounded."],
        "argument_plan": [{"step_id": "support_then_risk", "writing_goal": "Weigh support against risk."}],
        "decision_logic": {"bounded_bottom_line": "Adopt option A only if operating risk is bounded."},
    }

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_modeling.run_model_backend", fake_backend)

    result = run_analyst_decision_model(
        ledger=_ledger(),
        adjudication=_adjudication(),
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["analyst_decision_model_report"]["status"] == "accepted"
    assert result["analyst_decision_model_parse_report"]["valid"] is True
    assert result["analyst_decision_model"]["evidence_groups"][0]["covered_evidence_item_ids"] == [
        "bundle:support",
        "bundle:support_duplicate",
    ]


def test_run_analyst_decision_model_invalid_backend_falls_back(monkeypatch) -> None:
    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text='{"schema_id": "analyst_decision_model_v1", "evidence_groups": []}', backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_modeling.run_model_backend", fake_backend)

    result = run_analyst_decision_model(
        ledger=_ledger(),
        adjudication=_adjudication(),
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["analyst_decision_model_report"]["status"] == "model_output_invalid_scaffold"
    assert result["analyst_decision_model"]["schema_id"] == "analyst_decision_model_v1"
    assert result["analyst_decision_model"]["evidence_groups"]
