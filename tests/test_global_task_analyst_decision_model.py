from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_model_global_tasks import (
    build_analyst_decision_model_from_global_tasks,
    build_global_analyst_task_prompt,
    build_global_analyst_tasks,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_model_global_task_runner import run_global_analyst_task_calls
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_schemas import build_analyst_decision_model_parse_report
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_global_analyst_tasks_use_task_specific_contexts() -> None:
    tasks = build_global_analyst_tasks(_context())
    by_id = {task["task_id"]: task for task in tasks}

    assert set(by_id) == {
        "answer_frame",
        "evidence_reconciliation",
        "quantity_plan",
        "source_hierarchy",
        "argument_blueprint",
    }
    assert "quantity_bearing_evidence_rows" in by_id["quantity_plan"]["context"]
    assert "evidence_rows" not in by_id["quantity_plan"]["context"]
    assert "source_inventory" in by_id["source_hierarchy"]["context"]
    assert "all_evidence_roster" in by_id["evidence_reconciliation"]["context"]
    assert "detail_cards" in by_id["evidence_reconciliation"]["context"]
    assert "decision_diagnostic_evidence_rows" in by_id["answer_frame"]["context"]
    assert len(build_global_analyst_task_prompt(by_id["quantity_plan"])) <= len(build_global_analyst_task_prompt(by_id["evidence_reconciliation"]))
    assert "source_labels" not in "\n".join(build_global_analyst_task_prompt(task) for task in tasks)


def test_global_task_runner_rejects_wrong_task_schema(monkeypatch) -> None:
    task = {task["task_id"]: task for task in build_global_analyst_tasks(_context())}["answer_frame"]

    def wrong_schema_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text='{"schema_id":"global_quantity_plan_v1","quantity_decisions":[]}', backend="fake")

    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "1")

    [result] = run_global_analyst_task_calls(
        [task],
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        num_predict=4096,
        run_backend=wrong_schema_backend,
    )

    assert result["status"] == "failed"
    assert result["retry_reports"][0]["status"] == "parse_failed"


