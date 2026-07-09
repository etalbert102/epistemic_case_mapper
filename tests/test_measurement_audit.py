from __future__ import annotations

from epistemic_case_mapper.map_briefing_measurement_audit import (
    build_final_source_lineage_report,
    build_pipeline_measurement_audit,
    build_scoped_metric_report,
)
from epistemic_case_mapper.map_briefing_packet_retention import build_memo_packet_retention_report


def test_packet_retention_normalizes_numeric_terms_and_reports_match_method() -> None:
    packet = {
        "must_retain_ledger": [
            {
                "item_id": "retain_1",
                "importance": "critical",
                "omission_policy": "must_include",
                "statement": "The pooled estimate was below one in the main comparison.",
                "required_terms": ["RR = 0.84"],
                "source_ids": ["study_a"],
            }
        ],
        "evidence_bundles": [],
        "source_trail": [{"source_id": "study_a", "source_label": "Study A", "display_label": "Trial Report"}],
    }
    memo = "The main comparison reported RR=0.84 in Study A, so the pooled estimate was below one."

    report = build_memo_packet_retention_report(memo, packet)

    assert report["status"] == "ready"
    match = report["retained_items"][0]["required_term_matches"][0]
    assert match["retained"] is True
    assert match["match_method"] == "normalized_text"


def test_source_lineage_flags_sources_list_that_exceeds_packet_sources() -> None:
    scaffold = {
        "decision_briefing_packet": {
            "source_trail": [
                {
                    "source_id": "study_a",
                    "source_label": "Study A",
                    "display_label": "Trial Report",
                    "source_url": "https://example.test/study-a",
                    "appears_in_packet": True,
                }
            ]
        }
    }
    memo = """
## Decision Brief

Use option A.

## Sources

- [Trial Report](https://example.test/study-a)
- [Unused Background](https://example.test/unused)
"""

    report = build_final_source_lineage_report(memo, scaffold)

    assert report["status"] == "warning"
    assert report["matched_packet_source_count"] == 1
    assert report["unused_memo_source_count"] == 1
    assert report["unused_memo_sources"][0]["source_label"] == "Unused Background"


def test_source_lineage_treats_known_nonpacket_sources_as_unused() -> None:
    scaffold = {
        "decision_briefing_packet": {
            "source_trail": [
                {
                    "source_id": "study_a",
                    "source_label": "Study A",
                    "display_label": "Trial Report",
                    "source_url": "https://example.test/study-a",
                    "appears_in_packet": True,
                },
                {
                    "source_id": "background_b",
                    "source_label": "Background B",
                    "display_label": "Background Report",
                    "source_url": "https://example.test/background-b",
                    "appears_in_packet": False,
                },
            ]
        }
    }
    memo = """
## Sources

- [Trial Report](https://example.test/study-a)
- [Background Report](https://example.test/background-b)
"""

    report = build_final_source_lineage_report(memo, scaffold)

    assert report["matched_packet_source_count"] == 1
    assert report["unused_memo_source_count"] == 1
    assert report["unused_memo_sources"][0]["packet_match_status"] == "known_source_not_in_packet"


def test_measurement_audit_combines_scoped_metrics_and_noncomputable_warnings() -> None:
    scaffold = {
        "input_map_scope_counts": {"claim_count": 10, "relation_count": 5},
        "source_evidence_cards": {"source_card_count": 4, "anchored_card_count": 4},
        "decision_briefing_packet": {"evidence_bundles": [{}, {}], "must_retain_ledger": [{}]},
    }
    scoped = build_scoped_metric_report(
        scaffold=scaffold,
        prioritized_map={"claims": [{}, {}, {}], "relations": [{}]},
        runtime_budget_report={"model_call_count": 2},
        packet_retention_report={"retained_must_retain_count": 1},
    )
    audit = build_pipeline_measurement_audit(
        scoped_metric_report=scoped,
        source_lineage_report={"unused_memo_source_count": 1, "missing_packet_source_count": 0},
        relation_value_report={"connectivity_status": "not_computable_missing_endpoint_ids", "missing_endpoint_relation_count": 1},
        packet_retention_report={"retained_items": []},
        runtime_budget_report={"scope": "late_briefing_stages_only"},
        section_role_quality_report={"status": "warning", "issue_count": 2},
    )

    assert "claim_count" in scoped["ambiguous_metric_names"]
    issue_types = {issue["issue_type"] for issue in audit["issues"]}
    assert "metric_has_multiple_scopes" in issue_types
    assert "section_role_quality_warnings_present" in issue_types
    assert "relation_connectivity_not_computable" in issue_types
    assert "memo_sources_include_sources_not_in_packet" in issue_types
