from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_direct_synthesis_comparison import (
    build_direct_source_synthesis_comparison_report,
)

from test_decision_briefing_packet import _scaffold


def test_direct_source_synthesis_comparison_scores_packet_and_baseline_retention() -> None:
    built = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    packet = built["decision_briefing_packet"]

    report = build_direct_source_synthesis_comparison_report(
        question=packet["decision_question"],
        packet=packet,
        briefing_text="Outcome Study reports 25% lower losses, but Counter Study warns about spillover harms.",
        baseline_text="Outcome Study discusses losses but drops the 25% estimate.",
        baseline_path="baseline.md",
    )

    assert report["schema_id"] == "direct_source_synthesis_comparison_report_v1"
    assert report["baseline_available"] is True
    assert report["anchor_inventory"]["quantity_count"] >= 1
    assert report["packet_memo_retention"]["quantity_mentions"] >= report["baseline_retention"]["quantity_mentions"]
    assert report["retention_delta_vs_baseline"]["quantity_mentions"] >= 0


def test_direct_source_synthesis_comparison_emits_prompt_without_baseline() -> None:
    built = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )

    report = build_direct_source_synthesis_comparison_report(
        question="Should the city adopt option A for flood protection?",
        packet=built["decision_briefing_packet"],
        briefing_text="Outcome Study reports 25% lower losses.",
    )

    assert report["status"] == "comparison_pending_baseline"
    assert "Decision question: Should the city adopt option A" in report["direct_source_baseline_prompt"]
    assert report["retention_delta_vs_baseline"]["status"] == "baseline_not_available"


def test_direct_source_synthesis_comparison_scores_memo_ready_packet_retention_and_prose() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "evidence_items": [
            {
                "item_id": "support",
                "role": "strongest_support",
                "must_use": True,
                "reader_claim": "Option A reduces losses.",
                "source_label": "Outcome Study",
                "quantities": [{"value": "25%", "interpretation": "loss reduction"}],
            }
        ],
    }

    report = build_direct_source_synthesis_comparison_report(
        question=packet["decision_question"],
        packet=packet,
        briefing_text="**Bottom Line:** Option A should be adopted because Outcome Study found Option A reduces losses by 25%.",
        baseline_text="Option A should be adopted because Outcome Study found lower losses.",
        baseline_path="baseline.md",
    )

    assert report["anchor_inventory"]["quantity_count"] == 1
    assert report["packet_memo_mandatory_retention"]["status"] == "ready"
    assert report["baseline_mandatory_retention"]["missing_quantity_count"] == 1
    assert report["mandatory_retention_delta_vs_baseline"]["missing_quantity_count"] == -1
    assert report["packet_memo_prose_diagnostics"]["bottom_line_present"] is True
