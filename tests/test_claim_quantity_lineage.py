from __future__ import annotations

from epistemic_case_mapper.staged_semantic_pipeline import consolidate_claims_for_map


def test_claim_consolidation_preserves_claim_bound_quantities() -> None:
    claims = [
        {
            "claim_id": "demo_c001",
            "claim": "The intervention was not associated with worse cardiovascular outcomes.",
            "source_id": "doc_a",
            "source_span": "lines 1-1",
            "excerpt": "The intervention was not associated with worse cardiovascular outcomes.",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
            "claim_quantities": [
                {
                    "value": "RR 0.98",
                    "quantity_role": "effect_estimate",
                    "measures": "cardiovascular outcomes",
                    "local_interpretation": "Near-null relative risk.",
                    "source_quote": "The intervention was not associated with worse cardiovascular outcomes.",
                    "line_hint": "lines 1-1",
                    "retention_hint": "must_retain",
                }
            ],
        },
        {
            "claim_id": "demo_c002",
            "claim": "The intervention was not associated with worse cardiovascular outcomes in adults.",
            "source_id": "doc_b",
            "source_span": "lines 2-2",
            "excerpt": "The intervention was not associated with worse cardiovascular outcomes in adults.",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
            "quantity_values": ["95% CI 0.90 to 1.05"],
        },
    ]

    consolidated, report = consolidate_claims_for_map(claims)

    assert report["changed"] is True
    assert len(consolidated) == 1
    assert consolidated[0]["quantity_values"] == ["RR 0.98", "95% CI 0.90 to 1.05"]
    assert consolidated[0]["claim_quantities"][0]["quantity_role"] == "effect_estimate"
    assert consolidated[0]["claim_quantities"][0]["evidence_bundle_id"].startswith("bundle_")
    assert consolidated[0]["claim_quantities"][0]["assertion_bundles"][0]["source_ids"] == ["doc_a"]
    assert consolidated[0]["claim_quantities"][1]["assertion_bundles"][0]["source_ids"] == ["doc_b"]
