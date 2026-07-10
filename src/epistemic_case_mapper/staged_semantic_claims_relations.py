from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.classical_ml import tfidf_near_duplicate_pairs
from epistemic_case_mapper.config_profiles import (
    EpistemicConfigProfile,
    config_profile_from_manifest_payload,
    profile_vocabulary,
)
from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION, VALID_ENTAILMENT
from epistemic_case_mapper.staged_semantic_progress import PipelineProgress
from epistemic_case_mapper.staged_semantic_relation_backfill import finalize_sparse_relation_graph
from epistemic_case_mapper.staged_semantic_prompt_schemas import relation_json_schema
from epistemic_case_mapper.staged_semantic_relation_quality import relation_semantic_rejection_reason
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest

def _concept_gap_backfill_claims(
    *,
    all_chunks: list[SourceChunk],
    existing_claims: list[dict[str, Any]],
    existing_keys: set[tuple[str, str, str]],
    id_prefix: str,
    next_index: int,
    profile_id: str = "general_decision_support",
    max_total: int = 18,
    max_per_family: int = 2,
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    existing_text = "\n".join(
        str(claim.get("claim", "")) + "\n" + str(claim.get("excerpt", ""))
        for claim in existing_claims
    ).lower()
    candidates = _concept_gap_candidates(all_chunks, existing_text, profile_id=profile_id)
    backfilled: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    duplicate_span_ids: list[str] = []
    selected_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(backfilled) >= max_total:
            break
        family = str(candidate["family"])
        if family_counts.get(family, 0) >= max_per_family:
            continue
        span = candidate["span"]
        rejection_reason = _concept_backfill_rejection_reason(span.text, family)
        if rejection_reason:
            rejected_rows.append(
                {
                    "family": family,
                    "source_id": span.source_id,
                    "span_id": span.span_id,
                    "source_span": span.source_span,
                    "reason": rejection_reason,
                    "matched_markers": candidate["matched_markers"],
                }
            )
            continue
        claim = _concept_backfill_claim(span, family, candidate["matched_markers"], vocabulary=profile_vocabulary(profile_id))
        key = (
            claim["source_id"],
            _normalize_text(claim["excerpt"]),
            _normalize_text(claim["claim"]),
        )
        excerpt_key_exists = any(
            source_id == claim["source_id"] and excerpt == _normalize_text(claim["excerpt"])
            for source_id, excerpt, _claim_text in existing_keys
        )
        if key in existing_keys or excerpt_key_exists:
            duplicate_span_ids.append(span.span_id)
            continue
        claim["claim_id"] = f"{id_prefix}_c{next_index:03d}"
        next_index += 1
        existing_keys.add(key)
        family_counts[family] = family_counts.get(family, 0) + 1
        backfilled.append(claim)
        selected_rows.append(
            {
                "claim_id": claim["claim_id"],
                "family": family,
                "source_id": span.source_id,
                "span_id": span.span_id,
                "source_span": span.source_span,
                "score": candidate["score"],
                "matched_markers": candidate["matched_markers"],
            }
        )
    report = {
        "schema_id": "source_concept_gap_backfill_v1",
        "method": "concept_family_sentence_retrieval_with_quote_first_claims",
        "candidate_count": len(candidates),
        "backfilled_claim_count": len(backfilled),
        "family_counts": family_counts,
        "selected": selected_rows,
        "rejected": rejected_rows[:100],
        "rejection_counts": _counts(row["reason"] for row in rejected_rows),
        "duplicate_span_ids": duplicate_span_ids[:50],
    }
    return backfilled, report, next_index

def _concept_gap_candidates(all_chunks: list[SourceChunk], existing_text: str, *, profile_id: str = "general_decision_support") -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    vocabulary = profile_vocabulary(profile_id)
    for chunk in all_chunks:
        for span in chunk.spans:
            for family, matched in _source_concept_families(span.text, vocabulary=vocabulary).items():
                if _existing_text_covers_concept(existing_text, family, matched, vocabulary=vocabulary):
                    continue
                score = _concept_span_score(span.text, family, matched, vocabulary=vocabulary)
                if score <= 0:
                    continue
                candidates.append(
                    {
                        "family": family,
                        "span": span,
                        "score": score,
                        "matched_markers": matched,
                    }
                )
    candidates.sort(key=lambda row: (-int(row["score"]), _CONCEPT_FAMILY_PRIORITY.get(str(row["family"]), 99), row["span"].span_id))
    return candidates

def _source_concept_families(text: str, *, vocabulary: dict[str, Any] | None = None) -> dict[str, list[str]]:
    lowered = text.lower()
    matched: dict[str, list[str]] = {}
    for family, marker_groups in _concept_family_markers(vocabulary).items():
        hits: list[str] = []
        for markers in marker_groups:
            group_hits = [marker for marker in markers if marker in lowered]
            hits.extend(group_hits)
        if hits:
            matched[family] = _dedupe_strings(hits)
    return matched

def _existing_text_covers_concept(existing_text: str, family: str, matched_markers: list[str], *, vocabulary: dict[str, Any] | None = None) -> bool:
    strong_by_family = _concept_family_strong_markers(vocabulary)
    strong_markers = tuple(marker for marker in strong_by_family.get(family, ()) if marker in matched_markers)
    if strong_markers:
        return any(marker in existing_text for marker in strong_markers)
    return any(marker in existing_text for marker in matched_markers if len(marker) >= 5)

def _concept_span_score(text: str, family: str, matched_markers: list[str], *, vocabulary: dict[str, Any] | None = None) -> int:
    lowered = text.lower()
    if _non_evidence_text_reason(text):
        return 0
    score = 2 + 2 * len(set(matched_markers))
    for marker in _concept_family_strong_markers(vocabulary).get(family, ()):
        if marker in lowered:
            score += 4
    for marker in ("associated", "risk", "mortality", "cardiovascular", "outcome", "guideline", "recommend", "randomized", "cohort"):
        if marker in lowered:
            score += 1
    if len(text) < 40:
        score -= 3
    if _looks_like_reference_or_boilerplate(text):
        score -= 8
    return score

def _concept_backfill_rejection_reason(text: str, family: str) -> str:
    non_evidence = _non_evidence_text_reason(text)
    if non_evidence:
        return non_evidence
    lowered = text.lower()
    if family == "guideline_or_recommendation" and "policy" in lowered and not re.search(r"\b(?:recommend|guideline|advice|should|dietary|clinical|practice)\b", lowered):
        return "policy_marker_without_guidance_content"
    if not _has_evidence_predicate(lowered):
        return "no_evidence_predicate"
    return ""

def _concept_backfill_claim(span: SourceSpan, family: str, matched_markers: list[str], *, vocabulary: dict[str, Any] | None = None) -> dict[str, Any]:
    excerpt = re.sub(r"\s+", " ", span.text).strip()
    return {
        "claim_id": "",
        "claim": _quote_first_claim_text(excerpt, family, matched_markers, vocabulary=vocabulary),
        "source_id": span.source_id,
        "source_span": span.source_span,
        "excerpt": excerpt,
        "entailed_by_excerpt": "yes",
        "role": _concept_family_role(family, excerpt),
        "span_id": span.span_id,
        "extraction_method": "deterministic_concept_gap_backfill",
        "concept_gap_backfill": {
            "family": family,
            "matched_markers": matched_markers,
        },
    }

def _quote_first_claim_text(excerpt: str, family: str, matched_markers: list[str], *, vocabulary: dict[str, Any] | None = None) -> str:
    prefix = {
        "comparator_or_substitution": "Comparator/substitution evidence: ",
        "mechanism_or_biomarker": "Mechanism/biomarker evidence: ",
        "dietary_context": "Context/modifier evidence: ",
        "subgroup_or_scope": "Subgroup/scope evidence: ",
        "guideline_or_recommendation": "Guidance/recommendation evidence: ",
        "study_design": "Study-design evidence: ",
        "endpoint_or_outcome": "Endpoint/outcome evidence: ",
        "dose_or_threshold": "Dose/threshold evidence: ",
        "method_limit": "Method-limit evidence: ",
    }.get(family, "Source evidence: ")
    strong_markers = [marker for marker in _concept_family_strong_markers(vocabulary).get(family, ()) if marker in matched_markers]
    ordered_markers = [*strong_markers, *(marker for marker in matched_markers if marker not in strong_markers)]
    return prefix + _focused_excerpt(excerpt, ordered_markers, max_chars=260)

def _concept_family_role(family: str, text: str) -> str:
    lowered = text.lower()
    if family in {"subgroup_or_scope", "method_limit", "dietary_context"}:
        return "scope_limit"
    if family in {"comparator_or_substitution", "guideline_or_recommendation", "dose_or_threshold"}:
        return "implementation_constraint"
    if any(marker in lowered for marker in ("not associated", "higher risk", "lower risk", "reduced risk", "increased risk")):
        return "conclusion_support"
    return "background"

def _concept_family_markers(vocabulary: dict[str, Any] | None) -> dict[str, tuple[tuple[str, ...], ...]]:
    raw = (vocabulary or profile_vocabulary("general_decision_support")).get("concept_family_markers", {})
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, tuple[tuple[str, ...], ...]] = {}
    for family, groups in raw.items():
        if not isinstance(groups, list):
            continue
        normalized_groups: list[tuple[str, ...]] = []
        for group in groups:
            if isinstance(group, list):
                markers = tuple(str(marker).lower() for marker in group if str(marker).strip())
                if markers:
                    normalized_groups.append(markers)
        if normalized_groups:
            normalized[str(family)] = tuple(normalized_groups)
    return normalized

