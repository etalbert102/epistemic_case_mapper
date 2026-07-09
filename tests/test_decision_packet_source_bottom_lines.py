from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_source_bottom_lines import build_source_bottom_line_cards

from tests.test_decision_briefing_packet import _scaffold


def test_packet_promotes_source_bottom_lines_as_first_class_evidence() -> None:
    scaffold = _scaffold()
    scaffold["source_bottom_line_cards"] = {
        "schema_id": "source_bottom_line_cards_v1",
        "cards": [
            {
                "source_bottom_line_id": "sbl0001",
                "source_id": "s1",
                "source_label": "Outcome Study",
                "claim_ids": ["c1"],
                "source_bottom_line": (
                    "Option A was not associated with higher downstream flood losses overall, "
                    "though the result may not apply when maintenance funding is cut."
                ),
                "decision_importance_level": "high",
                "decision_function": "answer_bearing",
            }
        ],
    }

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    bundles = result["decision_briefing_packet"]["evidence_bundles"]
    source_summary = [row for row in bundles if row.get("pretrim_kind") == "source_bottom_line"]

    assert source_summary
    assert source_summary[0]["decision_role"] == "strongest_support"
    assert "Source-level bottom line" in source_summary[0]["why_it_matters"]


def test_packet_reports_omitted_source_bottom_lines_after_trimming() -> None:
    scaffold = _scaffold()
    for index in range(12):
        source_id = f"sbl_source_{index}"
        scaffold["source_display_names"][source_id] = f"Source Bottom Line {index}"
    scaffold["source_bottom_line_cards"] = {
        "schema_id": "source_bottom_line_cards_v1",
        "cards": [
            {
                "source_bottom_line_id": f"sbl{index:04d}",
                "source_id": f"sbl_source_{index}",
                "source_label": f"Source Bottom Line {index}",
                "claim_ids": [f"sbl_claim_{index}"],
                "source_bottom_line": f"Option A was not associated with worse outcomes in source {index}.",
                "decision_importance_level": "high",
                "decision_function": "answer_bearing",
            }
            for index in range(12)
        ],
    }

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    coverage = result["decision_briefing_packet"]["coverage_report"]
    sufficiency = result["packet_sufficiency_report"]

    assert coverage["source_bottom_line_candidate_count"] == 12
    assert coverage["omitted_source_bottom_line_ids"]
    assert "source_bottom_lines_omitted_after_trimming" in coverage["warnings"]
    assert sufficiency["source_bottom_line_retention"]["missing_count"] >= 1
    assert "source_bottom_lines_missing" in sufficiency["issues"]


def test_source_bottom_line_cards_read_whole_doc_source_card_shape() -> None:
    scaffold = {"source_display_names": {"s1": "Guideline Source"}}
    prioritized_map = {
        "claims": [
            {
                "claim_id": "c1",
                "source_id": "s1",
                "decision_importance_level": "high",
                "whole_doc_source_card": {
                    "source_bottom_line": "Moderate use is acceptable in the population named by the source.",
                    "source_card_role": "main_finding",
                },
            }
        ]
    }

    cards = build_source_bottom_line_cards(prioritized_map, scaffold)

    assert cards["card_count"] == 1
    assert cards["cards"][0]["source_bottom_line"] == "Moderate use is acceptable in the population named by the source."
    assert cards["cards"][0]["decision_function"] == "main_finding"


def test_source_bottom_line_role_signals_cover_common_source_summary_language() -> None:
    scaffold = _scaffold()
    scaffold["source_bottom_line_cards"] = {
        "cards": [
            {
                "source_bottom_line_id": "sbl_support",
                "source_id": "s1",
                "source_bottom_line": "Moderate use is tolerable and not strongly linked to worse outcomes.",
                "decision_importance_level": "high",
            },
            {
                "source_bottom_line_id": "sbl_counter",
                "source_id": "s2",
                "source_bottom_line": "Longer exposure increases an intermediate risk marker, so restriction may be warranted.",
                "decision_importance_level": "high",
            },
        ]
    }

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    roles = {
        row["candidate_card_ids"][0]: row["decision_role"]
        for row in result["decision_briefing_packet"]["evidence_bundles"]
        if row.get("pretrim_kind") == "source_bottom_line"
    }

    assert roles["sbl_support"] == "strongest_support"
    assert roles["sbl_counter"] == "counterweight"
