from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.staged_semantic_pipeline import (
    SourceSpan,
    _batches,
    _candidate_relation_pairs,
    _concept_backfill_rejection_reason,
    _load_context,
    _normalize_claim_proposal,
    _non_evidence_text_reason,
    _parse_relation_model_json,
    _relation_candidate_pool_report,
    _relation_claim_card,
    _relation_pair_prompt,
    _relation_pair_block,
    _relation_pair_budget,
)
from epistemic_case_mapper.pipeline.map.staged_semantic_relation_candidates import _relation_endpoint_rejection_reason
from epistemic_case_mapper.pipeline.map.staged_semantic_relation_quality import relation_pair_intent


def test_candidate_relation_pairs_prioritize_decision_role_templates_without_shared_terms() -> None:
    claims = [
        {
            "claim_id": "demo_c001",
            "claim": "Portable filtration improves classroom respiratory outcomes.",
            "source_id": "doc_a",
            "excerpt": "The intervention improved outcomes in monitored classrooms.",
            "role": "conclusion_support",
        },
        {
            "claim_id": "demo_c002",
            "claim": "Benefits only apply where devices are maintained and correctly sized.",
            "source_id": "doc_b",
            "excerpt": "Effects depend on maintenance and correct sizing.",
            "role": "scope_limit",
        },
        {
            "claim_id": "demo_c003",
            "claim": "The appendix lists procurement dates.",
            "source_id": "doc_c",
            "excerpt": "Procurement dates were archived.",
            "role": "background",
        },
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=1)

    assert [(pairs[0]["left"]["claim_id"], pairs[0]["right"]["claim_id"])] == [("demo_c001", "demo_c002")]
    assert "scope_limit_bounds_decision_claim" in pairs[0]["candidate_reason"]


def test_relation_candidate_pool_prefers_canonical_claims_with_source_role_coverage() -> None:
    claims = [
        {
            "claim_id": "doc_a_raw_001",
            "claim": f"Raw same-source finding {index} says the intervention had a neutral effect on the target outcome.",
            "source_id": "doc_a",
            "excerpt": f"Raw same-source finding {index}.",
            "role": "conclusion_support",
        }
        for index in range(18)
    ]
    claims.extend(
        [
            {
                "claim_id": "doc_a_canonical",
                "claim": "The best canonical finding says the intervention had a neutral effect on the target outcome.",
                "source_id": "doc_a",
                "excerpt": "The best canonical finding says neutral effect.",
                "role": "conclusion_support",
                "supporting_claim_ids": ["doc_a_raw_001", "doc_a_raw_002", "doc_a_raw_003", "doc_a_raw_004"],
                "consolidation_method": "vector_cluster_llm_adjudicated",
            },
            {
                "claim_id": "doc_b_scope",
                "claim": "The neutral finding only applies where the study population matches the decision population.",
                "source_id": "doc_b",
                "excerpt": "Only applies where populations match.",
                "role": "scope_limit",
            },
            {
                "claim_id": "doc_c_crux",
                "claim": "The decision changes if the neutral effect disappears in the target subgroup.",
                "source_id": "doc_c",
                "excerpt": "Decision changes in the target subgroup.",
                "role": "crux",
            },
        ]
    )

    pairs = _candidate_relation_pairs(claims, max_pairs=6)
    endpoint_ids = {packet[side]["claim_id"] for packet in pairs for side in ("left", "right")}
    report = _relation_candidate_pool_report(claims, pairs, requested_max_pairs=6, effective_max_pairs=6)
    pool_ids = {row["claim_id"] for row in report["relation_pool_claims"]}

    assert "doc_a_canonical" in endpoint_ids
    assert "doc_c_crux" in endpoint_ids
    assert "doc_b_scope" in pool_ids