def _concept_family_strong_markers(vocabulary: dict[str, Any] | None) -> dict[str, tuple[str, ...]]:
    raw = (vocabulary or profile_vocabulary("general_decision_support")).get("concept_family_strong_markers", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(family): tuple(str(marker).lower() for marker in markers if str(marker).strip())
        for family, markers in raw.items()
        if isinstance(markers, list)
    }

def _looks_like_reference_or_boilerplate(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\bdoi\b|\bpmid\b|\bgoogle scholar\b|\bcrossref\b", lowered):
        return True
    if lowered.count("received ") >= 2 and len(lowered) > 400:
        return True
    return False

def _shorten_excerpt(text: str, max_chars: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip(" ,.;") + "..."

def _focused_excerpt(text: str, markers: list[str], max_chars: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    lowered = cleaned.lower()
    marker_positions = [
        (lowered.find(marker), marker)
        for marker in sorted(markers, key=len, reverse=True)
        if marker and lowered.find(marker) >= 0
    ]
    if not marker_positions:
        return _shorten_excerpt(cleaned, max_chars=max_chars)
    position, marker = marker_positions[0]
    marker_end = position + len(marker)
    window_start = max(0, position - max_chars // 3)
    window_end = min(len(cleaned), max(marker_end + max_chars // 2, window_start + max_chars))
    if window_end - window_start < max_chars:
        window_start = max(0, window_end - max_chars)
    snippet = cleaned[window_start:window_end].strip(" ,.;")
    if window_start > 0:
        snippet = "..." + snippet
    if window_end < len(cleaned):
        snippet = snippet.rstrip(" ,.;") + "..."
    return snippet

def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped

_CONCEPT_FAMILY_PRIORITY = {
    "comparator_or_substitution": 0,
    "mechanism_or_biomarker": 1,
    "dietary_context": 2,
    "subgroup_or_scope": 3,
    "guideline_or_recommendation": 4,
    "study_design": 5,
    "endpoint_or_outcome": 6,
    "dose_or_threshold": 7,
    "method_limit": 8,
}

def _next_claim_index(claims: list[dict[str, Any]], id_prefix: str) -> int:
    max_index = 0
    pattern = re.compile(rf"^{re.escape(id_prefix)}_c(\d+)$")
    for claim in claims:
        match = pattern.match(str(claim.get("claim_id", "")))
        if match:
            max_index = max(max_index, int(match.group(1)))
    return max_index + 1

def consolidate_claims_for_map(
    claims: list[dict[str, Any]],
    *,
    min_claims: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(claims) < 2:
        return claims, {
            "schema_id": "claim_consolidation_report_v1",
            "changed": False,
            "method": "tfidf_overlap_polarity_guarded_components",
            "input_claim_count": len(claims),
            "output_claim_count": len(claims),
            "merged_groups": [],
        }
    duplicate_pairs = _consolidation_duplicate_pairs(claims)
    groups = _claim_duplicate_components(claims, duplicate_pairs)
    if not groups:
        return claims, {
            "schema_id": "claim_consolidation_report_v1",
            "changed": False,
            "method": "tfidf_overlap_polarity_guarded_components",
            "input_claim_count": len(claims),
            "output_claim_count": len(claims),
            "duplicate_pairs": _duplicate_pair_rows(duplicate_pairs),
            "merged_groups": [],
        }
    grouped_ids = {claim_id for group in groups for claim_id in group}
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    consolidated: list[dict[str, Any]] = []
    merged_group_rows: list[dict[str, Any]] = []
    for group in groups:
        group_claims = [claim_lookup[claim_id] for claim_id in group if claim_id in claim_lookup]
        if not group_claims:
            continue
        canonical = _canonical_claim_for_group(group_claims)
        merged_ids = [str(claim.get("claim_id")) for claim in group_claims]
        merged_sources = _claim_supporting_sources(group_claims)
        merged_excerpts = _claim_supporting_excerpts(group_claims)
        merged_methods = sorted({str(claim.get("extraction_method", "model")) for claim in group_claims if claim.get("extraction_method")})
        canonical = dict(canonical)
        canonical["supporting_claim_ids"] = merged_ids
        canonical["supporting_sources"] = merged_sources
        canonical["supporting_excerpts"] = merged_excerpts[:6]
        canonical["consolidation_method"] = "tfidf_overlap_polarity_guarded_components"
        if merged_methods:
            canonical["supporting_extraction_methods"] = merged_methods
        consolidated.append(canonical)
        merged_group_rows.append(
            {
                "canonical_claim_id": canonical.get("claim_id"),
                "merged_claim_ids": merged_ids,
                "supporting_sources": merged_sources,
            }
        )
    for claim in claims:
        if str(claim.get("claim_id")) not in grouped_ids:
            consolidated.append(claim)
    order = {str(claim.get("claim_id")): index for index, claim in enumerate(claims)}
    consolidated.sort(key=lambda claim: order.get(str(claim.get("claim_id")), len(order)))
    if len(consolidated) < min_claims:
        return claims, {
            "schema_id": "claim_consolidation_report_v1",
            "changed": False,
            "method": "tfidf_overlap_polarity_guarded_components",
            "reason": "would_reduce_below_min_claims",
            "min_claims": min_claims,
            "input_claim_count": len(claims),
            "output_claim_count": len(claims),
            "candidate_output_claim_count": len(consolidated),
            "duplicate_pairs": _duplicate_pair_rows(duplicate_pairs),
            "merged_groups": merged_group_rows,
        }
    return consolidated, {
        "schema_id": "claim_consolidation_report_v1",
        "changed": True,
        "method": "tfidf_overlap_polarity_guarded_components",
        "input_claim_count": len(claims),
        "output_claim_count": len(consolidated),
        "duplicate_pairs": _duplicate_pair_rows(duplicate_pairs),
        "merged_groups": merged_group_rows,
    }

def _consolidation_duplicate_pairs(claims: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
    ids = [str(claim.get("claim_id", "")) for claim in claims]
    texts = [str(claim.get("claim", "") or claim.get("text", "")) for claim in claims]
    tfidf_pairs = tfidf_near_duplicate_pairs(texts, ids, threshold=CONSOLIDATION_SIMILARITY_THRESHOLD)
    pair_scores: dict[tuple[str, str], float] = {}
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    for left, right, score in tfidf_pairs:
        if _claims_can_merge(claim_lookup.get(left, {}), claim_lookup.get(right, {})):
            pair_scores[(left, right)] = score
    for left_index, left in enumerate(claims):
        for right in claims[left_index + 1 :]:
            if not _claims_can_merge(left, right):
                continue
            overlap = _text_overlap_ratio(str(left.get("claim", "")), str(right.get("claim", "")))
            if overlap >= CONSOLIDATION_OVERLAP_THRESHOLD:
                pair_scores.setdefault((str(left.get("claim_id", "")), str(right.get("claim_id", ""))), round(overlap, 4))
    return [(left, right, score) for (left, right), score in pair_scores.items() if left and right]

def _claims_can_merge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not left or not right:
        return False
    left_polarity = _claim_polarity(str(left.get("claim", "")))
    right_polarity = _claim_polarity(str(right.get("claim", "")))
    if left_polarity != "mixed" and right_polarity != "mixed" and left_polarity != right_polarity:
        return False
    left_role = str(left.get("role", "other"))
    right_role = str(right.get("role", "other"))
    role_family = {
        "conclusion_support": "directional",
        "crux": "crux",
        "scope_limit": "limit",
        "external_validity": "limit",
        "measurement_validity": "method",
        "implementation_constraint": "method",
        "cost_feasibility": "method",
        "background": "background",
        "other": "other",
    }
    return role_family.get(left_role, left_role) == role_family.get(right_role, right_role)

def _claim_polarity(text: str) -> str:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    positive = any(marker in normalized for marker in (" lower risk ", " reduced risk ", " no association ", " not associated ", " no adverse ", " did not have adverse ", " beneficial "))
    negative = any(marker in normalized for marker in (" higher risk ", " increased risk ", " harmful ", " adverse effect ", " adverse effects ", " mortality ", " concern "))
    if positive and not negative:
        return "positive_or_null"
    if negative and not positive:
        return "negative_or_concern"
    return "mixed"

def _claim_duplicate_components(
    claims: list[dict[str, Any]],
    duplicate_pairs: list[tuple[str, str, float]],
) -> list[list[str]]:
    ids = {str(claim.get("claim_id", "")) for claim in claims if claim.get("claim_id")}
    parent = {claim_id: claim_id for claim_id in ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        if left not in parent or right not in parent:
            return
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right, _score in duplicate_pairs:
        union(left, right)
    groups: dict[str, list[str]] = {}
    for claim_id in ids:
        groups.setdefault(find(claim_id), []).append(claim_id)
    order = {str(claim.get("claim_id")): index for index, claim in enumerate(claims)}
    return [
        sorted(group, key=lambda claim_id: order.get(claim_id, len(order)))
        for group in groups.values()
        if len(group) > 1
    ]

def _canonical_claim_for_group(group_claims: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        group_claims,
        key=lambda claim: (
            1 if str(claim.get("extraction_method", "")).startswith("deterministic") else 0,
            -_span_signal_score(str(claim.get("claim", ""))),
            len(str(claim.get("claim", ""))),
            str(claim.get("claim_id", "")),
        ),
    )[0]

def _claim_supporting_sources(group_claims: list[dict[str, Any]]) -> list[str]:
    sources: list[str] = []
    for claim in group_claims:
        source_id = str(claim.get("source_id", ""))
        if source_id:
            sources.append(source_id)
        for source_id in claim.get("supporting_sources", []):
            if isinstance(source_id, str):
                sources.append(source_id)
    return sorted(set(sources))

def _claim_supporting_excerpts(group_claims: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for claim in group_claims:
        row = {
            "claim_id": str(claim.get("claim_id", "")),
            "source_id": str(claim.get("source_id", "")),
            "source_span": str(claim.get("source_span", "")),
            "excerpt": str(claim.get("excerpt", "")),
        }
        key = (row["source_id"], row["source_span"], row["excerpt"])
        if key not in seen and row["excerpt"]:
            seen.add(key)
            rows.append(row)
        for existing in claim.get("supporting_excerpts", []):
            if not isinstance(existing, dict):
                continue
            existing_row = {
                "claim_id": str(existing.get("claim_id", "")),
                "source_id": str(existing.get("source_id", "")),
                "source_span": str(existing.get("source_span", "")),
                "excerpt": str(existing.get("excerpt", "")),
            }
            key = (existing_row["source_id"], existing_row["source_span"], existing_row["excerpt"])
            if key not in seen and existing_row["excerpt"]:
                seen.add(key)
                rows.append(existing_row)
    return rows

def _duplicate_pair_rows(pairs: list[tuple[str, str, float]]) -> list[dict[str, Any]]:
    return [{"left": left, "right": right, "score": score} for left, right, score in pairs]

def _run_quality_repair(
    *,
    repo_root: Path,
    manifest_path: str,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[SourceChunk],
    selected_chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    decision_question: str | None = None,
) -> dict[str, Any]:
    return run_map_critique_repair_loop(
        repo_root=repo_root,
        manifest_path=manifest_path,
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        selected_chunks=selected_chunks,
        skipped_chunks=skipped_chunks,
        candidate_map=candidate_map,
        quality_report=quality_report,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifact_dir,
        decision_question=decision_question,
    )

def _repair_improves_or_preserves_quality(original: dict[str, Any], repaired: dict[str, Any]) -> bool:
    original_rank = _quality_status_rank(str(original.get("status", "")))
    repaired_rank = _quality_status_rank(str(repaired.get("status", "")))
    original_score = int(original.get("score", 0))
    repaired_score = int(repaired.get("score", 0))
    return repaired_rank >= original_rank and repaired_score >= original_score

def _quality_status_rank(status: str) -> int:
    return {
        "needs_repair": 0,
        "review_recommended": 1,
        "usable_with_review": 2,
    }.get(status, -1)

def _summary_repair_info(repo_root: Path, repair_info: dict[str, Any]) -> dict[str, Any]:
    return summarize_repair_info(repo_root, repair_info)

def _extract_relations(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    claims: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    max_relation_pairs: int,
    relation_batch_size: int,
    decision_question: str | None = None,
    progress: PipelineProgress | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if len(claims) < 2:
        return [], [], [{"reason": "too_few_claims"}]
    effective_max_relation_pairs = _relation_pair_budget(claims, max_relation_pairs)
    pair_packets = _candidate_relation_pairs(claims, effective_max_relation_pairs)
    _write_relation_candidate_pool_report(artifact_dir, claims, pair_packets, max_relation_pairs, effective_max_relation_pairs)
    batches = list(_batches(pair_packets, relation_batch_size))
    _start_relation_progress(progress, claims, pair_packets, batches, max_relation_pairs, effective_max_relation_pairs)
    claim_ids = {claim["claim_id"] for claim in claims}
    permitted_types = manifest.relation_ontology.permitted_types()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    relation_index = 1

    for batch_index, batch in enumerate(batches, start=1):
        batch_id = f"batch_{batch_index:03d}"
        prompt = (
            _relation_pair_prompt(manifest, region, case_manifest, batch[0], decision_question=decision_question)
            if len(batch) == 1
            else _relation_batch_prompt(manifest, region, case_manifest, batch, batch_id, decision_question=decision_question)
        )
        artifact_subdir = "relation_pairs" if len(batch) == 1 else "relation_batches"
        artifact_stem = batch[0]["pair_id"] if len(batch) == 1 else batch_id
        write_markdown(artifact_dir / artifact_subdir / f"{artifact_stem}_prompt.txt", prompt)
        _start_relation_batch_progress(progress, batch_id, batch_index, batches, batch, backend_timeout)
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                response_schema=relation_json_schema(batch=len(batch) > 1),
            )
            raw = result.text
            if progress:
                progress.finish_backend_call(status="completed", pair_count=len(batch))
        except (RuntimeError, ValueError) as exc:
            if progress:
                progress.finish_backend_call(status="backend_error", error=str(exc), pair_count=len(batch))
            if len(batch) > 1:
                relation_index = _append_singleton_fallback(
                    accepted, payloads, rejected, relation_index,
                    manifest, region, case_manifest, batch, claim_ids, permitted_types, seen,
                    backend, backend_timeout, backend_retries, artifact_dir, batch_id, str(exc), decision_question, progress,
                )
                continue
            for packet in batch:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "backend_error", "error": str(exc)})
            continue
        write_markdown(artifact_dir / artifact_subdir / f"{artifact_stem}_raw.txt", raw)
        payload = _parse_relation_model_json(raw)
        write_json(artifact_dir / artifact_subdir / f"{artifact_stem}_canonical.json", payload or {})
        if not isinstance(payload, dict):
            if len(batch) > 1:
                relation_index = _append_singleton_fallback(
                    accepted, payloads, rejected, relation_index,
                    manifest, region, case_manifest, batch, claim_ids, permitted_types, seen,
                    backend, backend_timeout, backend_retries, artifact_dir, batch_id, "invalid_json", decision_question, progress,
                )
                continue
            for packet in batch:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "invalid_json"})
            continue
        payloads.append(payload)
        packet_lookup = {packet["pair_id"]: packet for packet in batch}
        proposals = _relation_proposals(payload)
        if not proposals:
            for packet in batch:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "missing_relation_proposal"})
            continue
        proposed_pair_ids: set[str] = set()
        for proposal in proposals:
            pair_id = str(proposal.get("pair_id", "")).strip() if isinstance(proposal, dict) else ""
            packet = packet_lookup.get(pair_id)
            if packet is None:
                rejected.append({"pair_id": pair_id or "missing", "batch_id": batch_id, "reason": "unknown_pair_id", "proposal": proposal})
                continue
            proposed_pair_ids.add(pair_id)
            relation, reason = _normalize_relation_proposal(proposal, claim_ids, permitted_types, packet)
            if relation is None:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": reason, "proposal": proposal})
                continue
            if _append_semantic_relation_rejection(rejected, relation, packet, batch_id, proposal):
                continue
            key = (relation["source_claim"], relation["target_claim"], relation["relation_type"])
            if key in seen:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "duplicate_relation", "proposal": proposal})
                continue
            seen.add(key)
            relation["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
            relation_index += 1
            accepted.append(relation)
        for packet in batch:
            if packet["pair_id"] not in proposed_pair_ids:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "missing_relation_proposal"})
    accepted, rejected = _finalize_and_write_relations(accepted, rejected, pair_packets, permitted_types, region, relation_index, seen, claims, artifact_dir)
    _finish_relation_progress(progress, pair_packets, batches, accepted, rejected)
    return accepted, payloads, rejected


def _append_singleton_fallback(
    accepted: list[dict[str, Any]],
    payloads: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    relation_index: int,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    batch: list[dict[str, Any]],
    claim_ids: set[str],
    permitted_types: set[str],
    seen: set[tuple[str, str, str]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    batch_id: str,
    batch_error: str,
    decision_question: str | None,
    progress: PipelineProgress | None,
) -> int:
    singleton_relations, singleton_payloads, singleton_rejected, relation_index = _classify_singleton_relations(
        manifest=manifest, region=region, case_manifest=case_manifest, batch=batch,
        claim_ids=claim_ids, permitted_types=permitted_types, seen=seen, relation_index=relation_index,
        backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries,
        artifact_dir=artifact_dir, batch_id=batch_id, batch_error=batch_error,
        decision_question=decision_question, progress=progress,
    )
    accepted.extend(singleton_relations)
    payloads.extend(singleton_payloads)
    rejected.extend(singleton_rejected)
    return relation_index


def _start_relation_progress(
    progress: PipelineProgress | None,
    claims: list[dict[str, Any]],
    pair_packets: list[dict[str, Any]],
    batches: list[list[dict[str, Any]]],
    requested_max_pairs: int,
    effective_max_pairs: int,
) -> None:
    if progress:
        progress.start_stage(
            "relation_extraction",
            claim_count=len(claims),
            selected_pair_count=len(pair_packets),
            total_batches=len(batches),
            requested_max_pairs=requested_max_pairs,
            effective_max_pairs=effective_max_pairs,
        )


def _start_relation_batch_progress(
    progress: PipelineProgress | None,
    batch_id: str,
    batch_index: int,
    batches: list[list[dict[str, Any]]],
    batch: list[dict[str, Any]],
    backend_timeout: int | None,
) -> None:
    if progress:
        progress.start_backend_call(
            stage="relation_extraction",
            item_id=batch_id,
            item_index=batch_index,
            total_items=len(batches),
            timeout_seconds=backend_timeout,
            pair_count=len(batch),
            pair_ids=[packet["pair_id"] for packet in batch],
        )


def _finish_relation_progress(
    progress: PipelineProgress | None,
    pair_packets: list[dict[str, Any]],
    batches: list[list[dict[str, Any]]],
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> None:
    if progress:
        progress.finish_stage(
            "relation_extraction",
            selected_pair_count=len(pair_packets),
            total_batches=len(batches),
            accepted_relation_count=len(accepted),
            rejected_relation_count=len(rejected),
        )


def _finalize_and_write_relations(
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    pair_packets: list[dict[str, Any]],
    permitted_types: set[str],
    region: WorkedRegion,
    relation_index: int,
    seen: set[tuple[str, str, str]],
    claims: list[dict[str, Any]],
    artifact_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted, rejected, _ = finalize_sparse_relation_graph(
        accepted=accepted,
        rejected=rejected,
        pair_packets=pair_packets,
        permitted_types=permitted_types,
        region=region,
        relation_index=relation_index,
        seen=seen,
        min_relation_count=max(2, len(claims) // 20) if len(claims) >= 20 else 0,
    )
    write_json(artifact_dir / "accepted_relations.json", {"relations": accepted, "rejected": rejected})
    return accepted, rejected


def _append_semantic_relation_rejection(
    rejected: list[dict[str, Any]],
    relation: dict[str, Any],
    packet: dict[str, Any],
    batch_id: str,
    proposal: Any,
) -> bool:
    reason = relation_semantic_rejection_reason(relation, packet)
    if not reason:
        return False
    rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": reason, "proposal": proposal})
    return True


def _write_relation_candidate_pool_report(
    artifact_dir: Path,
    claims: list[dict[str, Any]],
    pair_packets: list[dict[str, Any]],
    requested_max_pairs: int,
    effective_max_pairs: int,
) -> None:
    write_json(
        artifact_dir / "relation_candidate_pool_report.json",
        _relation_candidate_pool_report(
            claims,
            pair_packets,
            requested_max_pairs=requested_max_pairs,
            effective_max_pairs=effective_max_pairs,
        ),
    )


# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.staged_semantic_pipeline_runner import (
    CONSOLIDATION_OVERLAP_THRESHOLD,
    CONSOLIDATION_SIMILARITY_THRESHOLD,
    SourceChunk,
    SourceSpan,
)
from epistemic_case_mapper.staged_semantic_quality import (
    _classify_singleton_relations,
    _counts,
    _text_overlap_ratio,
)
from epistemic_case_mapper.staged_semantic_map_repair_loop import run_map_critique_repair_loop, summarize_repair_info
from epistemic_case_mapper.staged_semantic_relation_candidates import (
    _candidate_relation_pairs,
    _relation_candidate_pool_report,
    _relation_pair_budget,
)
from epistemic_case_mapper.staged_semantic_sources import (
    _batches,
    _has_evidence_predicate,
    _normalize_relation_proposal,
    _normalize_text,
    _non_evidence_text_reason,
    _parse_model_json,
    _parse_relation_model_json,
    _relation_batch_prompt,
    _relation_pair_prompt,
    _relation_proposals,
    _relative,
    _span_signal_score,
)
