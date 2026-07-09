from __future__ import annotations

from epistemic_case_mapper.staged_semantic_pipeline import (
    SourceSpan,
    _candidate_relation_pairs,
    _normalize_claim_proposal,
    _relation_candidate_pool_report,
)


def test_relation_candidate_pool_prioritizes_calibrated_decision_importance() -> None:
    claims = [
        {
            "claim_id": f"background_{index:03d}",
            "claim": f"Background claim {index} mentions the topic but does not change the decision.",
            "source_id": f"doc_{index % 8}",
            "excerpt": f"Background topic mention {index}.",
            "role": "background",
            "question_relevance": "background",
            "decision_importance": {
                "calibrated_level": "low",
                "decision_function": "background_context",
                "default_use": "appendix",
            },
        }
        for index in range(24)
    ]
    claims.extend(
        [
            {
                "claim_id": "critical_outcome",
                "claim": "The intervention reduced the target outcome risk by 20 percent.",
                "source_id": "trial",
                "excerpt": "The intervention reduced the target outcome risk by 20 percent.",
                "role": "conclusion_support",
                "question_relevance": "direct",
                "decision_importance": {
                    "calibrated_level": "critical",
                    "decision_function": "answer_bearing",
                    "default_use": "main_map",
                },
            },
            {
                "claim_id": "critical_scope",
                "claim": "The effect only applies where the target population matches the study population.",
                "source_id": "review",
                "excerpt": "The effect only applies where the target population matches the study population.",
                "role": "scope_limit",
                "question_relevance": "scope_limit",
                "decision_importance": {
                    "calibrated_level": "critical",
                    "decision_function": "scope_boundary",
                    "default_use": "main_map",
                },
            },
        ]
    )

    pairs = _candidate_relation_pairs(claims, max_pairs=4)
    endpoint_ids = {packet[side]["claim_id"] for packet in pairs for side in ("left", "right")}
    report = _relation_candidate_pool_report(claims, pairs, requested_max_pairs=4, effective_max_pairs=4)
    pool_by_id = {row["claim_id"]: row for row in report["relation_pool_claims"]}

    assert {"critical_outcome", "critical_scope"} <= endpoint_ids
    assert pool_by_id["critical_outcome"]["decision_importance"] == "critical"
    assert pool_by_id["critical_scope"]["decision_function"] == "scope_boundary"


def test_normalize_claim_calibrates_overstated_background_importance() -> None:
    span = SourceSpan(
        span_id="demo_s0001",
        source_id="demo_source",
        source_span="lines 1-1",
        text="The source was published in 2021.",
    )

    accepted, reason = _normalize_claim_proposal(
        {
            "source_quote": "published in 2021",
            "claim": "The source was published in 2021.",
            "span_id": "demo_s0001",
            "entailed_by_excerpt": "yes",
            "role": "background",
            "question_relevance": "background",
            "scope_flags": ["none"],
            "decision_importance": "critical",
            "decision_function": "background_context",
            "default_use": "main_map",
        },
        {span.span_id: span},
    )

    assert reason == ""
    assert accepted is not None
    assert accepted["decision_importance"]["model_level"] == "critical"
    assert accepted["decision_importance"]["calibrated_level"] == "medium"
    assert accepted["default_use"] == "supporting_map"
