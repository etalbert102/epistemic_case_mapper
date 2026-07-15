from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_analyst_decision_modeling import (
    DEFAULT_DECISION_MODEL_NUM_PREDICT,
    analyst_decision_model_num_predict,
    build_analyst_decision_context,
    build_analyst_decision_model_prompt,
    run_analyst_decision_model,
)
from epistemic_case_mapper.map_briefing_analyst_decision_model_parallel import (
    _decision_logic,
    build_decision_model_tasks,
)
from epistemic_case_mapper.map_briefing_analyst_decision_repair import build_analyst_decision_model_repair_prompt
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
                "current_role": "load_bearing_primary_support",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
                "quantity_values": ["25% reduction"],
                "source_excerpt": "Raw support excerpt should not be model-facing.",
                "relation_context": [
                    {
                        "relation_type": "in_tension_with",
                        "other_claim_id": "risk",
                        "other_claim": "Broad relation context should not be forwarded.",
                    }
                ],
                "source_appraisal": {
                    "decision_directness": "direct",
                    "document_types": ["trial"],
                    "large_internal_notes": "Bulky appraisal detail should not be model-facing.",
                },
                "source_use_warnings": ["quality_limit"],
            },
            {
                "evidence_item_id": "bundle:support_duplicate",
                "claim_id": "support_duplicate",
                "claim": "The main outcome study found that option A reduced losses.",
                "current_role": "covered_by_group",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
            },
            {
                "evidence_item_id": "bundle:risk",
                "claim_id": "risk",
                "claim": "Option A shifts risk to the operating budget.",
                "current_role": "load_bearing_counterweight",
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


def _large_ledger(count: int = 14) -> dict:
    rows = []
    for index in range(1, count + 1):
        role = "load_bearing_counterweight" if index % 5 == 0 else "load_bearing_primary_support"
        rows.append(
            {
                "evidence_item_id": f"bundle:{index:03d}",
                "claim_id": f"c{index:03d}",
                "claim": f"Evidence item {index} bears on option A.",
                "current_role": role,
                "source_ids": [f"s{index}"],
                "source_labels": [f"Source {index}"],
                "quantity_values": [f"{index}%"] if index % 3 == 0 else [],
            }
        )
    return {"schema_id": "analyst_evidence_ledger_v1", "decision_question": "Should option A be adopted?", "rows": rows}


def _large_adjudication(count: int = 14) -> dict:
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": f"bundle:{index:03d}",
                "memo_use": "load_bearing_counterweight" if index % 5 == 0 else "load_bearing_primary_support",
                "importance_rank": index,
                "rationale": f"Item {index} is relevant.",
            }
            for index in range(1, count + 1)
        ],
    }


def _relation_ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "relation:r001",
                "input_kind": "candidate_decision_edge",
                "current_role": "load_bearing_primary_support",
                "current_priority": 8,
                "current_weight": "medium",
                "directionality": "supports",
                "relation_semantic_role": "supports",
                "relation_contract": {
                    "edge_basis": "source_inferred",
                    "source_anchor_a": "mechanism changed",
                    "source_anchor_b": "outcome improved",
                    "why_decision_relevant": "The mechanism may explain the outcome.",
                    "failure_condition": "The edge fails if the mechanism is not causally connected to the outcome.",
                },
                "candidate_pair": {
                    "pair_id": "pair_001",
                    "score": 11.0,
                    "reason": "mechanism_to_outcome+cross_source",
                    "decision_edge_contract": "mechanism_to_outcome",
                    "pair_intent": {"intent": "mechanism_to_outcome", "allowed_relation_types": ["supports", "none"]},
                },
                "endpoint_claims": [
                    {"endpoint": "source", "claim_id": "c001", "decision_edge_role": "mechanism_or_biomarker"},
                    {"endpoint": "target", "claim_id": "c002", "decision_edge_role": "outcome_finding"},
                ],
                "claim": "supports: mechanism evidence may explain the outcome finding.",
                "source_excerpt": "mechanism changed | outcome improved",
                "why_it_matters": "The edge would make the outcome evidence more coherent if valid.",
                "failure_condition": "The edge fails if the mechanism is not causally connected to the outcome.",
            }
        ],
    }


