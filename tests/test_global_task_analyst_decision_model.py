from __future__ import annotations

from epistemic_case_mapper.map_briefing_analyst_decision_model_global_tasks import (
    build_analyst_decision_model_from_global_tasks,
    build_global_analyst_task_prompt,
    build_global_analyst_tasks,
)
from epistemic_case_mapper.map_briefing_analyst_schemas import build_analyst_decision_model_parse_report


def test_global_analyst_tasks_use_task_specific_contexts() -> None:
    tasks = build_global_analyst_tasks(_context())
    by_id = {task["task_id"]: task for task in tasks}

    assert set(by_id) == {"answer_frame", "evidence_roles", "quantity_plan", "source_hierarchy", "argument_blueprint"}
    assert "quantity_bearing_evidence_rows" in by_id["quantity_plan"]["context"]
    assert "evidence_rows" not in by_id["quantity_plan"]["context"]
    assert "source_inventory" in by_id["source_hierarchy"]["context"]
    assert "decision_diagnostic_evidence_rows" in by_id["answer_frame"]["context"]
    assert len(build_global_analyst_task_prompt(by_id["quantity_plan"])) < len(build_global_analyst_task_prompt(by_id["evidence_roles"]))


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
                "scope_boundaries": ["Applies when budget risk is monitored."],
                "practical_implication": "Adopt with monitoring.",
                "do_not_overstate": ["Do not ignore budget risk."],
            },
        },
        {
            "task_id": "evidence_roles",
            "status": "parsed",
            "payload": {
                "schema_id": "global_evidence_roles_v1",
                "evidence_roles": [
                    {
                        "evidence_item_id": "item:support",
                        "memo_inclusion": "memo_spine",
                        "decision_role": "answer_driver",
                        "answer_relation": "supports_answer",
                        "priority_rank": 1,
                        "rationale": "Load-bearing support.",
                    },
                    {
                        "evidence_item_id": "item:risk",
                        "memo_inclusion": "memo_spine",
                        "decision_role": "counterweight",
                        "answer_relation": "challenges_answer",
                        "priority_rank": 2,
                        "rationale": "Load-bearing counterweight.",
                    },
                ],
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
    assert model["source_hierarchy"]["schema_id"] == "source_weight_hierarchy_v1"
    assert {row["evidence_item_id"] for row in model["memo_relevance_decisions"]} == {"item:support", "item:risk"}
    assert model["quantity_relevance_decisions"][0]["retention_phrase"] == "20% improvement"


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
