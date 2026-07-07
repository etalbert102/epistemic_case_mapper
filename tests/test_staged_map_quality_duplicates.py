from __future__ import annotations

from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.staged_semantic_pipeline import evaluate_staged_map_quality


def test_staged_map_quality_does_not_call_opposite_direction_claims_duplicates() -> None:
    case_manifest = CaseManifest.model_validate(
        {
            "case_id": "demo",
            "title": "Demo",
            "question": "What matters?",
            "case_type": "test",
            "sources": [
                {"source_id": "doc_a", "title": "A", "text": "Higher risk evidence."},
                {"source_id": "doc_b", "title": "B", "text": "Lower risk evidence."},
            ],
        }
    )
    candidate_map = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "Daily egg consumption is associated with a higher risk of cardiovascular disease.",
                "source_id": "doc_a",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "demo_c002",
                "claim": "Daily egg consumption is associated with a lower risk of cardiovascular disease.",
                "source_id": "doc_b",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
        ],
        "relations": [],
    }

    report = evaluate_staged_map_quality(
        manifest=_Manifest(),
        region=_Region(),
        case_manifest=case_manifest,
        all_chunks=[],
        selected_chunks=[],
        skipped_chunks=[],
        candidate_map=candidate_map,
        rejected_claims=[],
        rejected_relations=[],
    )

    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert "near_duplicate_claims" not in issue_types
    assert "lexically_similar_opposite_direction_claims" in issue_types


def test_staged_map_quality_does_not_call_mixed_direction_claim_duplicate() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "Whole egg consumption is associated with higher cardiovascular mortality, while egg white consumption is associated with lower mortality.",
                "source_id": "doc_a",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "demo_c002",
                "claim": "Daily egg consumption is associated with a lower risk of cardiovascular disease.",
                "source_id": "doc_b",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
        ],
        "relations": [],
    }

    report = evaluate_staged_map_quality(
        manifest=_Manifest(),
        region=_Region(),
        case_manifest=_case_manifest(),
        all_chunks=[],
        selected_chunks=[],
        skipped_chunks=[],
        candidate_map=candidate_map,
        rejected_claims=[],
        rejected_relations=[],
    )

    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert "near_duplicate_claims" not in issue_types


class _Thresholds:
    min_claims = 2
    max_claims = 8
    min_relation_types = 1


class _Region:
    required_sources = []
    thresholds = _Thresholds()


class _Ontology:
    def permitted_types(self) -> set[str]:
        return {"supports", "in_tension_with"}


class _Manifest:
    relation_ontology = _Ontology()


def _case_manifest() -> CaseManifest:
    return CaseManifest.model_validate(
        {
            "case_id": "demo",
            "title": "Demo",
            "question": "What matters?",
            "case_type": "test",
            "sources": [
                {"source_id": "doc_a", "title": "A", "text": "Higher risk evidence."},
                {"source_id": "doc_b", "title": "B", "text": "Lower risk evidence."},
            ],
        }
    )
