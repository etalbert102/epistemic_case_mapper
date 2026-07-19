from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_plan_qa_reports import (
    build_adversarial_memo_qa_report,
    build_compact_review_packet,
    build_memo_mutation_eval,
    build_relation_value_ablation_report,
    build_reviewer_effort_ablation_report,
)


def _scaffold() -> dict:
    return {
        "question": "Should option A be preferred?",
        "active_cited_source_report": {"active_source_ids": ["src001"]},
        "evidence_universe": {"active_source_ids": ["src001"], "analyzed_source_ids": ["src001", "src002"]},
        "analyst_decision_model_verification_report": {"status": "ready", "known_result_tuple_count": 1},
        "evidence_accounting_report": {"status": "ready"},
        "packet_quality_gate_report": {"status": "ready"},
        "analyst_evidence_ledger": {
            "rows": [
                {"evidence_item_id": "relation:r001", "input_kind": "decision_relation", "source_ids": ["src001"]},
            ]
        },
        "analyst_decision_model": {
            "decision_question": "Should option A be preferred?",
            "counterweight_dispositions": [
                {"evidence_item_ids": ["claim:risk"], "disposition": "bounds_scope", "rationale": "Scope risk."}
            ],
            "cruxes": [{"crux": "External validity", "evidence_item_ids": ["claim:one"], "current_read": "Unclear"}],
            "quantity_relevance_decisions": [
                {
                    "evidence_item_id": "claim:one",
                    "quantity_value": "20 percent",
                    "result_tuple_ids": ["qt001"],
                    "memo_inclusion": "must_use",
                }
            ],
            "decision_logic": {"do_not_overstate": ["Do not generalize beyond matching settings."]},
        },
    }


def test_relation_and_reviewer_reports_surface_value_and_review_packet() -> None:
    scaffold = _scaffold()
    prioritized_map = {"relations": [{"relation_id": "r001"}]}

    relation = build_relation_value_ablation_report(prioritized_map=prioritized_map, scaffold=scaffold)
    packet = build_compact_review_packet(scaffold=scaffold)
    reviewer = build_reviewer_effort_ablation_report(scaffold=scaffold)

    assert relation["recommendation"] == "keep_relation_stage"
    assert packet["strongest_counterweight"]["disposition"] == "bounds_scope"
    assert reviewer["status"] == "ready"


def test_adversarial_memo_qa_reports_source_and_quantity_issues_without_blocking() -> None:
    memo = "Option A is preferred. [src999]"
    report = build_adversarial_memo_qa_report(memo_markdown=memo, scaffold=_scaffold())

    assert report["status"] == "report_only_warning"
    assert "source_outside_active_universe" in report["warnings"]
    assert "must_use_quantity_not_visible" in report["warnings"]
    assert "do_not_overstate_constraint_not_visible" in report["warnings"]


def test_memo_mutation_eval_detects_outside_source_injection() -> None:
    memo = "Option A improves the outcome by 20 percent. Do not generalize beyond matching settings. [src001]"
    report = build_memo_mutation_eval(memo_markdown=memo, scaffold=_scaffold())

    assert report["status"] == "ready"
    assert report["detected_mutation_count"] == 1
