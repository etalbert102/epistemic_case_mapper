from __future__ import annotations

from copy import deepcopy

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle

from test_decision_briefing_packet import _scaffold


def test_top_quantity_anchor_groups_create_first_class_bundles() -> None:
    scaffold = _scaffold()
    for card in scaffold["candidate_evidence_cards"]["cards"]:
        card["quantity_values"] = []
    for card in scaffold["source_evidence_cards"]["cards"]:
        card["quantity_values"] = []

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    quantity_bundles = [
        row
        for row in result["decision_briefing_packet"]["evidence_bundles"]
        if row.get("decision_role") == "quantitative_anchor"
    ]

    assert quantity_bundles
    assert any(row.get("pretrim_kind") == "quantity_ledger.top_quantitative_anchor" for row in quantity_bundles)
    assert any("25%" in row.get("quantity_values", []) for row in quantity_bundles)


def test_richness_aware_dedupe_prefers_quantity_row_over_thin_duplicate() -> None:
    scaffold = _scaffold()
    scaffold["candidate_evidence_cards"]["cards"][0]["quantity_values"] = []
    scaffold["source_evidence_cards"]["cards"][0]["quantity_values"] = []
    thin = deepcopy(scaffold["candidate_evidence_cards"]["cards"][0])
    thin.update(
        {
            "candidate_card_id": "ec_thin_duplicate",
            "source_card_ids": [],
            "claim_ids": ["c_shared"],
            "source_ids": ["s1"],
            "claim": "Option A has a thin duplicate claim without the quantitative result.",
            "role": "context",
            "evidence_roles": ["context"],
            "quantity_values": [],
            "decision_relevance_score": 8,
        }
    )
    scaffold["candidate_evidence_cards"]["cards"].append(thin)
    scaffold["quantity_ledger"]["evidence_cards"].append(
        {
            "card_id": "qc_shared",
            "claim_id": "c_shared",
            "claim": "Option A has a richer quantitative duplicate with a 41% reduction.",
            "context": "Option A has a richer quantitative duplicate with a 41% reduction.",
            "key_quantities": ["41%"],
            "effect_estimates": ["41%"],
            "source": "Outcome Study",
            "card_score": 40,
        }
    )

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    matching = [
        row
        for row in result["decision_briefing_packet"]["evidence_bundles"]
        if "c_shared" in row.get("claim_ids", [])
    ]

    assert matching
    assert matching[0]["decision_role"] == "quantitative_anchor"
    assert "41%" in matching[0].get("quantity_values", [])