def test_relation_candidate_pool_report_records_pool_and_skipped_claims() -> None:
    claims = [
        {
            "claim_id": f"c{index:03d}",
            "claim": f"Claim {index} reports an association with the decision-relevant outcome.",
            "source_id": f"doc_{index % 6}",
            "excerpt": f"Claim {index} excerpt.",
            "role": "conclusion_support" if index % 2 else "scope_limit",
        }
        for index in range(70)
    ]
    pairs = _candidate_relation_pairs(claims, max_pairs=12)
    report = _relation_candidate_pool_report(claims, pairs, requested_max_pairs=12, effective_max_pairs=12)

    assert report["relation_pool_count"] <= report["relation_pool_limit"]
    assert report["skipped_relation_pool_count"] > 0
    assert report["relation_pool_claims"]
    assert report["skipped_relation_pool_examples"]

def test_prompt_builders_honor_explicit_decision_question_override() -> None:
    manifest, region, case_manifest = _load_context(Path("."), "submission_manifest.yaml", "eggs_observational_vs_rct")
    override = "Should generally healthy adults treat eggs as harmful, neutral, or beneficial for cardiovascular risk?"
    packet = {
        "pair_id": "pair_001",
        "left": {
            "claim_id": "demo_c001",
            "claim": "Egg intake was not associated with higher cardiovascular risk.",
            "source_id": "doc_a",
            "role": "conclusion_support",
            "decision_edge_role": "outcome_finding",
            "decision_edge_role_confidence": "high",
            "decision_edge_role_source": "model",
            "decision_edge_role_reasons": ["Directly answers the cardiovascular-risk question."],
            "decision_function": "answer_bearing",
            "question_relevance": "direct",
            "decision_importance_level": "critical",
            "source_alignment": {"source_quote": "not associated with higher cardiovascular risk"},
        },
        "right": {
            "claim_id": "demo_c002",
            "claim": "The cohort design limits causal interpretation.",
            "source_id": "doc_b",
            "role": "scope_limit",
            "decision_edge_role": "method_or_validity_limit",
            "decision_edge_role_confidence": "medium",
            "decision_edge_role_source": "model",
            "decision_edge_role_reasons": ["Limits the strength of causal use."],
            "decision_function": "source_quality_caveat",
            "question_relevance": "direct",
            "decision_importance_level": "high",
            "source_alignment": {"source_quote": "cohort design limits causal interpretation"},
        },
        "pair_intent": {"intent": "cross_source_general_scope_to_finding", "allowed_relation_types": ["refines", "none"]},
    }

    relation_prompt = _relation_pair_prompt(manifest, region, case_manifest, packet, decision_question=override)

    assert f"Decision question: {override}" in relation_prompt
    assert "# Relation Type Semantics" in relation_prompt
    assert "depends_on: The force of one claim depends on a condition" in relation_prompt
    assert "contextualizes: One claim supplies interpretation context" in relation_prompt
    assert "suggested_relation_types as the default decision menu" in relation_prompt
    assert "selection_rule: First try to choose the strongest relation from suggested_relation_types" in relation_prompt
    assert "Use contextualizes when a claim helps interpret another claim" in relation_prompt
    assert '"decision_edge_role": "outcome_finding"' in relation_prompt
    assert '"decision_edge_role": "method_or_validity_limit"' in relation_prompt
    assert "exact evidence quotes carry the evidence for an edge" in relation_prompt

