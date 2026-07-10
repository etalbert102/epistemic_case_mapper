from __future__ import annotations

from copy import deepcopy

from epistemic_case_mapper.map_briefing_analyst_evidence_ledger import build_analyst_evidence_ledger, build_analyst_map_evidence_ledger
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle

from test_decision_briefing_packet import _scaffold


def test_analyst_evidence_ledger_accounts_for_bundles_warnings_and_top_quantities() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    packet["source_trail"].append({"source_id": "s4", "source_label": "Equity Review"})
    packet["coverage_report"]["truly_lost_decision_critical"] = [
        {
            "candidate_card_id": "ec_warning",
            "decision_role": "counterweight",
            "priority": 10,
            "source_ids": ["s4"],
            "claim": "Option A shifted flood risk toward downstream neighborhoods.",
            "quantity_values": ["3 neighborhoods"],
        }
    ]

    bundle = build_quality_synthesis_packet_bundle(packet)
    ledger = bundle["analyst_evidence_ledger"]
    rows = ledger["rows"]

    assert ledger["schema_id"] == "analyst_evidence_ledger_v1"
    assert ledger["coverage_checks"]["retained_bundle_rows"] == len(packet["evidence_bundles"])
    assert ledger["coverage_checks"]["memo_warning_rows"] == 1
    assert any(row["input_kind"] == "top_quantity_anchor" for row in rows)
    assert any(row["evidence_item_id"] == "warning:memo_warning_001" for row in rows)
    assert any("Equity Review" in row.get("source_labels", []) for row in rows)
    assert len({row["evidence_item_id"] for row in rows}) == len(rows)


def test_analyst_evidence_ledger_ids_are_stable_under_source_trail_order_changes() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet_a = built["decision_briefing_packet"]
    packet_b = deepcopy(packet_a)
    packet_b["source_trail"] = list(reversed(packet_b["source_trail"]))

    ledger_a = build_analyst_evidence_ledger(packet_a)
    ledger_b = build_analyst_evidence_ledger(packet_b)

    assert [row["evidence_item_id"] for row in ledger_a["rows"]] == [
        row["evidence_item_id"] for row in ledger_b["rows"]
    ]


def test_analyst_map_evidence_ledger_adjudicates_retained_claim_map_with_relation_context() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Option A reduces flood losses by 20 percent.",
                "source_id": "s1",
                "source_quote": "reduces flood losses by 20 percent",
                "decision_importance_level": "high",
                "decision_function": "answer_bearing",
                "question_relevance": "direct",
                "whole_doc_source_card": {"quantities": ["20 percent"]},
            },
            {
                "claim_id": "c002",
                "claim": "Option A shifts maintenance costs to neighborhoods with lower tax capacity.",
                "source_id": "s2",
                "excerpt": "shifts maintenance costs to neighborhoods with lower tax capacity",
                "decision_importance_level": "medium",
                "decision_function": "scope_boundary",
                "question_relevance": "scope_limit",
                "validation_warnings": ["question_scope_mismatch"],
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "in_tension_with",
                "rationale": "The distributional cost claim limits the apparent flood-loss benefit.",
            }
        ],
    }
    scaffold = {
        "source_display_names": {"s1": "Benefit Study", "s2": "Equity Review"},
        "quantity_ledger": {"quantities": [{"claim_id": "c001", "quantity_text": "20 percent"}]},
    }

    ledger = build_analyst_map_evidence_ledger(
        candidate_map,
        scaffold,
        question="Should the city adopt option A for flood protection?",
    )

    assert ledger["method"] == "retained_claim_map_inventory_for_llm_adjudicated_packet_construction"
    assert ledger["coverage_checks"]["retained_map_claim_rows"] == 2
    assert [row["evidence_item_id"] for row in ledger["rows"]] == ["claim:c001", "claim:c002"]
    assert ledger["rows"][0]["source_labels"] == ["Benefit Study"]
    assert ledger["rows"][0]["quantity_values"] == ["20 percent"]
    assert ledger["rows"][1]["existing_warning_codes"] == ["question_scope_mismatch"]
    assert ledger["rows"][1]["relation_context"][0]["relation_type"] == "in_tension_with"
