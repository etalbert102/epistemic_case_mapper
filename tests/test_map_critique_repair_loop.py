from __future__ import annotations

from epistemic_case_mapper.staged_semantic_map_repair_loop import build_map_critique, build_map_repair_plan


def test_map_critique_surfaces_label_warnings_and_missing_relation_candidates() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "case_c001",
                "claim": "The intervention improves the decision-relevant outcome.",
                "source_id": "doc_a",
                "source_span": "lines 1-1",
                "excerpt": "The intervention improves the decision-relevant outcome.",
                "role": "conclusion_support",
                "label_audit": {"synthesis_bucket": "core", "warnings": []},
            },
            {
                "claim_id": "case_c002",
                "claim": "The result only applies in a narrow target population.",
                "source_id": "doc_b",
                "source_span": "lines 1-1",
                "excerpt": "The result only applies in a narrow target population.",
                "role": "scope_limit",
                "label_audit": {
                    "synthesis_bucket": "supporting",
                    "warnings": ["model_main_map_demoted_by_audit"],
                },
            },
        ],
        "relations": [],
    }
    quality_report = {
        "issues": [{"severity": "risk", "issue_type": "missing_relations", "message": "No relations."}],
    }

    critique = build_map_critique(candidate_map, quality_report, [], [])
    plan = build_map_repair_plan(candidate_map, critique)

    categories = {finding["category"] for finding in critique["findings"]}
    assert "quality:missing_relations" in categories
    assert "label_audit_warning" in categories
    assert "missing_relation" in categories
    assert critique["repair_candidates"]["relation_pairs"]
    assert plan["relation_pairs"]
    assert plan["evidence_check_rows"]
    assert plan["crux_review_notes"]
