from __future__ import annotations

import json
from pathlib import Path

from epistemic_case_mapper.model_backends import ModelBackendResult
from epistemic_case_mapper.pipeline.map.staged_semantic_claim_consolidation import consolidate_claims_with_vector_llm


def test_vector_llm_consolidation_merges_model_adjudicated_duplicates(tmp_path: Path) -> None:
    claims = [
        _claim("c001", "doc", "Healthy adults can include up to one egg per day.", "same excerpt"),
        _claim("c002", "doc", "Healthy people may include one egg daily.", "same excerpt"),
        _claim("c003", "doc", "The study was conducted in US cohorts.", "different excerpt", role="scope_limit"),
    ]

    consolidated, report = consolidate_claims_with_vector_llm(
        claims,
        backend="fake",
        artifact_dir=tmp_path,
        decision_question="Should adults treat eggs as harmful, neutral, or beneficial?",
        backend_timeout=1,
        backend_retries=0,
        run_backend=_merge_first_two_backend,
    )

    assert report["method"] == "vector_cluster_llm_adjudicated"
    assert len(consolidated) == 2
    merged = next(claim for claim in consolidated if claim.get("supporting_claim_ids"))
    assert merged["claim"] == "Healthy adults can include up to one egg per day."
    assert merged["supporting_claim_ids"] == ["c001", "c002"]
    assert (tmp_path / "claim_consolidation_clusters").exists()


def test_vector_llm_consolidation_rejects_model_overmerge_direction_conflict(tmp_path: Path) -> None:
    claims = [
        _claim("c001", "doc_a", "Egg intake was not associated with cardiovascular risk.", "excerpt a"),
        _claim("c002", "doc_b", "Higher egg intake was significantly associated with increased cardiovascular risk.", "excerpt b"),
    ]

    consolidated, report = consolidate_claims_with_vector_llm(
        claims,
        backend="fake",
        artifact_dir=tmp_path,
        decision_question="Should adults treat eggs as harmful, neutral, or beneficial?",
        backend_timeout=1,
        backend_retries=0,
        run_backend=_overmerge_backend,
    )

    assert len(consolidated) == 2
    assert report["changed"] is False
    assert not report["merged_groups"]


def test_vector_llm_consolidation_rejects_nonshared_numeric_canonical_claim(tmp_path: Path) -> None:
    claims = [
        _claim("c001", "doc", "The hazard ratio was 1.00 and not statistically significant.", "HR 1.00"),
        _claim("c002", "doc", "The hazard ratio was 1.03 and not statistically significant.", "HR 1.03"),
    ]

    consolidated, report = consolidate_claims_with_vector_llm(
        claims,
        backend="fake",
        artifact_dir=tmp_path,
        decision_question="Should adults treat eggs as harmful, neutral, or beneficial?",
        backend_timeout=1,
        backend_retries=0,
        run_backend=_over_specific_numeric_backend,
    )

    assert len(consolidated) == 2
    assert report["changed"] is False


def _merge_first_two_backend(*args, **kwargs) -> ModelBackendResult:
    del args, kwargs
    return ModelBackendResult(
        text=json.dumps(
            {
                "groups": [
                    {
                        "canonical_claim": "Healthy adults can include up to one egg per day.",
                        "member_claim_ids": ["c001", "c002"],
                        "rationale": "same source, role, and excerpt with equivalent wording",
                    }
                ],
                "preserve_claim_ids": ["c003"],
            }
        ),
        backend="fake",
    )


def _overmerge_backend(*args, **kwargs) -> ModelBackendResult:
    del args, kwargs
    return ModelBackendResult(
        text=json.dumps(
            {
                "groups": [
                    {
                        "canonical_claim": "Egg intake has one consolidated cardiovascular-risk finding.",
                        "member_claim_ids": ["c001", "c002"],
                        "rationale": "both discuss cardiovascular risk",
                    }
                ],
                "preserve_claim_ids": [],
            }
        ),
        backend="fake",
    )


def _over_specific_numeric_backend(*args, **kwargs) -> ModelBackendResult:
    del args, kwargs
    return ModelBackendResult(
        text=json.dumps(
            {
                "groups": [
                    {
                        "canonical_claim": "The hazard ratio was 1.00 and not statistically significant.",
                        "member_claim_ids": ["c001", "c002"],
                        "rationale": "both estimates are not statistically significant",
                    }
                ],
                "preserve_claim_ids": [],
            }
        ),
        backend="fake",
    )


def _claim(claim_id: str, source_id: str, claim: str, excerpt: str, *, role: str = "conclusion_support") -> dict:
    return {
        "claim_id": claim_id,
        "source_id": source_id,
        "source_span": "lines 1-1",
        "excerpt": excerpt,
        "claim": claim,
        "role": role,
        "entailed_by_excerpt": "yes",
    }