def test_global_task_payload_assembles_valid_analyst_decision_model() -> None:
    context = _context()
    task_results = [
        {
            "task_id": "answer_frame",
            "status": "parsed",
            "payload": {
                "schema_id": "global_answer_frame_v1",
                "best_answer": "Adopt option A with the stated boundary.",
                "confidence": "medium",
                "confidence_basis": "Direct outcome evidence supports the answer while risk bounds it.",
                "main_answer_drivers": [
                    {
                        "source_ids": ["s1"],
                        "evidence_item_ids": ["item:support"],
                        "reason": "Outcome evidence supports option A.",
                    }
                ],
                "main_counterweights": [
                    {
                        "source_ids": ["s2"],
                        "evidence_item_ids": ["item:risk"],
                        "reason": "Budget risk bounds implementation.",
                    }
                ],
                "counterweight_weighting": "Budget risk narrows where option A is attractive but does not erase the outcome evidence.",
                "what_would_change_the_answer": ["A direct implementation study showing unmanageable budget risk."],
                "scope_boundaries": ["Applies when budget risk is monitored."],
                "practical_implication": "Adopt with monitoring.",
                "practical_implications": ["Track budget risk during rollout."],
                "do_not_overstate": ["Do not ignore budget risk."],
            },
        },
        {
            "task_id": "evidence_reconciliation",
            "status": "parsed",
            "payload": {
                "schema_id": "global_evidence_reconciliation_v1",
                "groups": [
                    {
                        "group_id": "support",
                        "proposition": "Outcome evidence supports option A.",
                        "role": "answer_driver",
                        "answer_relation": "supports_answer",
                        "priority_band": "high",
                        "evidence_item_ids": ["item:support"],
                        "qualifier": "",
                        "rationale": "Load-bearing support.",
                    },
                    {
                        "group_id": "risk",
                        "proposition": "Budget risk bounds implementation.",
                        "role": "counterweight",
                        "answer_relation": "challenges_answer",
                        "priority_band": "high",
                        "evidence_item_ids": ["item:risk"],
                        "qualifier": "",
                        "rationale": "Load-bearing counterweight.",
                    },
                ],
                "overrides": [],
                "unresolved_evidence_item_ids": [],
            },
        },
        {
            "task_id": "quantity_plan",
            "status": "parsed",
            "payload": {
                "schema_id": "global_quantity_plan_v1",
                "quantity_decisions": [
                    {
                        "evidence_item_id": "item:support",
                        "quantity_value": "20%",
                        "memo_inclusion": "must_use",
                        "quantity_role": "decision_anchor",
                        "retention_phrase": "20% improvement",
                        "rationale": "Calibrates the answer.",
                    }
                ],
            },
        },
        {
            "task_id": "source_hierarchy",
            "status": "parsed",
            "payload": {
                "schema_id": "source_weight_hierarchy_v1",
                "hierarchy_thesis": "Outcome evidence drives the answer; risk evidence bounds it.",
                "lanes": {
                    "primary_answer_drivers": [
                        {
                            "source_ids": ["s1"],
                            "evidence_item_ids": ["item:support"],
                            "role": "Answer driver.",
                            "rationale": "Direct outcome evidence.",
                        }
                    ],
                    "counterweight_sources": [
                        {
                            "source_ids": ["s2"],
                            "evidence_item_ids": ["item:risk"],
                            "role": "Counterweight.",
                            "rationale": "Budget risk.",
                        }
                    ],
                },
                "source_accounting": [
                    {"source_id": "s1", "primary_lane": "primary_answer_drivers", "rationale": "Direct support."},
                    {"source_id": "s2", "primary_lane": "counterweight_sources", "rationale": "Bounds support."},
                ],
            },
        },
        {
            "task_id": "argument_blueprint",
            "status": "parsed",
            "payload": {
                "schema_id": "global_argument_blueprint_v1",
                "memo_thesis": "Adopt option A, bounded by budget risk.",
                "section_plan": [
                    {
                        "section_id": "answer",
                        "heading": "Answer",
                        "section_job": "State the support and counterweight.",
                        "core_claim": "Option A is supported but bounded.",
                        "must_use_evidence_item_ids": ["item:support", "item:risk"],
                        "must_use_quantities": ["20% improvement"],
                        "source_weighting_move": "Use s1 as driver and s2 as boundary.",
                        "transition": "Then apply monitoring.",
                    }
                ],
            },
        },
    ]

    model = build_analyst_decision_model_from_global_tasks(context, task_results)
    report = build_analyst_decision_model_parse_report(model, _ledger(), retention_obligations=context["retention_obligations"])

    assert report["valid"] is True
    assert model["decision_logic"]["bounded_bottom_line"] == "Adopt option A with the stated boundary."
    assert model["decision_logic"]["counterweight_weighting"] == "Budget risk narrows where option A is attractive but does not erase the outcome evidence."
    assert "A direct implementation study" in " ".join(model["decision_logic"]["reconciled_cruxes"])
    assert "Track budget risk" in " ".join(model["decision_logic"]["practical_implications"])
    assert model["source_hierarchy"]["schema_id"] == "source_weight_hierarchy_v1"
    assert {row["evidence_item_id"] for row in model["memo_relevance_decisions"]} == {"item:support", "item:risk"}
    assert model["quantity_relevance_decisions"][0]["retention_phrase"] == "20% improvement"


def test_global_answer_frame_prompt_requests_controlling_judgments() -> None:
    answer_task = {task["task_id"]: task for task in build_global_analyst_tasks(_context())}["answer_frame"]
    schema = answer_task["schema"]

    assert "counterweight_weighting" in schema
    assert "what_would_change_the_answer" in schema
    assert "practical_implications" in schema


def _context() -> dict:
    return {
        "schema_id": "analyst_decision_context_v1",
        "decision_question": "Should option A be adopted?",
        "stable_final_answer_frame": {"current_best_answer": "Adopt option A."},
        "evidence_rows": [
            {
                "evidence_item_id": "item:support",
                "claim": "Option A improves the main outcome by 20%.",
                "current_role": "load_bearing_primary_support",
                "adjudicated_memo_use": "load_bearing_primary_support",
                "adjudicated_answer_relation": "supports_answer",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
                "quantity_values": ["20%"],
            },
            {
                "evidence_item_id": "item:risk",
                "claim": "Option A increases budget risk.",
                "current_role": "load_bearing_counterweight",
                "adjudicated_memo_use": "load_bearing_counterweight",
                "adjudicated_answer_relation": "challenges_answer",
                "source_ids": ["s2"],
                "source_labels": ["Risk Review"],
                "quantity_values": [],
            },
        ],
        "retention_obligations": {
            "quantitative_anchor_ids": ["item:support"],
            "counterweight_ids": ["item:risk"],
            "crux_ids": [],
            "scope_boundary_ids": [],
        },
    }


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "rows": _context()["evidence_rows"],
    }