def test_normalize_claim_preserves_relevance_metadata_and_rejects_irrelevant() -> None:
    span = SourceSpan(
        span_id="demo_s0001",
        source_id="demo_source",
        source_span="lines 1-1",
        text="The intervention changed the decision-relevant outcome.",
    )
    span_lookup = {span.span_id: span}

    accepted, reason = _normalize_claim_proposal(
        {
            "source_quote": "intervention changed the decision-relevant outcome",
            "claim": "The intervention changed the decision-relevant outcome.",
            "span_id": "demo_s0001",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
            "question_relevance": "direct",
            "relevance_rationale": "It reports the target outcome.",
            "scope_flags": ["none"],
            "decision_importance": "critical",
            "decision_function": "answer_bearing",
            "default_use": "main_map",
            "importance_rationale": "It directly bears on the decision answer.",
        },
        span_lookup,
    )
    rejected, rejected_reason = _normalize_claim_proposal(
        {
            "source_quote": "intervention changed the decision-relevant outcome",
            "claim": "The page contains unrelated metadata.",
            "span_id": "demo_s0001",
            "entailed_by_excerpt": "yes",
            "role": "background",
            "question_relevance": "irrelevant",
            "scope_flags": ["administrative_context"],
        },
        span_lookup,
    )

    assert reason == ""
    assert accepted is not None
    assert accepted["role"] == "source_claim"
    assert "legacy_extraction_role" not in accepted
    assert accepted["question_relevance"] == "direct"
    assert accepted["question_fit"]["status"] == "match"
    assert accepted["scope_flags"] == ["none"]
    assert accepted["decision_importance"]["model_level"] == "critical"
    assert accepted["decision_importance"]["calibrated_level"] in {"critical", "high"}
    assert accepted["decision_function"] == "answer_bearing"
    assert accepted["default_use"] == "main_map"
    assert accepted["source_alignment"]["status"] == "exact_match"
    assert accepted["source_quote"] == "intervention changed the decision-relevant outcome"
    assert rejected is None
    assert rejected_reason == "question_irrelevant"

def test_normalize_claim_uses_source_quote_to_override_wrong_span_id() -> None:
    span_a = SourceSpan(
        span_id="demo_s0001",
        source_id="demo_source",
        source_span="lines 1-1",
        text="Administrative heading only.",
    )
    span_b = SourceSpan(
        span_id="demo_s0002",
        source_id="demo_source",
        source_span="lines 2-2",
        text="The intervention reduced the decision-relevant risk by 20 percent.",
    )

    claim, reason = _normalize_claim_proposal(
        {
            "source_quote": "reduced the decision-relevant risk by 20 percent",
            "claim": "The intervention reduced the decision-relevant risk by 20 percent.",
            "span_id": "demo_s0001",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
            "question_relevance": "direct",
            "scope_flags": ["none"],
        },
        {span_a.span_id: span_a, span_b.span_id: span_b},
    )

    assert reason == ""
    assert claim is not None
    assert claim["source_span"] == "lines 2-2"
    assert claim["source_alignment"]["status"] == "exact_match_span_id_overridden"
    assert claim["source_alignment"]["proposed_span_id"] == "demo_s0001"
    assert claim["source_alignment"]["resolved_span_id"] == "demo_s0002"

def test_normalize_claim_rejects_unaligned_source_quote() -> None:
    span = SourceSpan(
        span_id="demo_s0001",
        source_id="demo_source",
        source_span="lines 1-1",
        text="The source discusses a different topic.",
    )

    claim, reason = _normalize_claim_proposal(
        {
            "source_quote": "not actually present in this chunk",
            "claim": "A claim that is not grounded here.",
            "span_id": "demo_s0001",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
        },
        {span.span_id: span},
    )

    assert claim is None
    assert reason == "source_quote_unaligned"


def test_normalize_claim_rejects_non_yes_entailment_without_promotion() -> None:
    span = SourceSpan(
        span_id="demo_s0001",
        source_id="demo_source",
        source_span="lines 1-1",
        text="The intervention was associated with lower mortality.",
    )

    claim, reason = _normalize_claim_proposal(
        {
            "source_quote": "The intervention was associated with lower mortality.",
            "claim": "The intervention was associated with lower mortality.",
            "span_id": "demo_s0001",
            "entailed_by_excerpt": "uncertain",
            "question_relevance": "direct",
        },
        {span.span_id: span},
    )

    assert claim is None
    assert reason == "claim_not_entailed_by_excerpt"


