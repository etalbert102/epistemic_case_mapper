from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_interpretation_plan import build_decision_interpretation_plan


def test_decision_interpretation_plan_projects_roles_into_reader_use() -> None:
    context = {
        "decision_evidence_table": [
            {
                "item_id": "support",
                "role": "strongest_support",
                "answer_relation": "supports_answer",
                "claim": "Option A improves the main outcome.",
                "decision_relevance": "This is the main reason to adopt option A.",
                "source_labels": ["Outcome Review"],
                "quantities": [{"value": "20%", "interpretation": "large enough to matter"}],
            },
            {
                "item_id": "scope",
                "role": "scope_boundary",
                "answer_relation": "bounds_scope",
                "claim": "The evidence applies only to urban settings.",
                "quantities": [{"value": "urban"}],
            },
        ],
        "mandatory_evidence_ledger": [
            {"item_id": "support", "role": "strongest_support", "claim": "Option A improves the main outcome."},
            {"item_id": "missing", "role": "decision_crux", "claim": "Costs could change the answer."},
        ],
    }

    plan = build_decision_interpretation_plan(context)

    assert plan["schema_id"] == "decision_interpretation_plan_v1"
    assert plan["missing_mandatory_item_ids"] == []
    support = next(row for row in plan["interpretations"] if row["item_id"] == "support")
    assert support["answer_effect"] == "supports_default_answer"
    assert support["reader_use"] == "main_reason"
    assert support["decision_interpretation"] == "This is the main reason to adopt option A."
    assert support["quantity_meanings"][0]["meaning"] == "large enough to matter"
    scope = next(row for row in plan["interpretations"] if row["item_id"] == "scope")
    assert scope["answer_effect"] == "bounds_where_answer_applies"
    assert "bound" in scope["quantity_meanings"][0]["meaning"]
    missing = next(row for row in plan["interpretations"] if row["item_id"] == "missing")
    assert missing["reader_use"] == "crux_or_uncertainty"
