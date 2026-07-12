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
                "decision_edge_role": "outcome_finding",
                "decision_importance_level": "high",
                "decision_function": "answer_bearing",
                "question_relevance": "direct",
                "claim_quantities": [
                    {
                        "value": "20 percent",
                        "quantity_role": "effect_estimate",
                        "measures": "flood loss reduction",
                        "local_interpretation": "Main estimated benefit.",
                        "source_quote": "reduces flood losses by 20 percent",
                        "line_hint": "lines 1-1",
                        "retention_hint": "must_retain",
                    }
                ],
                "whole_doc_source_card": {"quantities": ["20 percent"]},
            },
            {
                "claim_id": "c002",
                "claim": "Option A shifts maintenance costs to neighborhoods with lower tax capacity.",
                "source_id": "s2",
                "excerpt": "shifts maintenance costs to neighborhoods with lower tax capacity",
                "decision_edge_role": "scope_or_subgroup_boundary",
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
                "relation_confidence": "high",
                "relation_contract": {
                    "edge_basis": "source_inferred",
                    "source_anchor_a": "shifts maintenance costs",
                    "source_anchor_b": "reduces flood losses",
                    "why_decision_relevant": "Costs limit the benefit claim.",
                    "failure_condition": "The edge weakens if maintenance costs are already included in the benefit estimate.",
                },
                "candidate_pair": {
                    "pair_id": "pair_001",
                    "score": 12.5,
                    "reason": "scope_bounds_outcome+cross_source",
                    "decision_edge_contract": "scope_bounds_outcome",
                    "pair_intent": {"intent": "scope_bounds_outcome", "allowed_relation_types": ["refines", "depends_on", "none"]},
                },
            }
        ],
    }
    scaffold = {
        "source_display_names": {"s1": "Benefit Study", "s2": "Equity Review"},
        "quantity_ledger": {"quantities": [{"claim_id": "c001", "quantity_text": "20 percent"}]},
        "source_appraisal_report": {
            "schema_id": "source_appraisal_report_v1",
            "status": "ready",
            "appraisal_by_source_id": {
                "s1": {
                    "source_appraisal_id": "sa_s1",
                    "source_id": "s1",
                    "source_label": "Benefit Study",
                    "status": "ready",
                    "source_use_warnings": ["association_not_causation"],
                    "allowed_wording": {"causal_language_allowed": False},
                },
                "s2": {
                    "source_appraisal_id": "sa_s2",
                    "source_id": "s2",
                    "source_label": "Equity Review",
                    "status": "ready",
                    "source_use_warnings": ["scope_sensitive"],
                    "allowed_wording": {"preferred_verbs": ["bounds"]},
                },
            },
        },
    }

    ledger = build_analyst_map_evidence_ledger(
        candidate_map,
        scaffold,
        question="Should the city adopt option A for flood protection?",
    )

    assert ledger["method"] == "retained_claim_map_inventory_for_llm_adjudicated_packet_construction"
    assert ledger["coverage_checks"]["retained_map_claim_rows"] == 2
    assert [row["evidence_item_id"] for row in ledger["rows"]] == ["claim:c001", "claim:c002", "relation:r001"]
    assert ledger["rows"][0]["source_labels"] == ["Benefit Study"]
    assert ledger["rows"][0]["source_appraisal"]["status"] == "ready"
    assert "association_not_causation" in ledger["rows"][0]["source_use_warnings"]
    assert ledger["rows"][0]["quantity_values"] == ["20 percent"]
    assert ledger["rows"][0]["claim_quantities"][0]["quantity_role"] == "effect_estimate"
    assert ledger["rows"][0]["claim_quantities"][0]["measures"] == "flood loss reduction"
    assert ledger["rows"][1]["existing_warning_codes"] == ["question_scope_mismatch"]
    assert ledger["rows"][1]["relation_context"][0]["relation_type"] == "in_tension_with"
    assert ledger["rows"][1]["relation_context"][0]["relation_contract"]["failure_condition"]
    assert ledger["rows"][2]["input_kind"] == "candidate_decision_edge"
    assert ledger["rows"][2]["source_appraisal"]["status"] == "ready"
    assert "scope_sensitive" in ledger["rows"][2]["source_use_warnings"]
    assert ledger["rows"][2]["current_role"] == "load_bearing_counterweight"
    assert ledger["rows"][2]["relation_contract"]["source_anchor_a"] == "shifts maintenance costs"
    assert ledger["rows"][2]["candidate_pair"]["decision_edge_contract"] == "scope_bounds_outcome"
    assert ledger["rows"][2]["endpoint_claims"][0]["decision_edge_role"] == "scope_or_subgroup_boundary"
