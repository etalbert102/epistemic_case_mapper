from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_final_polish_prompt,
    build_memo_ready_packet_repair_prompt,
)


def test_memo_ready_final_polish_prompt_projects_reader_source_labels_to_ids() -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "source_trail": [
            {
                "source_id": "s1",
                "source_label": "Deep Research Flood Sources Outcome Study 2025",
                "citation_label": "Outcome Study 2025",
            }
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "Option A reduced flood losses by 25%.",
                "source_label": "Outcome Study 2025",
                "source_labels": ["Deep Research Flood Sources Outcome Study 2025"],
                "quantities": [{"value": "25%"}],
            }
        ],
    }
    memo = "## Decision Brief\n\nOption A reduced flood losses by 25% (Outcome Study 2025)."

    prompt = build_memo_ready_final_polish_prompt(memo, packet)

    assert "s1" in prompt
    assert "Outcome Study 2025" not in prompt
    assert "Deep Research Flood Sources Outcome Study 2025" not in prompt


def test_memo_ready_repair_prompt_projects_reader_source_labels_to_ids() -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "source_trail": [{"source_id": "s1", "source_label": "Deep Research Flood Sources Outcome Study 2025"}],
    }
    retention_report = {
        "issues": [
            {
                "issue_type": "missing_memo_ready_item",
                "item": {
                    "reader_claim": "Option A reduced flood losses by 25%.",
                    "source_label": "Deep Research Flood Sources Outcome Study 2025",
                },
            }
        ]
    }
    memo = "## Decision Brief\n\nOption A reduced flood losses by 25% (Deep Research Flood Sources Outcome Study 2025)."

    prompt = build_memo_ready_packet_repair_prompt(memo, packet, retention_report)

    assert "source IDs" in prompt
    assert "s1" in prompt
    assert "Deep Research Flood Sources Outcome Study 2025" not in prompt
