from __future__ import annotations

from copy import deepcopy

from epistemic_case_mapper.map_briefing_analyst_evidence_ledger import build_analyst_evidence_ledger
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
