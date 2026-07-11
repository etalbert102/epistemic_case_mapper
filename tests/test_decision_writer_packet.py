from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "item:support",
                "claim_id": "support",
                "claim": "Option A improves the main outcome.",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Review"],
                "quantity_values": ["20% improvement"],
                "source_excerpt": "The main outcome improved by 20%.",
                "why_it_matters": "The improvement is the main support.",
            },
            {
                "evidence_item_id": "item:limit",
                "claim_id": "limit",
                "claim": "The result may not apply in a narrower setting.",
                "source_ids": ["s2"],
                "source_labels": ["Scope Review"],
                "source_excerpt": "The result did not cover the narrower setting.",
            },
            {
                "evidence_item_id": "item:missing",
                "claim_id": "missing",
                "claim": "This item has not been accounted for.",
                "source_ids": ["s3"],
                "source_labels": ["Open Question"],
            },
        ],
    }


def _global_model(*, missing: bool = False) -> dict:
    return {
        "schema_id": "global_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "bounded_answer": "Adopt option A only where the narrower setting is not decisive.",
        "confidence": "medium",
        "confidence_reasons": ["Support is meaningful but scope limits apply."],
        "strongest_support": [
            {
                "group_id": "support_group",
                "proposition": "Option A improves the main outcome.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["item:support"],
                "rationale": "This is the main support.",
            }
        ],
        "strongest_counterargument": [],
        "scope_boundaries": [
            {
                "group_id": "scope_group",
                "proposition": "The answer depends on whether the narrower setting matters.",
                "memo_role": "scope_or_applicability",
                "importance_rank": 2,
                "covered_evidence_item_ids": ["item:limit"],
                "rationale": "This bounds adoption.",
            }
        ],
        "decision_cruxes": [],
        "contextual_evidence": [],
        "argument_plan": [{"step_id": "support_then_scope", "evidence_item_ids": ["item:support", "item:limit"]}],
        "decision_logic": {"bounded_bottom_line": "Adopt option A only where the narrower setting is not decisive."},
        "evidence_accounting": {
            "missing_accounting_ids": ["item:missing"] if missing else [],
            "obligation_omissions": {"ungrouped_scope_boundary_ids": ["item:missing"]} if missing else {},
        },
        "reconciliation": {"issues": ["missing_evidence_accounting"] if missing else []},
    }


def test_decision_writer_packet_uses_global_model_as_answer_owner() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = bundle["decision_writer_packet"]
    quality = bundle["decision_writer_packet_quality_report"]

    assert packet["schema_id"] == "decision_writer_packet_v1"
    assert packet["answer"]["bounded_answer"] == "Adopt option A only where the narrower setting is not decisive."
    assert "answer_spine" not in packet
    assert "analyst_synthesis_packet" not in packet
    assert packet["evidence_units"][0]["role"] == "strongest_support"
    assert packet["evidence_units"][0]["quantities"][0]["value"] == "20% improvement"
    assert quality["status"] == "ready"


def test_decision_writer_packet_builds_deterministic_source_trail_and_traceability() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = bundle["decision_writer_packet"]
    matrix = bundle["evidence_unit_traceability_matrix"]

    assert [row["source_label"] for row in packet["source_trail"]] == ["Outcome Review", "Scope Review"]
    assert packet["source_aliases"]["Outcome Review"] == "Outcome Review"
    assert matrix["row_count"] == 3
    assert matrix["covered_row_count"] == 2
    missing_row = next(row for row in matrix["rows"] if row["evidence_item_id"] == "item:missing")
    assert missing_row["in_writer_packet"] is False


def test_decision_writer_packet_flags_missing_critical_evidence() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(missing=True), ledger=_ledger())
    quality = bundle["decision_writer_packet_quality_report"]

    assert quality["status"] == "warning"
    assert quality["missing_critical_evidence_item_ids"] == ["item:missing"]
    assert "critical_evidence_not_accounted" in quality["issues"]
    assert "global_model_has_reconciliation_warnings" in quality["issues"]


def test_decision_writer_packet_adapts_to_active_memo_ready_packet() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    assert packet["schema_id"] == "memo_ready_packet_v1"
    assert packet["method"] == "global_decision_writer_packet_adapter"
    assert packet["answer_spine"]["default_read"] == "Adopt option A only where the narrower setting is not decisive."
    assert packet["writer_packet"]["schema_id"] == "decision_writer_packet_v1"
    assert packet["evidence_items"][0]["reader_claim"] == "Option A improves the main outcome."
    assert packet["evidence_items"][0]["must_use"] is True
    assert packet["evidence_items"][0]["quantities"][0]["value"] == "20% improvement"