def _relation_adjudication() -> dict:
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "relation:r001",
                "memo_use": "needs_human_or_model_review",
                "importance_rank": 1,
                "rationale": "The proposed support edge needs directionality review.",
            }
        ],
    }


def test_decision_context_includes_ml_hints_and_adjudication_labels() -> None:
    context = build_analyst_decision_context(ledger=_ledger(), adjudication=_adjudication())

    assert context["schema_id"] == "analyst_decision_context_v1"
    assert context["row_count"] == 3
    assert context["model_hints"]["top_central_evidence_item_ids"]
    assert context["evidence_rows"][0]["adjudicated_memo_use"] == "load_bearing_primary_support"
    assert "source_excerpt" not in context["evidence_rows"][0]
    assert "relation_context" not in context["evidence_rows"][0]
    assert context["evidence_rows"][0]["source_quality"]["decision_directness"] == "direct"
    assert context["evidence_rows"][0]["source_quality"]["warnings"] == ["quality_limit"]
    assert "Bulky appraisal" not in json.dumps(context)
    assert context["retention_obligations"]["quantitative_anchors"][0]["evidence_item_id"] == "bundle:support"
    assert context["retention_obligations"]["counterweights"][0]["evidence_item_id"] == "bundle:risk"
    skeleton_ids = {row["skeleton_group_id"] for row in context["obligation_group_skeleton"]}
    assert "must_account_quantitative_anchors" in skeleton_ids
    assert "must_account_counterweights" in skeleton_ids


def test_decision_context_and_prompt_expose_candidate_relation_metadata() -> None:
    context = build_analyst_decision_context(ledger=_relation_ledger(), adjudication=_relation_adjudication())
    row = context["evidence_rows"][0]
    prompt = build_analyst_decision_model_prompt(context)

    assert row["relation_semantic_role"] == "supports"
    assert row["relation_contract"]["source_anchor_a"] == "mechanism changed"
    assert row["candidate_pair"]["decision_edge_contract"] == "mechanism_to_outcome"
    assert row["endpoint_claims"][1]["decision_edge_role"] == "outcome_finding"
    assert "provisional analytic links" in prompt
    assert "failure_condition" in prompt
    assert "endpoint_claims" in prompt


def test_decision_model_prompt_asks_for_global_groups() -> None:
    prompt = build_analyst_decision_model_prompt(build_analyst_decision_context(ledger=_ledger(), adjudication=_adjudication()))

    assert "global evidence organization" in prompt
    assert "evidence_groups" in prompt
    assert "evidence_dispositions" in prompt
    assert "model_hints" in prompt
    assert "retention_obligations" in prompt
    assert "obligation_group_skeleton" in prompt
    assert "Start from obligation_group_skeleton" in prompt
    assert "Do not bury contrary evidence inside a support group" in prompt
    assert "Rank by decision diagnosticity" in prompt
    assert "source_ids" in prompt
    assert "source_labels" not in prompt
    assert "Outcome Study" not in prompt
    assert "Risk Review" not in prompt


def test_parallel_decision_model_tasks_chunk_large_context() -> None:
    context = build_analyst_decision_context(ledger=_large_ledger(14), adjudication=_large_adjudication(14))
    tasks = build_decision_model_tasks(context, max_rows_per_task=6)

    assert len(tasks) == 3
    assert [len(task["evidence_rows"]) for task in tasks] == [6, 6, 2]
    assert tasks[0]["task_id"] == "analyst_decision_model_task_001"
    assert "source_excerpt" not in json.dumps(tasks)
    assert "relation_context" not in json.dumps(tasks)
    assert "source_ids" in json.dumps(tasks)
    assert "source_labels" not in json.dumps(tasks)
    assert "Source 1" not in json.dumps(tasks)


def test_decision_model_repair_prompt_uses_source_ids_not_labels() -> None:
    repair_rows = [
        {
            "evidence_item_id": "bundle:support",
            "claim": "Option A reduced losses in the main outcome study.",
            "source_ids": ["s1"],
            "source_labels": ["Outcome Study"],
        }
    ]

    prompt = build_analyst_decision_model_repair_prompt(
        current_model={"direct_answer": "Adopt option A only if operating risk is bounded.", "evidence_groups": []},
        repair_rows=repair_rows,
        decision_question="Should option A be adopted?",
    )

    assert "source_ids" in prompt
    assert "s1" in prompt
    assert "source_labels" not in prompt
    assert "Outcome Study" not in prompt


