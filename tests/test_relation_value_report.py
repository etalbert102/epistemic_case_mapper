from __future__ import annotations

from epistemic_case_mapper.map_briefing_relation_value import build_relation_value_report


def test_relation_value_report_accepts_grounded_decision_relevant_relations() -> None:
    report = build_relation_value_report(
        {
            "claims": [{"claim_id": f"c{i}"} for i in range(1, 7)],
            "relations": [
                {
                    "source_claim_id": "c1",
                    "target_claim_id": "c2",
                    "relation_type": "supports",
                    "rationale": "The first estimate supports the second because both describe the same decision-relevant outcome.",
                },
                {
                    "source_claim_id": "c3",
                    "target_claim_id": "c4",
                    "relation_type": "challenges",
                    "rationale": "The subgroup result challenges the general estimate by showing an important boundary condition.",
                },
                {
                    "source_claim_id": "c5",
                    "target_claim_id": "c6",
                    "relation_type": "crux_for",
                    "rationale": "This uncertainty is crux-like because resolving it would change the decision recommendation.",
                },
            ],
        }
    )

    assert report["schema_id"] == "relation_value_report_v1"
    assert report["status"] == "useful"
    assert report["valuable_relation_fraction"] == 1.0
    assert report["grounded_relation_fraction"] == 1.0


def test_relation_value_report_flags_sparse_generic_maps() -> None:
    report = build_relation_value_report(
        {
            "claims": [{"claim_id": f"c{i}"} for i in range(1, 30)],
            "relations": [
                {"source_claim_id": "c1", "target_claim_id": "c2", "relation_type": "similar_to", "rationale": "Similar."},
                {"source_claim_id": "c3", "target_claim_id": "c4", "relation_type": "similar_to"},
            ],
        }
    )

    assert report["status"] == "warning"
    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert "sparse_relation_graph" in issue_types
    assert "low_value_relation_type_dominance" in issue_types


def test_relation_value_report_marks_connectivity_not_computable_without_endpoint_ids() -> None:
    report = build_relation_value_report(
        {
            "claims": [{"claim_id": "c1"}, {"claim_id": "c2"}],
            "relations": [
                {
                    "source_claim": "One claim text",
                    "target_claim": "Another claim text",
                    "relation_type": "supports",
                    "rationale": "The first claim supports the second by sharing the same decision-relevant finding.",
                }
            ],
        }
    )

    assert report["connectivity_status"] == "not_computable_missing_endpoint_ids"
    assert report["missing_endpoint_relation_count"] == 1
    assert any(issue["issue_type"] == "relation_connectivity_not_computable" for issue in report["issues"])


def test_relation_value_report_accepts_source_claim_endpoint_ids_when_known() -> None:
    report = build_relation_value_report(
        {
            "claims": [{"claim_id": "c1"}, {"claim_id": "c2"}],
            "relations": [
                {
                    "source_claim": "c1",
                    "target_claim": "c2",
                    "relation_type": "supports",
                    "rationale": "The first claim supports the second because they describe the same decision-relevant mechanism.",
                }
            ],
        }
    )

    assert report["connectivity_status"] == "computed"
    assert report["missing_endpoint_relation_count"] == 0
    assert report["connected_claim_count"] == 2
