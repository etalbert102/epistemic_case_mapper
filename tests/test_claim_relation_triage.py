from __future__ import annotations

from epistemic_case_mapper.staged_semantic_claim_triage import triage_claims_for_relation_building


def _claim(
    claim_id: str,
    *,
    relevance: str,
    importance: str,
    default_use: str,
    bucket: str,
    routing_use: str,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "source_id": f"source_{claim_id}",
        "claim": f"Claim {claim_id}",
        "question_relevance": relevance,
        "decision_importance_level": importance,
        "default_use": default_use,
        "validation_warnings": warnings or [],
        "label_audit": {
            "synthesis_bucket": bucket,
            "routing_default_use": routing_use,
            "warnings": warnings or [],
        },
    }


def test_claim_relation_triage_preserves_claims_but_filters_off_question_appendix() -> None:
    claims = [
        _claim("core", relevance="direct", importance="high", default_use="main_map", bucket="core", routing_use="main_map"),
        _claim("support", relevance="indirect", importance="medium", default_use="supporting_map", bucket="supporting", routing_use="supporting_map"),
        _claim(
            "off_question",
            relevance="low",
            importance="low",
            default_use="appendix",
            bucket="appendix",
            routing_use="appendix",
            warnings=["question_outcome_mismatch"],
        ),
    ]

    triaged, eligible, report = triage_claims_for_relation_building(claims)

    assert [claim["claim_id"] for claim in triaged] == ["core", "support", "off_question"]
    assert [claim["claim_id"] for claim in eligible] == ["core", "support"]
    assert report["bucket_counts"] == {"core": 1, "excluded_from_relation_building": 1, "supporting": 1}
    assert report["excluded_claim_count"] == 1
    assert triaged[2]["relation_building_eligible"] is False
    assert "question_mismatch:question_outcome_mismatch" in triaged[2]["relation_triage_reasons"]


def test_claim_relation_triage_uses_floor_without_deleting_appendix_claims() -> None:
    claims = [
        _claim("core", relevance="direct", importance="high", default_use="main_map", bucket="core", routing_use="main_map"),
        _claim(
            "appendix",
            relevance="low",
            importance="low",
            default_use="appendix",
            bucket="appendix",
            routing_use="appendix",
            warnings=["question_scope_mismatch"],
        ),
    ]

    triaged, eligible, report = triage_claims_for_relation_building(claims)

    assert len(triaged) == 2
    assert len(eligible) == 2
    assert report["fallback_used"] is True
    assert report["fallback_claim_ids"] == ["appendix"]
    assert triaged[1]["relation_triage_bucket"] == "excluded_from_relation_building"
    assert triaged[1]["relation_building_eligible"] is True