def test_normalize_claim_accepts_quote_aligned_to_local_span_window() -> None:
    spans = {
        "demo_s0001": SourceSpan(
            span_id="demo_s0001",
            source_id="demo_source",
            source_span="lines 1-1",
            text="The relevant argument starts before the model selected line.",
        ),
        "demo_s0002": SourceSpan(
            span_id="demo_s0002",
            source_id="demo_source",
            source_span="lines 2-2",
            text="The source says high-energy comparisons matter for the decision.",
        ),
        "demo_s0003": SourceSpan(
            span_id="demo_s0003",
            source_id="demo_source",
            source_span="lines 3-3",
            text="It adds that adjacent source lines often carry the full quoted point.",
        ),
    }

    claim, reason = _normalize_claim_proposal(
        {
            "source_quote": "high-energy comparisons matter for the decision and adjacent source lines often carry the full quoted point",
            "claim": "The high-energy comparison is a local evidence point.",
            "span_id": "demo_s0002",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
            "question_relevance": "direct",
        },
        spans,
    )

    assert reason == ""
    assert claim is not None
    assert claim["source_alignment"]["method"] == "local_window_token_overlap"
    assert claim["source_alignment"]["resolved_span_id"] == "demo_s0002"


def test_candidate_relation_pairs_use_graph_diversity_to_cover_more_claims() -> None:
    claims = [
        _claim("demo_c001", "Primary intervention improves outcomes.", "a", "improves outcomes", "conclusion_support"),
        _claim("demo_c002", "Primary intervention has a scope boundary.", "b", "scope boundary", "scope_limit"),
        _claim("demo_c003", "Secondary pathway improves outcomes.", "c", "improves outcomes", "conclusion_support"),
        _claim("demo_c004", "Secondary pathway depends on maintenance.", "d", "depends on maintenance", "scope_limit"),
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=2)
    covered = {
        claim_id
        for pair in pairs
        for claim_id in (pair["left"]["claim_id"], pair["right"]["claim_id"])
    }

    assert len(covered) == 4
    assert all("scope_limit_bounds_decision_claim" in pair["candidate_reason"] for pair in pairs)


def test_candidate_relation_pairs_include_tfidf_semantic_similarity_reason() -> None:
    claims = [
        _claim("demo_c001", "Ventilation filtration lowers particle exposure.", "a", "filtration lowers particles", "background"),
        _claim("demo_c002", "Air cleaning filtration reduces particle concentration.", "b", "filtration reduces particles", "background"),
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=1)

    assert pairs
    assert "tfidf_semantic_similarity" in pairs[0]["candidate_reason"]


def test_candidate_relation_pairs_filter_non_substantive_claims() -> None:
    claims = [
        _claim("demo_c001", "Primary intervention improves outcomes for the target population.", "a", "improves outcomes", "conclusion_support"),
        _claim("demo_c002", "Benefits only apply where implementation capacity is maintained.", "b", "depends on capacity", "scope_limit"),
        _claim("demo_c003", "Education level, No. (%)", "c", "Education level, No. (%)", "conclusion_support"),
        _claim("demo_c004", "Guidance/recommendation evidence: Privacy Policy", "d", "Privacy Policy", "implementation_constraint"),
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=5)
    selected_ids = {pair[side]["claim_id"] for pair in pairs for side in ("left", "right")}

    assert pairs
    assert selected_ids == {"demo_c001", "demo_c002"}

def test_candidate_relation_pairs_filter_title_markup_and_appendix_endpoints() -> None:
    claims = [
        _claim("demo_c001", "Primary intervention improves outcomes for the target population.", "a", "improves outcomes", "conclusion_support"),
        _claim("demo_c002", "Benefits only apply where implementation capacity is maintained.", "b", "depends on capacity", "scope_limit"),
        _claim(
            "demo_c003",
            "Dietary Cholesterol and Cardiovascular Risk: A Science Advisory From a Professional Society",
            "c",
            "Dietary Cholesterol and Cardiovascular Risk: A Science Advisory From a Professional Society",
            "scope_limit",
        ),
        _claim("demo_c004", ".cls-11 { fill: none; stroke: #000; }", "d", ".cls-11 { fill: none; }", "background"),
        {
            **_claim("demo_c005", "Child-only evidence applies to toddlers rather than the adult target population.", "e", "toddlers", "conclusion_support"),
            "appendix_only": True,
        },
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=5)
    selected_ids = {pair[side]["claim_id"] for pair in pairs for side in ("left", "right")}
    report = _relation_candidate_pool_report(claims, pairs, requested_max_pairs=5, effective_max_pairs=5)

    assert selected_ids == {"demo_c001", "demo_c002"}
    assert report["rejected_endpoint_reason_counts"]["title_or_heading"] == 1
    assert report["rejected_endpoint_reason_counts"]["css_or_markup"] == 1
    assert report["rejected_endpoint_reason_counts"]["appendix_only"] == 1

