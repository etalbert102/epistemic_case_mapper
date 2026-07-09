from __future__ import annotations

from copy import deepcopy

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_packet_refinement import run_packet_critique_and_refinement

from test_decision_briefing_packet import _scaffold


def test_quantity_obligation_ledger_aligns_coverage_and_sufficiency_counts() -> None:
    scaffold = _scaffold()
    scaffold["quantity_ledger"]["evidence_cards"] = [
        {
            "card_id": "qc_label_source",
            "claim_id": "c4",
            "claim": "Outcome Study reports a broad quantitative result for option A.",
            "context": "Outcome Study reports 1%, 2%, 3%, and 4% effects.",
            "key_quantities": ["1%", "2%", "3%", "4%"],
            "effect_estimates": ["1%", "2%", "3%", "4%"],
            "source": "Outcome Study",
            "card_score": 40,
        }
    ]

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    packet = result["decision_briefing_packet"]
    sufficiency = result["packet_sufficiency_report"]
    ledger = sufficiency["quantity_obligation_ledger"]

    assert ledger["schema_id"] == "quantity_obligation_ledger_v1"
    assert ledger["obligation_count"] == len(sufficiency["quantity_retention"]["top_quantities"])
    assert ledger["missing_quantities"] == sufficiency["quantity_retention"]["missing_top_quantities"]
    assert packet["coverage_report"]["quantity_missing_count"] == ledger["missing_count"]
    assert packet["coverage_report"]["quantity_obligation_count"] == ledger["obligation_count"]
    assert all("quantity" in row and "status" in row for row in ledger["obligations"])


def test_post_refinement_quantity_telemetry_preserves_prior_obligations() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = deepcopy(built["decision_briefing_packet"])
    for item in packet["must_retain_ledger"]:
        item["required_terms"] = []
        item["statement"] = "The quantified result was removed from the retain text."

    result = run_packet_critique_and_refinement(
        packet,
        built["packet_sufficiency_report"],
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
    )

    ledger = result["packet_sufficiency_report"]["quantity_obligation_ledger"]
    coverage = result["decision_briefing_packet"]["coverage_report"]

    assert ledger["obligation_count"] == 1
    assert ledger["missing_count"] == 1
    assert coverage["quantity_missing_count"] == ledger["missing_count"]
    assert coverage["quantity_obligation_count"] == ledger["obligation_count"]
