from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_packet import (
    build_memo_ready_packet_synthesis_prompt,
    build_quality_synthesis_packet_bundle,
)

from test_decision_briefing_packet import _scaffold


def test_quality_synthesis_packet_builds_assembly_artifacts() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")

    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])

    assert result["packet_assembly_clusters"]["schema_id"] == "packet_assembly_clusters_v1"
    assert result["packet_role_assignment_report"]["schema_id"] == "packet_role_assignment_report_v1"
    assert result["diagnosticity_matrix"]["schema_id"] == "diagnosticity_matrix_v1"
    assert result["quantity_binding_report"]["schema_id"] == "quantity_binding_report_v1"
    assert result["packet_assembly_audit"]["schema_id"] == "packet_assembly_audit_v1"
    assert result["memo_ready_packet"]["schema_id"] == "memo_ready_packet_v1"
    assert result["memo_ready_packet_quality_report"]["schema_id"] == "memo_ready_packet_quality_report_v1"


def test_memo_ready_packet_preserves_roles_quantities_and_lineage() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])
    packet = result["memo_ready_packet"]

    roles = {item["role"] for item in packet["evidence_items"]}
    assert {"quantitative_anchor", "strongest_counterweight", "scope_boundary"} <= roles
    quantity_items = [item for item in packet["evidence_items"] if item["role"] == "quantitative_anchor"]
    assert any(quantity.get("value") == "25%" for item in quantity_items for quantity in item.get("quantities", []))
    assert all(item["lineage"]["derived_from_claim_ids"] for item in packet["evidence_items"] if item["must_use"])
    assert all(item.get("source_label") for item in packet["evidence_items"] if item["must_use"])
    assert all(item["argument"]["warrant"] for item in packet["evidence_items"] if item["must_use"])


def test_packet_assembly_keeps_cross_source_near_duplicates_separate() -> None:
    scaffold = _scaffold()
    scaffold["source_display_names"]["s4"] = "Second Outcome Study"
    scaffold["candidate_evidence_cards"]["cards"].append(
        {
            "candidate_card_id": "ec0004",
            "source_card_ids": ["sc0004"],
            "claim_ids": ["c4"],
            "source_ids": ["s4"],
            "source_titles": ["Second Outcome Study"],
            "claim": "Option A reduced flood losses by 25 percent in comparable river cities.",
            "role": "support",
            "evidence_roles": ["support"],
            "decision_relevance_score": 9,
            "inclusion_recommendation": "main_text",
            "inclusion_reason": "Independent confirmation.",
            "anchor_confidence": "exact",
            "quantity_values": ["25 percent"],
        }
    )
    built = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])

    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])
    kept_separate = result["packet_assembly_clusters"]["kept_separate_near_duplicates"]

    assert kept_separate
    assert any(row["reason"] == "kept_separate_due_to_distinct_blocking_key" for row in kept_separate)


def test_quantity_binding_excludes_unbound_quantities_from_mandatory_obligations() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    packet["evidence_bundles"].append(
        {
            "bundle_id": "bundle_unbound",
            "decision_role": "quantitative_anchor",
            "claim": "A floating quantity lacks source lineage.",
            "quantity_values": ["42%"],
            "weight": "high",
        }
    )

    result = build_quality_synthesis_packet_bundle(packet)
    binding = result["quantity_binding_report"]
    memo_ready = result["memo_ready_packet"]

    assert binding["unbound_quantity_group_count"] >= 1
    assert not any(
        item["reader_claim"] == "A floating quantity lacks source lineage." and item["must_use"]
        for item in memo_ready["evidence_items"]
    )


def test_synthesis_prompt_uses_memo_ready_packet_not_legacy_section_contract() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])

    prompt = build_memo_ready_packet_synthesis_prompt(result["memo_ready_packet"])

    assert "memo-ready evidence packet" in prompt
    assert "Why This Read" not in prompt
    assert "Evidence Carrying the Conclusion" not in prompt
    assert "25%" in prompt
    assert "Counter Study" in prompt
