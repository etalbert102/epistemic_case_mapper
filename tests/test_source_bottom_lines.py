from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_source_bottom_lines import source_bottom_line_candidates


def test_source_bottom_line_role_uses_explicit_labels_not_keyword_fallback() -> None:
    scaffold = {
        "source_bottom_line_cards": {
            "cards": [
                {
                    "source_bottom_line_id": "sbl001",
                    "source_id": "src001",
                    "source_bottom_line": "This source discusses a counterexample but gives no explicit role label.",
                },
                {
                    "source_bottom_line_id": "sbl002",
                    "source_id": "src002",
                    "source_bottom_line": "This source is explicitly contrary.",
                    "decision_polarity": "challenges_current_answer",
                },
            ]
        }
    }

    rows = source_bottom_line_candidates(scaffold, 0)

    by_source = {row["source_ids"][0]: row for row in rows}
    assert by_source["src001"]["source_summary_decision_role"] == "context"
    assert by_source["src002"]["source_summary_decision_role"] == "counterweight"
