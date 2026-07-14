from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_packet import (
    build_memo_ready_packet_synthesis_prompt,
    build_quality_synthesis_packet_bundle,
)

from test_decision_briefing_packet import _scaffold


def test_synthesis_prompt_uses_canonical_packet_not_legacy_context_surfaces() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])

    prompt = build_memo_ready_packet_synthesis_prompt(result["memo_ready_packet"])

    assert "canonical decision writer packet" in prompt
    assert "canonical_decision_writer_packet_v1" in prompt
    assert "reader_synthesis_packet_v1" in prompt
    assert "answer_frame" in prompt
    assert "source_weighting" in prompt
    assert "argument_spine" in prompt
    assert "limiting_evidence" in prompt
    assert "mandatory_retention_checklist" not in prompt
    assert "writer_model_context_v1" not in prompt
    assert "reader_brief_plan" not in prompt
    assert "decision_interpretation_plan" not in prompt
    assert "analytical_balance_contract" not in prompt
    assert "decision_boundary_source_contract" not in prompt
    assert "adaptive_memo_outline" not in prompt
    assert "Why This Read" not in prompt
    assert "Evidence Carrying the Conclusion" not in prompt
    assert "25%" in prompt
    assert '"source_id": "s2"' in prompt
    assert "Counter Study" not in prompt
    assert '"source_labels"' not in prompt


def test_warning_evidence_routes_through_canonical_prompt() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    decision_packet = built["decision_briefing_packet"]
    decision_packet["source_trail"].append(
        {"source_id": "s4", "source_label": "Equity Review", "source_url": "https://example.test/equity"}
    )
    decision_packet["coverage_report"]["truly_lost_decision_critical"] = [
        {
            "candidate_card_id": "ec_warning",
            "decision_role": "counterweight",
            "priority": 10,
            "source_ids": ["s4"],
            "claim": "Option A shifted flood risk toward downstream neighborhoods.",
            "quantity_values": ["3 neighborhoods"],
        }
    ]

    result = build_quality_synthesis_packet_bundle(decision_packet)
    packet = result["memo_ready_packet"]
    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert result["memo_warning_packet"]["critical_warning_count"] == 1
    assert packet["memo_warning_packet"]["warnings"][0]["source_labels"] == ["Equity Review"]
    assert "Option A shifted flood risk toward downstream neighborhoods" in prompt
    assert "canonical_decision_writer_packet_v1" in prompt
    assert "must_include_points" in prompt
    assert "section_retention_requirements" in prompt
    assert "mandatory_retention_checklist" not in prompt
    assert "adaptive_memo_outline" not in prompt
    assert "reader_brief_plan" not in prompt
    assert "decision_interpretation_plan" not in prompt
    assert "Required obligation ledger" not in prompt


def test_lightweight_writer_guidance_routes_through_canonical_prompt() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])
    packet = result["memo_ready_packet"]
    packet["lightweight_writer_guidance"] = {
        "schema_id": "lightweight_writer_guidance_v1",
        "overall_judgment": "Use observational evidence carefully.",
        "reader_guidance": [
            {
                "instruction": "Explain that the main source supports direction but not causal certainty.",
                "source_ids": ["s1"],
            }
        ],
        "evidence_quality_caveats": [
            {"caveat": "This source is indirect for implementation outcomes.", "source_ids": ["s1"]}
        ],
        "quantity_wording_risks": [
            {
                "risk": "Do not mix implementation failure rates with outcome rates.",
                "safe_wording": "Keep failure and outcome endpoints in separate clauses.",
            }
        ],
        "do_not_overstate": ["Do not state unconditional adoption."],
        "suggested_reader_flow": ["answer first, then source weighting"],
    }

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "lightweight_writer_guidance_v1" in prompt
    assert "This source is indirect for implementation outcomes." in prompt
    assert "Keep failure and outcome endpoints in separate clauses." in prompt
    assert "Do not state unconditional adoption." in prompt
