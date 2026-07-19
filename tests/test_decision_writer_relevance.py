from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)
from tests.test_decision_writer_packet import _global_model, _ledger


def test_decision_writer_packet_uses_group_roles_to_override_noisy_trace_only_relevance() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    analyst_model = _analyst_model_with_relevance(
        memo_relevance_decisions=[
            {
                "evidence_item_id": "item:support",
                "memo_inclusion": "trace_only",
                "group_id": "support_group",
                "source_ids": ["s1"],
                "rationale": "Noisy row-level relevance incorrectly routed this to trace.",
            },
            {
                "evidence_item_id": "item:limit",
                "memo_inclusion": "trace_only",
                "group_id": "scope_group",
                "source_ids": ["s2"],
                "rationale": "Noisy row-level relevance incorrectly routed this to trace.",
            },
        ]
    )

    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
        analyst_decision_model=analyst_model,
    )

    support = next(item for item in packet["evidence_items"] if item["reader_claim"] == "Option A improves the main outcome.")
    scope = next(item for item in packet["evidence_items"] if item["reader_claim"] == "The answer depends on whether the narrower setting matters.")
    assert support["must_use"] is True
    assert support["memo_inclusion"] == "memo_spine"
    assert support["analyst_relevance_decisions"][0]["overrode_memo_inclusion"] == "trace_only"
    assert "analyst_decision_model_relevance" in support["judgment_lineage"]
    assert scope["must_use"] is False
    assert scope["obligation_level"] == "should_include"
    assert scope["memo_inclusion"] == "supporting_context"
    assert scope["analyst_relevance_decisions"][0]["overrode_memo_inclusion"] == "trace_only"
    assert packet["analyst_relevance_plan"]["item:limit"]["memo_inclusion"] == "supporting_context"


def test_decision_writer_packet_preserves_explicit_exclusion_over_group_role() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    analyst_model = _analyst_model_with_relevance(
        memo_relevance_decisions=[
            {
                "evidence_item_id": "item:support",
                "memo_inclusion": "exclude",
                "group_id": "support_group",
                "source_ids": ["s1"],
                "rationale": "Explicitly outside the memo answer despite group membership.",
            }
        ]
    )

    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
        analyst_decision_model=analyst_model,
    )

    support = next(item for item in packet["evidence_items"] if item["reader_claim"] == "Option A improves the main outcome.")
    assert support["must_use"] is False
    assert support["memo_inclusion"] == "exclude"
    assert support["obligation_level"] == "optional_context"


def test_decision_writer_packet_uses_analyst_quantity_relevance_for_memo_quantities() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    analyst_model = _analyst_model_with_relevance(
        memo_relevance_decisions=[
            {
                "evidence_item_id": "item:support",
                "memo_inclusion": "memo_spine",
                "group_id": "support_group",
                "source_ids": ["s1"],
                "rationale": "Main support.",
            }
        ],
        quantity_relevance_decisions=[
            {
                "evidence_item_id": "item:support",
                "quantity_value": "20% improvement",
                "memo_inclusion": "must_use",
                "quantity_role": "decision_anchor",
                "retention_phrase": "20% improvement in the main outcome",
                "rationale": "This is the effect size that makes the decision concrete.",
            }
        ],
    )

    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
        analyst_decision_model=analyst_model,
        analyst_quantity_binding_report={"schema_id": "analyst_quantity_binding_report_v1", "status": "ready", "candidate_bindings": []},
    )

    support = packet["evidence_items"][0]
    assert support["quantities"][0]["value"] == "20% improvement"
    assert support["quantities"][0]["interpretation"] == "20% improvement in the main outcome"
    assert packet["quantity_obligation_plan"]["must_retain_count"] == 1
    quantity_row = packet["quantity_obligation_plan"]["rows"][0]
    assert quantity_row["binding_source"] == "analyst_decision_model"
    assert quantity_row["analyst_quantity_relevance"]["rationale"] == "This is the effect size that makes the decision concrete."


def _analyst_model_with_relevance(
    *,
    memo_relevance_decisions: list[dict],
    quantity_relevance_decisions: list[dict] | None = None,
) -> dict:
    return {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only where scope limits do not bind.",
        "confidence": "medium",
        "overall_rationale": "The outcome support matters more than broad context.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Option A improves the main outcome.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["item:support"],
                "rationale": "This is the memo spine.",
            },
            {
                "group_id": "scope_group",
                "proposition": "The narrower-setting evidence is audit context here.",
                "memo_role": "scope_or_applicability",
                "importance_rank": 2,
                "covered_evidence_item_ids": ["item:limit"],
                "rationale": "Useful for trace, not central enough for memo prose.",
            },
        ],
        "evidence_dispositions": [],
        "memo_relevance_decisions": memo_relevance_decisions,
        "quantity_relevance_decisions": quantity_relevance_decisions or [],
        "quantitative_anchors": ["20% improvement"] if quantity_relevance_decisions else [],
        "what_would_change_the_answer": [],
        "argument_plan": [],
        "decision_logic": {"bounded_bottom_line": "Adopt option A only where scope limits do not bind."},
    }
