from __future__ import annotations

from epistemic_case_mapper.map_briefing_analyst_schemas import AnalystDecisionModel
from epistemic_case_mapper.map_briefing_analyst_verifier import build_analyst_decision_model_verification_report


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should we adopt option A?",
        "rows": [
            {
                "evidence_item_id": "claim:one",
                "source_ids": ["src001"],
                "claim": "Option A improves the decision-relevant outcome.",
                "source_excerpt": "Option A improved the outcome by 20 percent.",
                "source_span": "line 1",
                "quantity_tuples": [
                    {
                        "result_tuple_id": "claim_one_q001",
                        "value": "20 percent",
                        "source_id": "src001",
                        "source_quote": "Option A improved the outcome by 20 percent.",
                        "source_span": "line 1",
                    }
                ],
            }
        ],
    }


def _model() -> dict:
    return {
        "schema_id": "analyst_decision_model_v2",
        "decision_question": "Should we adopt option A?",
        "active_evidence_universe": {
            "full_reasoning_evidence_item_ids": ["claim:one"],
            "routed_away_evidence_item_ids": [],
            "source_ids": ["src001"],
        },
        "direct_answer": "Option A is provisionally favored.",
        "confidence": "medium",
        "overall_rationale": "The only source-bound outcome evidence favors option A.",
        "evidence_groups": [
            {
                "group_id": "support",
                "proposition": "Option A improves the outcome.",
                "memo_role": "load_bearing_primary_support",
                "covered_evidence_item_ids": ["claim:one"],
                "rationale": "It directly answers the question.",
            }
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "claim:one", "disposition": "foreground", "group_id": "support", "rationale": "Used."}
        ],
        "memo_relevance_decisions": [
            {
                "evidence_item_id": "claim:one",
                "memo_inclusion": "memo_spine",
                "rationale": "It carries the answer.",
                "source_ids": ["src001"],
            }
        ],
        "quantity_relevance_decisions": [
            {
                "evidence_item_id": "claim:one",
                "quantity_value": "20 percent",
                "result_tuple_ids": ["claim_one_q001"],
                "memo_inclusion": "must_use",
                "quantity_role": "decision_anchor",
                "retention_phrase": "20 percent outcome improvement",
                "rationale": "It sizes the answer.",
            }
        ],
        "counterweight_dispositions": [],
        "cruxes": [{"crux": "Whether this generalizes.", "evidence_item_ids": ["claim:one"], "current_read": "Unknown."}],
        "update_triggers": [],
        "practical_implications": [{"implication": "Prefer option A in matching settings.", "evidence_item_ids": ["claim:one"], "source_ids": ["src001"], "scope": "matching settings"}],
        "do_not_overstate_constraints": ["Do not generalize beyond matching settings."],
        "appendix_accounting": [],
        "source_hierarchy": {},
        "source_hierarchy_report": {},
        "source_weight_judgments": [],
        "source_weight_judgment_report": {},
        "quantitative_anchors": ["20 percent"],
        "what_would_change_the_answer": ["External validity evidence."],
        "argument_plan": [],
        "decision_logic": {"bounded_bottom_line": "Option A is provisionally favored.", "practical_implications": ["Prefer option A in matching settings."]},
    }


def test_analyst_decision_model_accepts_v2_surface() -> None:
    parsed = AnalystDecisionModel.model_validate(_model())

    assert parsed.schema_id == "analyst_decision_model_v2"
    assert parsed.active_evidence_universe["source_ids"] == ["src001"]
    assert parsed.quantity_relevance_decisions[0].result_tuple_ids == ["claim_one_q001"]


def test_analyst_verifier_accepts_clean_hard_invariants() -> None:
    report = build_analyst_decision_model_verification_report(
        analyst_decision_model=_model(),
        ledger=_ledger(),
        parse_report={"issues": []},
    )

    assert report["accepted"] is True
    assert report["status"] in {"ready", "warning"}
    assert report["fatal_issues"] == []
    assert report["unknown_result_tuple_ids"] == []


def test_analyst_verifier_blocks_unknown_ids_before_writer_projection() -> None:
    model = _model()
    model["evidence_groups"][0]["covered_evidence_item_ids"] = ["claim:missing"]
    model["quantity_relevance_decisions"][0]["result_tuple_ids"] = ["tuple:missing"]

    report = build_analyst_decision_model_verification_report(
        analyst_decision_model=model,
        ledger=_ledger(),
        parse_report={"issues": []},
    )

    assert report["accepted"] is False
    assert "unknown_evidence_item_ids" in report["fatal_issues"]
    assert "unknown_result_tuple_ids" in report["fatal_issues"]
