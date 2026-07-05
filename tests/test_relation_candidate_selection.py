from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.staged_semantic_pipeline import (
    SourceChunk,
    SourceSpan,
    _batches,
    _candidate_relation_pairs,
    _concept_backfill_rejection_reason,
    _extract_claims,
    _load_context,
    _non_evidence_text_reason,
    _parse_relation_model_json,
    _relation_pair_block,
)


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

    assert "excerpt_A" in block
    assert len(block) < 1600
    assert block.count("Long filler") < 20


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


def _claim(claim_id: str, claim: str, source_id: str, excerpt: str, role: str) -> dict[str, str]:
    return {
        "claim_id": claim_id,
        "claim": claim,
        "source_id": source_id,
        "excerpt": excerpt,
        "role": role,
    }
