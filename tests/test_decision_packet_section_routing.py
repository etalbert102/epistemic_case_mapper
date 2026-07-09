from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle

from test_decision_briefing_packet import _scaffold


def test_why_this_read_gets_support_counterweight_and_boundary_routes() -> None:
    result = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = result["decision_briefing_packet"]
    views = {row["section"]: row for row in packet["section_views"]}
    bundles = {row["bundle_id"]: row for row in packet["evidence_bundles"]}
    why = views["Why This Read"]

    assert any(bundles[bundle_id]["decision_role"] in {"strongest_support", "quantitative_anchor"} for bundle_id in why["primary_bundle_ids"])
    assert any(bundles[bundle_id]["decision_role"] == "counterweight" for bundle_id in why["contrast_bundle_ids"])
    assert any(bundles[bundle_id]["decision_role"] == "scope_boundary" for bundle_id in why["boundary_bundle_ids"])
