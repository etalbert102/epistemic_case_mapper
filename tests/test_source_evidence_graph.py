from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_evidence_graph import build_source_evidence_graph

from test_decision_briefing_packet import _scaffold


def test_source_evidence_graph_preserves_source_claim_quantity_lineage() -> None:
    graph = build_source_evidence_graph(_scaffold())
    node_ids = {node["node_id"] for node in graph["nodes"]}
    edges = {
        (edge["source_node_id"], edge["target_node_id"], edge["edge_type"])
        for edge in graph["edges"]
    }

    assert graph["schema_id"] == "source_evidence_graph_v1"
    assert "source:s1" in node_ids
    assert "source_card:sc0001" in node_ids
    assert "claim:c1" in node_ids
    assert any(node["node_type"] == "quantity" and node.get("quantity") == "25%" for node in graph["nodes"])
    assert ("source:s1", "source_card:sc0001", "source_has_card") in edges
    assert ("source_card:sc0001", "claim:c1", "card_supports_claim") in edges
    assert graph["summary"]["source_node_count"] >= 3
    assert graph["summary"]["claim_node_count"] >= 3
    assert graph["summary"]["quantity_node_count"] >= 1


def test_decision_packet_embeds_source_evidence_graph() -> None:
    result = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    graph = result["source_evidence_graph"]

    assert result["decision_briefing_packet"]["source_evidence_graph"] == graph
    assert graph["summary"]["node_count"] >= 1
    assert graph["summary"]["edge_count"] >= 1
