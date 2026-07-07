from __future__ import annotations

import sys
import types
from pathlib import Path

import epistemic_case_mapper.staged_semantic_langextract as langextract_adapter
from epistemic_case_mapper.staged_semantic_claim_prompt_contract import claim_prompt_examples
from epistemic_case_mapper.staged_semantic_pipeline import (
    SourceChunk,
    SourceSpan,
    _batches,
    _candidate_relation_pairs,
    _claim_prompt,
    _claim_prompt_json_schema,
    _concept_backfill_rejection_reason,
    _extract_claims,
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
from epistemic_case_mapper.staged_semantic_relation_candidates import _relation_endpoint_rejection_reason
from epistemic_case_mapper.staged_semantic_relation_quality import relation_pair_intent


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

def test_claim_prompt_makes_decision_question_the_relevance_filter() -> None:
    manifest, region, case_manifest = _load_context(Path("."), "submission_manifest.yaml", "eggs_observational_vs_rct")
    chunk = SourceChunk(
        chunk_id="demo_lines_1_1",
        source_id="demo_source",
        title="Demo Source",
        start_line=1,
        end_line=1,
        ordinal=1,
        numbered_text="1: A bounded source span.",
        plain_text="A bounded source span.",
        spans=(
            SourceSpan(
                span_id="demo_s0001",
                source_id="demo_source",
                source_span="lines 1-1",
                text="A bounded source span.",
            ),
        ),
    )

    prompt = _claim_prompt(manifest, region, case_manifest, chunk, max_claims=2)
    schema = _claim_prompt_json_schema()

    assert "Decision question: How should a synthesis preserve the relationship between observational CVD outcome evidence" in prompt
    assert "Treat the decision question as the governing extraction filter" in prompt
    assert "Do not return claims merely because they mention the topic term" in prompt
    assert "source_quote as an exact substring" in prompt
    assert "question_relevance" in prompt
    assert "source_quote" in schema["properties"]["claims"]["items"]["properties"]
    assert "source_quote" in schema["properties"]["claims"]["items"]["required"]
    assert "scope_flags" in schema["properties"]["claims"]["items"]["properties"]

def test_prompt_builders_honor_explicit_decision_question_override() -> None:
    manifest, region, case_manifest = _load_context(Path("."), "submission_manifest.yaml", "eggs_observational_vs_rct")
    override = "Should generally healthy adults treat eggs as harmful, neutral, or beneficial for cardiovascular risk?"
    chunk = SourceChunk(
        chunk_id="demo_lines_1_1",
        source_id="demo_source",
        title="Demo Source",
        start_line=1,
        end_line=1,
        ordinal=1,
        numbered_text="1: Egg intake was not associated with higher cardiovascular risk in this cohort.",
        plain_text="Egg intake was not associated with higher cardiovascular risk in this cohort.",
        spans=(
            SourceSpan(
                span_id="demo_s0001",
                source_id="demo_source",
                source_span="lines 1-1",
                text="Egg intake was not associated with higher cardiovascular risk in this cohort.",
            ),
        ),
    )
    packet = {
        "pair_id": "pair_001",
        "left": {
            "claim_id": "demo_c001",
            "claim": "Egg intake was not associated with higher cardiovascular risk.",
            "source_id": "doc_a",
            "role": "conclusion_support",
            "source_alignment": {"source_quote": "not associated with higher cardiovascular risk"},
        },
        "right": {
            "claim_id": "demo_c002",
            "claim": "The cohort design limits causal interpretation.",
            "source_id": "doc_b",
            "role": "scope_limit",
            "source_alignment": {"source_quote": "cohort design limits causal interpretation"},
        },
        "pair_intent": {"intent": "cross_source_general_scope_to_finding", "allowed_relation_types": ["refines", "none"]},
    }

    claim_prompt = _claim_prompt(manifest, region, case_manifest, chunk, max_claims=2, decision_question=override)
    relation_prompt = _relation_pair_prompt(manifest, region, case_manifest, packet, decision_question=override)

    assert f"Decision question: {override}" in claim_prompt
    assert f"Decision question: {override}" in relation_prompt
    assert "Decision question: How should a synthesis preserve the relationship" not in claim_prompt

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
    assert accepted["question_relevance"] == "direct"
    assert accepted["scope_flags"] == ["none"]
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

def test_claim_prompt_examples_have_grounded_source_quotes() -> None:
    for example in claim_prompt_examples():
        excerpt = str(example.get("input_excerpt", ""))
        for claim in example.get("output", {}).get("claims", []):
            assert claim["source_quote"] in excerpt


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


def test_extract_claims_reuses_cached_chunk_payload(tmp_path: Path) -> None:
    repo_root = Path(".")
    manifest, region, case_manifest = _load_context(repo_root, "submission_manifest.yaml", "eggs_observational_vs_rct")
    chunk = SourceChunk(
        chunk_id="cache_demo_lines_1_1",
        source_id="cache_demo",
        title="Cache Demo",
        start_line=1,
        end_line=1,
        ordinal=1,
        numbered_text="1: Cached evidence line.",
        plain_text="Cached evidence line.",
        spans=(
            SourceSpan(
                span_id="cache_demo_s0001",
                source_id="cache_demo",
                source_span="lines 1-1",
                text="Cached evidence line.",
            ),
        ),
    )
    canonical = tmp_path / "claim_chunks" / "cache_demo_lines_1_1_canonical.json"
    canonical.parent.mkdir(parents=True)
    canonical.write_text(
        '{"claims":[{"claim":"Cached claim from prior run.","span_id":"cache_demo_s0001","entailed_by_excerpt":"yes","role":"background"}]}',
        encoding="utf-8",
    )

    claims, rejected = _extract_claims(
        repo_root,
        manifest,
        region,
        case_manifest,
        [chunk],
        backend="command:python3 -c 'raise SystemExit(99)'",
        backend_timeout=1,
        backend_retries=0,
        artifact_dir=tmp_path,
        max_claims_per_chunk=4,
        reuse_claim_cache=True,
    )
    progress = (tmp_path / "claim_extraction_progress.json").read_text(encoding="utf-8")

    assert [claim["claim"] for claim in claims] == ["Cached claim from prior run."]
    assert rejected == []
    assert '"cache_hit_count": 1' in progress
    assert '"backend_call_count": 0' in progress


def test_extract_claims_respects_valid_empty_model_response(tmp_path: Path) -> None:
    repo_root = Path(".")
    manifest, region, case_manifest = _load_context(repo_root, "submission_manifest.yaml", "eggs_observational_vs_rct")
    chunk = SourceChunk(
        chunk_id="empty_demo_lines_1_1",
        source_id="empty_demo",
        title="Empty Demo",
        start_line=1,
        end_line=1,
        ordinal=1,
        numbered_text="1: Bibliographic metadata only.",
        plain_text="Bibliographic metadata only.",
        spans=(
            SourceSpan(
                span_id="empty_demo_s0001",
                source_id="empty_demo",
                source_span="lines 1-1",
                text="Bibliographic metadata only.",
            ),
        ),
    )
    fake_model = tmp_path / "empty_claim_model.py"
    fake_model.write_text("import json\nprint(json.dumps({'claims': []}))\n", encoding="utf-8")

    claims, rejected = _extract_claims(
        repo_root,
        manifest,
        region,
        case_manifest,
        [chunk],
        backend=f"command:python3 {fake_model}",
        backend_timeout=5,
        backend_retries=0,
        artifact_dir=tmp_path,
        max_claims_per_chunk=4,
        reuse_claim_cache=False,
    )
    progress = (tmp_path / "claim_extraction_progress.json").read_text(encoding="utf-8")

    assert claims == []
    assert rejected == []
    assert '"fallback_claim_count": 0' in progress


def test_extract_claims_can_use_langextract_grounded_payload(monkeypatch, tmp_path: Path) -> None:
    repo_root = Path(".")
    manifest, region, case_manifest = _load_context(repo_root, "submission_manifest.yaml", "eggs_observational_vs_rct")
    chunk = SourceChunk(
        chunk_id="langextract_demo_lines_1_1",
        source_id="langextract_demo",
        title="LangExtract Demo",
        start_line=1,
        end_line=1,
        ordinal=1,
        numbered_text="1: The intervention reduced decision-relevant risk by 20 percent.",
        plain_text="The intervention reduced decision-relevant risk by 20 percent.",
        spans=(
            SourceSpan(
                span_id="langextract_demo_s0001",
                source_id="langextract_demo",
                source_span="lines 1-1",
                text="The intervention reduced decision-relevant risk by 20 percent.",
            ),
        ),
    )
    _install_fake_langextract(
        monkeypatch,
        extraction_text="reduced decision-relevant risk by 20 percent",
        attributes={
            "claim": "The intervention reduced decision-relevant risk by 20 percent.",
            "role": "conclusion_support",
            "question_relevance": "direct",
            "relevance_rationale": "It reports a decision-relevant outcome.",
            "scope_flags": ["none"],
            "entailed_by_excerpt": "yes",
        },
    )

    claims, rejected = _extract_claims(
        repo_root,
        manifest,
        region,
        case_manifest,
        [chunk],
        backend="ollama:fake-model",
        backend_timeout=5,
        backend_retries=0,
        artifact_dir=tmp_path,
        max_claims_per_chunk=4,
        reuse_claim_cache=False,
        claim_extractor="langextract",
    )
    progress = (tmp_path / "claim_extraction_progress.json").read_text(encoding="utf-8")

    assert [claim["claim"] for claim in claims] == ["The intervention reduced decision-relevant risk by 20 percent."]
    assert claims[0]["source_span"] == "lines 1-1"
    assert rejected == []
    assert '"claim_extractor": "langextract"' in progress
    report = (tmp_path / "claim_chunks" / "langextract_demo_lines_1_1_langextract_report.json").read_text(encoding="utf-8")
    assert '"use_schema_constraints": false' in report


def test_langextract_ollama_runtime_options_accept_fenced_json() -> None:
    assert langextract_adapter._runtime_options("ollama:gemma4:12b-mlx") == {
        "use_schema_constraints": False,
        "resolver_params": {"suppress_parse_errors": True},
    }
    assert langextract_adapter._runtime_options("openai:gpt-5.2") == {}


def test_langextract_span_resolution_prefers_exact_text_over_interval() -> None:
    chunk = SourceChunk(
        chunk_id="misaligned_lines_10_11",
        source_id="misaligned",
        title="Misaligned",
        start_line=10,
        end_line=11,
        ordinal=1,
        numbered_text="10: A meta-analysis found higher LDL.\n11: A different line discusses cohort outcomes.",
        plain_text="A meta-analysis found higher LDL.\nA different line discusses cohort outcomes.",
        spans=(
            SourceSpan(
                span_id="misaligned_s0010",
                source_id="misaligned",
                source_span="lines 10-10",
                text="A meta-analysis found higher LDL.",
            ),
            SourceSpan(
                span_id="misaligned_s0011",
                source_id="misaligned",
                source_span="lines 11-11",
                text="A different line discusses cohort outcomes.",
            ),
        ),
    )

    span_id = langextract_adapter._span_id_for_extraction(
        chunk,
        "A meta-analysis found higher LDL.",
        {"start_pos": 34, "end_pos": 54},
    )

    assert span_id == "misaligned_s0010"


def test_langextract_mode_requires_optional_package(monkeypatch, tmp_path: Path) -> None:
    def missing_import(name: str):
        if name == "langextract":
            raise ImportError("missing test module")
        return __import__(name)

    monkeypatch.setattr(langextract_adapter.importlib, "import_module", missing_import)
    repo_root = Path(".")
    manifest, region, case_manifest = _load_context(repo_root, "submission_manifest.yaml", "eggs_observational_vs_rct")
    chunk = SourceChunk(
        chunk_id="missing_langextract_lines_1_1",
        source_id="missing_langextract",
        title="Missing LangExtract",
        start_line=1,
        end_line=1,
        ordinal=1,
        numbered_text="1: The intervention reduced risk.",
        plain_text="The intervention reduced risk.",
        spans=(
            SourceSpan(
                span_id="missing_langextract_s0001",
                source_id="missing_langextract",
                source_span="lines 1-1",
                text="The intervention reduced risk.",
            ),
        ),
    )

    claims, rejected = _extract_claims(
        repo_root,
        manifest,
        region,
        case_manifest,
        [chunk],
        backend="ollama:fake-model",
        backend_timeout=5,
        backend_retries=0,
        artifact_dir=tmp_path,
        max_claims_per_chunk=4,
        reuse_claim_cache=False,
        claim_extractor="langextract",
    )

    assert claims
    assert rejected[0]["reason"] == "backend_error_used_deterministic_fallback"
    assert "LangExtract is not installed" in rejected[0]["error"]


def _claim(claim_id: str, claim: str, source_id: str, excerpt: str, role: str) -> dict[str, str]:
    return {
        "claim_id": claim_id,
        "claim": claim,
        "source_id": source_id,
        "excerpt": excerpt,
        "role": role,
    }


def _install_fake_langextract(monkeypatch, *, extraction_text: str, attributes: dict[str, object]) -> None:
    class Extraction:
        def __init__(self, extraction_class="", extraction_text="", attributes=None):
            self.extraction_class = extraction_class
            self.extraction_text = extraction_text
            self.attributes = attributes or {}
            self.char_interval = {"start_pos": 17, "end_pos": 60}
            self.alignment_status = "match_exact"

    class ExampleData:
        def __init__(self, text="", extractions=None):
            self.text = text
            self.extractions = extractions or []

    def extract(**kwargs):
        _ = kwargs
        return types.SimpleNamespace(
            extractions=[
                types.SimpleNamespace(
                    extraction_text=extraction_text,
                    attributes=attributes,
                    char_interval={"start_pos": 17, "end_pos": 60},
                    alignment_status="match_exact",
                )
            ]
        )

    fake = types.SimpleNamespace(
        data=types.SimpleNamespace(ExampleData=ExampleData, Extraction=Extraction),
        extract=extract,
    )
    monkeypatch.setitem(sys.modules, "langextract", fake)