def test_decision_model_uses_larger_stage_specific_output_budget(monkeypatch) -> None:
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
                "covered_evidence_item_ids": ["bundle:support"],
                "rationale": "The main study supports adoption.",
            }
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "bundle:support", "disposition": "foreground", "group_id": "support_group"},
            {"evidence_item_id": "bundle:support_duplicate", "disposition": "covered_by_group", "group_id": "support_group"},
            {"evidence_item_id": "bundle:risk", "disposition": "background", "group_id": ""},
        ],
    }
    seen = {}

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        seen["num_predict"] = kwargs.get("num_predict")
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_modeling.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_repair.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_repair.run_model_backend", fake_backend)

    run_analyst_decision_model(
        ledger=_ledger(),
        adjudication=_adjudication(),
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert seen["num_predict"] == DEFAULT_DECISION_MODEL_NUM_PREDICT


def test_decision_model_output_budget_has_env_override(monkeypatch) -> None:
    monkeypatch.setenv("ECM_ANALYST_DECISION_MODEL_NUM_PREDICT", "16000")

    assert analyst_decision_model_num_predict({}) == 16_000


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
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_repair.run_model_backend", fake_backend)

    result = run_analyst_decision_model(
        ledger=_ledger(),
        adjudication=_adjudication(),
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["analyst_decision_model_report"]["status"] == "accepted_with_warnings"
    assert "missing_practical_implications" in result["analyst_decision_model_report"]["issues"]
    assert result["analyst_decision_model_parse_report"]["valid"] is True
    assert result["analyst_decision_model"]["evidence_groups"][0]["covered_evidence_item_ids"] == [
        "bundle:support",
        "bundle:support_duplicate",
    ]
    assert result["analyst_decision_model_repair_report"]["status"] == "not_needed"


def test_decision_model_ranking_guard_promotes_quantified_decision_anchor(monkeypatch) -> None:
    ledger = {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should the intervention be treated as harmful, neutral, or beneficial?",
        "rows": [
            {
                "evidence_item_id": "claim:context",
                "claim": "The intervention is included in general background guidance for in-scope users.",
                "source_labels": ["Guidance"],
            },
            {
                "evidence_item_id": "claim:outcome",
                "claim": "Moderate exposure was not associated with the main adverse outcome.",
                "source_labels": ["Outcome Study"],
                "quantity_values": ["hazard ratio 0.93", "95% confidence interval 0.82 to 1.05"],
            },
        ],
    }
    adjudication = {
        "rows": [
            {
                "evidence_item_id": "claim:context",
                "memo_use": "load_bearing_primary_support",
                "importance_rank": 10,
                "rationale": "Relevant context.",
            },
            {
                "evidence_item_id": "claim:outcome",
                "memo_use": "load_bearing_primary_support",
                "importance_rank": 1,
                "rationale": "This is the quantified outcome anchor.",
            },
        ],
    }
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": ledger["decision_question"],
        "direct_answer": "The intervention is included in general guidance.",
        "confidence": "medium",
        "overall_rationale": "The model overvalued contextual guidance.",
        "evidence_groups": [
            {
                "group_id": "context_group",
                "proposition": "The intervention is included in general background guidance.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["claim:context"],
                "rationale": "In-scope guidance.",
            },
            {
                "group_id": "outcome_group",
                "proposition": "Moderate exposure was not associated with the main adverse outcome.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 2,
                "covered_evidence_item_ids": ["claim:outcome"],
                "rationale": "Quantified outcome evidence.",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "claim:context", "disposition": "foreground", "group_id": "context_group"},
            {"evidence_item_id": "claim:outcome", "disposition": "foreground", "group_id": "outcome_group"},
        ],
        "decision_logic": {"bounded_bottom_line": "Treat the intervention as neutral with caveats."},
    }

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_modeling.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_repair.run_model_backend", fake_backend)

    result = run_analyst_decision_model(
        ledger=ledger,
        adjudication=adjudication,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    groups = result["analyst_decision_model"]["evidence_groups"]
    assert groups[0]["group_id"] == "outcome_group"
    assert groups[0]["importance_rank"] == 1
    assert groups[0]["diagnostic_priority_score"] > groups[1]["diagnostic_priority_score"]
    assert result["analyst_decision_model_ranking_guard"]["changed_group_count"] >= 1


def test_run_analyst_decision_model_parallelizes_large_context(monkeypatch) -> None:
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        payload = json.loads(prompt)
        rows = payload["context"]["evidence_rows"]
        groups = [
            {
                "group_id": f"group_{len(calls):03d}",
                "proposition": f"Grouped {len(rows)} local evidence rows.",
                "memo_role": rows[0].get("adjudicated_memo_use") or "load_bearing_primary_support",
                "importance_rank": len(calls),
                "covered_evidence_item_ids": [row["evidence_item_id"] for row in rows],
                "rationale": "Local grouped rationale.",
            }
        ]
        model = {
            "schema_id": "analyst_decision_model_v1",
            "decision_question": "Should option A be adopted?",
            "direct_answer": "Adopt if the grouped evidence warrants it.",
            "confidence": "medium",
            "overall_rationale": "Local grouped model.",
            "evidence_groups": groups,
            "evidence_dispositions": [
                {"evidence_item_id": row["evidence_item_id"], "disposition": "foreground", "group_id": groups[0]["group_id"]}
                for row in rows
            ],
            "quantitative_anchors": [quantity for row in rows for quantity in row.get("quantity_values", [])],
            "what_would_change_the_answer": [],
            "decision_logic": {"bounded_bottom_line": "Adopt if warranted."},
            "argument_plan": [],
        }
        return ModelBackendResult(text=json.dumps(model), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_modeling.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_repair.run_model_backend", fake_backend)

    result = run_analyst_decision_model(
        ledger=_large_ledger(14),
        adjudication=_large_adjudication(14),
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert len(calls) == 4
    assert result["analyst_decision_model_report"]["status"].startswith("accepted_parallel")
    assert result["analyst_decision_model_parallel_report"]["task_count"] == 4
    assert result["analyst_decision_model_parse_report"]["valid"] is True
    assert result["analyst_decision_model_parse_report"]["covered_evidence_item_count"] == 14


def test_parallel_decision_logic_preserves_model_counterweight_judgment() -> None:
    groups = [
        {
            "proposition": "Outcome evidence supports option A.",
            "memo_role": "load_bearing_primary_support",
        },
        {
            "proposition": "Implementation risk narrows when option A is attractive.",
            "memo_role": "load_bearing_counterweight",
        },
    ]
    payloads = [
        {
            "decision_logic": {
                "bounded_bottom_line": "Adopt option A only where implementation risk is manageable.",
                "support_summary": "Outcome evidence supports option A.",
                "strongest_counterweight": "Implementation risk narrows where adoption makes sense.",
                "counterweight_weighting": "The risk narrows scope but does not erase the outcome signal.",
                "practical_implications": ["Pilot where implementation controls are available."],
            }
        }
    ]

    result = _decision_logic({"decision_question": "Should option A be adopted?"}, groups, payloads)

    assert result["counterweight_weighting"] == "The risk narrows scope but does not erase the outcome signal."
    assert result["practical_implications"] == ["Pilot where implementation controls are available."]


def test_parallel_decision_logic_does_not_invent_missing_counterweight_weighting() -> None:
    groups = [
        {
            "proposition": "Outcome evidence supports option A.",
            "memo_role": "load_bearing_primary_support",
        },
        {
            "proposition": "Implementation risk narrows adoption.",
            "memo_role": "load_bearing_counterweight",
        },
    ]

    result = _decision_logic({"decision_question": "Should option A be adopted?"}, groups, [])

    assert result["counterweight_weighting"] == ""
    assert result["bounded_bottom_line"] == ""
    assert result["support_summary"] == "Outcome evidence supports option A."
    assert result["strongest_counterweight"] == "Implementation risk narrows adoption."


def test_run_analyst_decision_model_parallel_partial_failure_uses_valid_tasks(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("timeout")
        if "Assign each repair_row" in prompt:
            return ModelBackendResult(text=json.dumps({"assignments": []}), backend="fake")
        payload = json.loads(prompt)
        rows = payload["context"]["evidence_rows"]
        model = {
            "schema_id": "analyst_decision_model_v1",
            "decision_question": "Should option A be adopted?",
            "direct_answer": "Partial model.",
            "confidence": "medium",
            "overall_rationale": "Partial grouped model.",
            "evidence_groups": [
                {
                    "group_id": f"group_{calls['count']:03d}",
                    "proposition": "Recovered local group.",
                    "memo_role": "load_bearing_primary_support",
                    "importance_rank": calls["count"],
                    "covered_evidence_item_ids": [row["evidence_item_id"] for row in rows],
                    "rationale": "Recovered rows.",
                }
            ],
            "evidence_dispositions": [],
        }
        return ModelBackendResult(text=json.dumps(model), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_modeling.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_repair.run_model_backend", fake_backend)

    result = run_analyst_decision_model(
        ledger=_large_ledger(14),
        adjudication=_large_adjudication(14),
        backend="fake",
        backend_timeout=1,
        backend_retries=0,
    )

    assert result["analyst_decision_model_parallel_report"]["failed_count"] == 1
    assert result["analyst_decision_model_report"]["status"].startswith("accepted_parallel")
    assert result["analyst_decision_model_parse_report"]["valid"] is True


def test_run_analyst_decision_model_repairs_omitted_obligations(monkeypatch) -> None:
    initial_payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A if risks are acceptable.",
        "confidence": "medium",
        "overall_rationale": "The outcome signal supports adoption.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Outcome evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["bundle:support", "bundle:support_duplicate"],
                "rationale": "The main study supports adoption.",
            }
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "bundle:risk", "disposition": "background", "rationale": "Not foregrounded."},
        ],
        "quantitative_anchors": ["25% reduction"],
        "what_would_change_the_answer": [],
        "decision_logic": {"bounded_bottom_line": "Adopt if risk is acceptable."},
        "argument_plan": [],
    }
    assignment_payload = {
        "assignments": [
            {
                "evidence_item_id": "bundle:risk",
                "action": "create_group",
                "new_group": {
                    "group_id": "risk_group",
                    "proposition": "Operating-budget risk bounds adoption.",
                    "memo_role": "load_bearing_counterweight",
                    "importance_rank": 2,
                    "rationale": "The risk row is the main counterweight.",
                    "answer_impact": "Bounds adoption.",
                },
                "rationale": "Risk is a counterweight and should be foregrounded.",
            },
        ],
    }
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        if "Assign each repair_row" in prompt:
            return ModelBackendResult(text=json.dumps(assignment_payload), backend="fake")
        return ModelBackendResult(text=json.dumps(initial_payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_modeling.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_decision_repair.run_model_backend", fake_backend)

    result = run_analyst_decision_model(
        ledger=_ledger(),
        adjudication=_adjudication(),
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert len(calls) == 2
    assert result["analyst_decision_model_report"]["status"] == "accepted_after_repair_with_warnings"
    assert "missing_practical_implications" in result["analyst_decision_model_report"]["issues"]
    assert result["analyst_decision_model_repair_report"]["accepted"] is True
    assert result["analyst_decision_model"]["evidence_groups"][-1]["covered_evidence_item_ids"] == ["bundle:risk"]
    assert result["analyst_decision_model_repair_report"]["batch_count"] == 1
    assert result["analyst_decision_model_initial_parse_report"]["obligation_omissions"]["ungrouped_counterweight_ids"] == ["bundle:risk"]


def test_run_analyst_decision_model_invalid_backend_stays_invalid(monkeypatch) -> None:
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

    assert result["analyst_decision_model_report"]["status"] == "model_output_invalid"
    assert result["analyst_decision_model_report"]["accepted"] is False
    assert result["analyst_decision_model"]["schema_id"] == "analyst_decision_model_v1"
    assert result["analyst_decision_model"]["evidence_groups"] == []