def test_relation_pair_budget_scales_for_large_claim_sets_but_respects_small_explicit_caps() -> None:
    small = [
        _claim("demo_c001", "Primary intervention improves outcomes.", "a", "improves outcomes", "conclusion_support"),
        _claim("demo_c002", "Primary intervention has a scope boundary.", "b", "scope boundary", "scope_limit"),
    ]
    large = [
        _claim(f"demo_c{index:03d}", f"Claim {index} reports an effect on the decision relevant outcome.", f"source_{index % 8}", "reports effect", "conclusion_support")
        for index in range(1, 80)
    ]

    assert _relation_pair_budget(small, 1) == 1
    assert _relation_pair_budget(large, 12) > 12
    assert _relation_pair_budget(large, 12) <= 48

def test_candidate_relation_pairs_penalize_population_scope_mismatch() -> None:
    claims = [
        _claim(
            "demo_c001",
            "For toddlers, early exposure to the food may reduce later allergy risk.",
            "pediatric_guidance",
            "toddlers reduce allergy risk",
            "conclusion_support",
        ),
        _claim(
            "demo_c002",
            "In adults, the exposure increased a lipid biomarker without measuring clinical events.",
            "adult_trial",
            "adults increased lipid biomarker",
            "conclusion_support",
        ),
        _claim(
            "demo_c003",
            "Adult cohort evidence found no increase in cardiovascular events.",
            "adult_cohort",
            "adult cardiovascular events",
            "conclusion_support",
        ),
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=1)
    selected_ids = {pairs[0][side]["claim_id"] for side in ("left", "right")}

    assert selected_ids == {"demo_c002", "demo_c003"}


def test_candidate_relation_pairs_exclude_cross_source_study_scope_to_finding() -> None:
    claims = [
        _claim(
            "demo_c001",
            "The trial enrolled patients with prior cardiovascular events at baseline.",
            "trial_a",
            "patients with prior cardiovascular events at baseline",
            "scope_limit",
        ),
        _claim(
            "demo_c002",
            "A separate meta-analysis found egg intake was not associated with cardiovascular disease.",
            "meta_b",
            "egg intake was not associated with cardiovascular disease",
            "conclusion_support",
        ),
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=5)

    assert pairs == []
    assert relation_pair_intent(claims[0], claims[1]) == {
        "intent": "cross_source_study_scope_to_finding",
        "allowed_relation_types": ["none"],
    }


def test_candidate_relation_pairs_exclude_cross_source_study_scope_to_crux() -> None:
    claims = [
        _claim(
            "demo_c001",
            "The trial enrolled patients with prior cardiovascular events at baseline.",
            "trial_a",
            "patients with prior cardiovascular events at baseline",
            "scope_limit",
        ),
        _claim(
            "demo_c002",
            "The decision turns on whether egg intake changes cardiovascular event risk.",
            "meta_b",
            "turns on cardiovascular event risk",
            "crux",
        ),
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=5)

    assert pairs == []
    assert relation_pair_intent(claims[0], claims[1]) == {
        "intent": "cross_source_study_scope_to_finding",
        "allowed_relation_types": ["none"],
    }


