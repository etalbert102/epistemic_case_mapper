from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_analyst_decision_model_parallel import (
    build_decision_model_task_prompt,
    merge_decision_model_payloads,
)


def _context() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "evidence_rows": [
            {
                "evidence_item_id": "item:support",
                "claim": "Option A improves the main outcome by 20%.",
                "current_role": "load_bearing_primary_support",
                "quantity_values": ["20%"],
                "source_ids": ["source:a"],
            },
            {
                "evidence_item_id": "item:background",
                "claim": "The study also reports a baseline age of 45 years.",
                "current_role": "background_only",
                "quantity_values": ["45 years"],
                "source_ids": ["source:b"],
            },
        ],
    }


def test_parallel_decision_model_task_prompt_includes_relevance_contract() -> None:
    prompt = build_decision_model_task_prompt(
        {
            "task_id": "task_001",
            "decision_question": "Should option A be adopted?",
            "stable_final_answer_frame": {},
            "evidence_rows": _context()["evidence_rows"],
            "obligation_group_skeleton": [],
            "model_hints": {},
        }
    )
    packet = json.loads(prompt)

    schema = packet["required_output_schema"]
    assert "memo_relevance_decisions" in schema
    assert "quantity_relevance_decisions" in schema
    assert "For every supplied evidence_item_id" in " ".join(packet["instructions"])


def test_parallel_decision_model_merge_preserves_relevance_decisions() -> None:
    merged = merge_decision_model_payloads(
        _context(),
        [
            {
                "schema_id": "analyst_decision_model_v1",
                "decision_question": "Should option A be adopted?",
                "direct_answer": "Adopt option A.",
                "confidence": "medium",
                "overall_rationale": "The main outcome improvement drives the answer.",
                "evidence_groups": [
                    {
                        "group_id": "support_group",
                        "proposition": "Option A improves the main outcome.",
                        "memo_role": "load_bearing_primary_support",
                        "importance_rank": 1,
                        "covered_evidence_item_ids": ["item:support"],
                        "rationale": "This is the direct decision support.",
                    }
                ],
                "evidence_dispositions": [
                    {
                        "evidence_item_id": "item:background",
                        "disposition": "background",
                        "rationale": "Baseline detail is audit context.",
                    }
                ],
                "memo_relevance_decisions": [
                    {
                        "evidence_item_id": "item:support",
                        "memo_inclusion": "memo_spine",
                        "group_id": "support_group",
                        "source_ids": ["source:a"],
                        "rationale": "The memo would be materially worse without the effect size.",
                    }
                ],
                "quantity_relevance_decisions": [
                    {
                        "evidence_item_id": "item:support",
                        "quantity_value": "20%",
                        "memo_inclusion": "must_use",
                        "quantity_role": "decision_anchor",
                        "retention_phrase": "20% improvement in the main outcome",
                        "rationale": "This calibrates the answer.",
                    }
                ],
            }
        ],
    )

    relevance_by_id = {row["evidence_item_id"]: row for row in merged["memo_relevance_decisions"]}
    quantity_by_value = {row["quantity_value"]: row for row in merged["quantity_relevance_decisions"]}

    assert relevance_by_id["item:support"]["memo_inclusion"] == "memo_spine"
    assert relevance_by_id["item:background"]["memo_inclusion"] == "trace_only"
    assert quantity_by_value["20%"]["memo_inclusion"] == "must_use"
    assert quantity_by_value["45 years"]["memo_inclusion"] == "trace_only"