def test_candidate_relation_pairs_keep_same_source_scope_to_finding() -> None:
    claims = [
        _claim(
            "demo_c001",
            "The cohort enrolled adults without prior cardiovascular disease.",
            "cohort_a",
            "adults without prior cardiovascular disease",
            "scope_limit",
        ),
        _claim(
            "demo_c002",
            "The cohort found egg intake was not associated with cardiovascular disease events.",
            "cohort_a",
            "egg intake was not associated with cardiovascular disease events",
            "conclusion_support",
        ),
    ]

    pairs = _candidate_relation_pairs(claims, max_pairs=5)

    assert pairs
    assert pairs[0]["pair_intent"] == {
        "intent": "same_source_scope_to_finding",
        "allowed_relation_types": ["refines", "depends_on", "none"],
    }


def test_relation_endpoint_rejects_keyword_index_scope_claims() -> None:
    claim = {
        **_claim(
            "demo_c001",
            "The research involves cardiovascular outcomes, exposure, policy, and humans.",
            "indexed_source",
            "Outcomes; Exposure; Policy; Humans; Risk Factors",
            "scope_limit",
        ),
        "source_quote": "Outcomes; Exposure; Policy; Humans; Risk Factors",
    }

    assert _relation_endpoint_rejection_reason(claim) == "keyword_index_scope"


def test_non_evidence_classifier_rejects_footer_policy_and_index_terms() -> None:
    assert _non_evidence_text_reason("Privacy Policy") == "navigation_or_policy_boilerplate"
    assert _non_evidence_text_reason("Nutrition Policy*") == "list_heading_or_index_term"
    assert _non_evidence_text_reason("The https:// ensures that you are connecting to the official website.") == "site_navigation_or_security_boilerplate"
    assert _concept_backfill_rejection_reason("• Privacy Policy", "guideline_or_recommendation") == "navigation_or_policy_boilerplate"


def test_relation_model_json_salvages_complete_objects_from_truncated_array() -> None:
    raw = """```json
{
  "relations": [
    {"pair_id": "pair_001", "source_claim": "c001", "target_claim": "c002", "relation_type": "supports", "rationale": "A supports B."},
    {"pair_id": "pair_002", "source_claim": null, "target_claim": null, "relation_type": "none", "rationale": "No edge."},
    {"pair_id": "pair_003", "source_claim": "c003"
"""

    parsed = _parse_relation_model_json(raw)

    assert parsed is not None
    assert parsed["parse_recovery"] == "truncated_relations_array"
    assert [row["pair_id"] for row in parsed["relations"]] == ["pair_001", "pair_002"]


def test_relation_batches_cap_large_user_batch_size() -> None:
    items = [{"pair_id": f"pair_{index:03d}"} for index in range(10)]

    batches = _batches(items, batch_size=16)

    assert [len(batch) for batch in batches] == [4, 4, 2]


def test_relation_pair_block_uses_compact_claim_cards() -> None:
    long_text = "Sentence one is relevant. " + "Long filler. " * 200
    packet = {
        "pair_id": "pair_001",
        "left": _claim("demo_c001", long_text, "a", long_text, "conclusion_support"),
        "right": _claim("demo_c002", "Boundary applies.", "b", long_text, "scope_limit"),
    }

    block = _relation_pair_block(packet)

    assert "exact_evidence_quote_A" in block
    assert "excerpt_A" not in block
    assert "Pair contract:" in block
    assert "allowed_claim_ids_for_non_none_relation: demo_c001, demo_c002" in block
    assert "endpoint_rule:" in block
    assert len(block) < 2200
    assert block.count("Long filler") < 20


def test_relation_claim_card_prefers_exact_source_quote_over_broad_excerpt() -> None:
    claim = {
        **_claim(
            "demo_c001",
            "The exact finding matters.",
            "doc_a",
            "Broad background sentence. " * 20,
            "conclusion_support",
        ),
        "source_quote": "Exact source quote that grounds the finding.",
    }

    card = _relation_claim_card(claim, "A")

    assert "exact_evidence_quote_A: Exact source quote that grounds the finding." in card
    assert "Broad background sentence" not in card


def _claim(claim_id: str, claim: str, source_id: str, excerpt: str, role: str) -> dict[str, str]:
    return {
        "claim_id": claim_id,
        "claim": claim,
        "source_id": source_id,
        "excerpt": excerpt,
        "role": role,
    }
