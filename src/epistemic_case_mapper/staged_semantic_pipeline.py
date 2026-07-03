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
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION, VALID_ENTAILMENT, validate_map_candidate
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest


CLAIM_EXTRACTION_PROMPT_VERSION = "staged_claim_extraction_prompt_v1_json"
RELATION_PROMPT_VERSION = "staged_relation_prompt_v1_json"
RELATION_BATCH_PROMPT_VERSION = "staged_relation_batch_prompt_v1_json"
VALID_CLAIM_ROLES = {
    "conclusion_support",
    "crux",
    "scope_limit",
    "implementation_constraint",
    "background",
    "other",
}
CONSOLIDATION_SIMILARITY_THRESHOLD = 0.72
CONSOLIDATION_OVERLAP_THRESHOLD = 0.82


@dataclass(frozen=True)
class SourceSpan:
    span_id: str
    source_id: str
    source_span: str
    text: str


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    source_id: str
    title: str
    start_line: int
    end_line: int
    ordinal: int
    numbered_text: str
    plain_text: str
    spans: tuple[SourceSpan, ...]


@dataclass(frozen=True)
class StagedMapResult:
    output_path: Path
    artifact_dir: Path
    claim_count: int
    relation_count: int
    rejected_claim_count: int
    rejected_relation_count: int
    failures: tuple[str, ...]
    quality_status: str = "not_run"
    quality_repair_ran: bool = False
    quality_repaired: bool = False


def run_staged_map(
    repo_root: Path,
    manifest_path: str,
    region_id: str,
    backend: str,
    output_path: str | Path | None = None,
    artifact_dir: str | Path | None = None,
    chunk_lines: int = 40,
    chunk_overlap_lines: int = 0,
    max_chunks_per_source: int | None = None,
    max_total_chunks: int | None = None,
    max_claims_per_chunk: int = 4,
    max_relation_pairs: int = 12,
    relation_batch_size: int = 4,
    backend_timeout: int | None = 90,
    backend_retries: int = 1,
    validate: bool = True,
    repair_quality: bool = False,
) -> StagedMapResult:
    if chunk_lines < 1:
        raise ValueError("chunk_lines must be positive")
    if chunk_overlap_lines < 0 or chunk_overlap_lines >= chunk_lines:
        raise ValueError("chunk_overlap_lines must be nonnegative and smaller than chunk_lines")
    if max_chunks_per_source is not None and max_chunks_per_source < 1:
        raise ValueError("max_chunks_per_source must be positive when supplied")
    if max_total_chunks is not None and max_total_chunks < 1:
        raise ValueError("max_total_chunks must be positive when supplied")
    if relation_batch_size < 1:
        raise ValueError("relation_batch_size must be positive")
    manifest, region, case_manifest = _load_context(repo_root, manifest_path, region_id)
    artifacts = _artifact_dir(repo_root, region_id, artifact_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    config_profile = _case_config_profile(case_manifest)

    all_chunks = _source_chunks(repo_root, case_manifest, region, chunk_lines, chunk_overlap_lines)
    chunks, skipped_chunks = _budget_chunks(all_chunks, max_chunks_per_source, max_total_chunks)
    claims, rejected_claims = _extract_claims(
        repo_root=repo_root,
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        chunks=chunks,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifacts,
        max_claims_per_chunk=max_claims_per_chunk,
    )
    llm_claim_count = len(claims)
    coverage_claims, coverage_report = _coverage_backfill_claims(
        all_chunks=all_chunks,
        selected_chunks=chunks,
        existing_claims=claims,
        id_prefix=region.id_prefix,
        profile_id=config_profile.profile_id,
    )
    if coverage_claims:
        claims.extend(coverage_claims)
    pre_consolidation_claim_count = len(claims)
    write_json(artifacts / "coverage_backfill_claims.json", coverage_report)
    claims, consolidation_report = consolidate_claims_for_map(
        claims,
        min_claims=max(2, region.thresholds.min_claims),
    )
    write_json(artifacts / "claim_consolidation_report.json", consolidation_report)
    relations, relation_payloads, rejected_relations = _extract_relations(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        claims=claims,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifacts,
        max_relation_pairs=max_relation_pairs,
        relation_batch_size=relation_batch_size,
    )
    relations = _sharpen_relations(relations, claims, manifest.relation_ontology.permitted_types())
    final_map = _assemble_map(
        region=region,
        case_manifest=case_manifest,
        claims=claims,
        relations=relations,
        relation_payloads=relation_payloads,
    )
    quality_report = evaluate_staged_map_quality(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        selected_chunks=chunks,
        skipped_chunks=skipped_chunks,
        candidate_map=final_map,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
    )
    write_json(artifacts / "candidate_map_initial.json", final_map)
    write_json(artifacts / "map_quality_report_initial.json", quality_report)
    write_markdown(artifacts / "MAP_QUALITY_REPORT_INITIAL.md", _quality_markdown(quality_report))
    repair_info: dict[str, Any] = {
        "ran": False,
        "accepted": False,
        "reason": "not_requested",
    }
    if repair_quality:
        repair_info = _run_quality_repair(
            repo_root=repo_root,
            manifest_path=manifest_path,
            manifest=manifest,
            region=region,
            case_manifest=case_manifest,
            all_chunks=all_chunks,
            selected_chunks=chunks,
            skipped_chunks=skipped_chunks,
            candidate_map=final_map,
            quality_report=quality_report,
            rejected_claims=rejected_claims,
            rejected_relations=rejected_relations,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            artifact_dir=artifacts,
        )
        if repair_info.get("accepted") and isinstance(repair_info.get("candidate_map"), dict):
            final_map = repair_info["candidate_map"]
            quality_report = repair_info["quality_report"]
    target = Path(output_path or region.map_path)
    if not target.is_absolute():
        target = repo_root / target
    validation_target = artifacts / "candidate_map.json"
    write_json(validation_target, final_map)
    failures: list[str] = []
    if validate:
        failures = validate_map_candidate(repo_root, manifest_path, region_id, validation_target)
    if failures and validate:
        target = artifacts / "failed_candidate.json"
    write_json(target, final_map)
    write_json(artifacts / "map_quality_report.json", quality_report)
    write_markdown(artifacts / "MAP_QUALITY_REPORT.md", _quality_markdown(quality_report))
    repair_prompt_path = artifacts / "map_quality_repair_prompt.txt"
    if not repair_prompt_path.exists():
        write_markdown(repair_prompt_path, _map_quality_repair_prompt(region, case_manifest, final_map, quality_report))
    final_claims = [claim for claim in final_map.get("claims", []) if isinstance(claim, dict)]
    final_relations = [relation for relation in final_map.get("relations", []) if isinstance(relation, dict)]
    write_json(
        artifacts / "run_summary.json",
        {
            "region_id": region.region_id,
            "backend": backend,
            "chunk_lines": chunk_lines,
            "chunk_overlap_lines": chunk_overlap_lines,
            "max_chunks_per_source": max_chunks_per_source,
            "max_total_chunks": max_total_chunks,
            "max_claims_per_chunk": max_claims_per_chunk,
            "max_relation_pairs": max_relation_pairs,
            "relation_batch_size": relation_batch_size,
            "backend_timeout": backend_timeout,
            "backend_retries": backend_retries,
            "epistemic_config_profile": config_profile.profile_id,
            "all_chunk_count": len(all_chunks),
            "selected_chunk_count": len(chunks),
            "skipped_chunk_count": len(skipped_chunks),
            "chunks": [_chunk_summary(chunk) for chunk in chunks],
            "skipped_chunks": skipped_chunks,
            "coverage_backfill": coverage_report,
            "claim_consolidation": consolidation_report,
            "llm_claim_count": llm_claim_count,
            "coverage_claim_count": len(coverage_claims),
            "pre_consolidation_claim_count": pre_consolidation_claim_count,
            "initial_claim_count": len(claims),
            "initial_relation_count": len(relations),
            "relation_sharpening": _relation_sharpening_summary(relations),
            "claim_count": len(final_claims),
            "relation_count": len(final_relations),
            "relation_batch_count": _relation_batch_count(max_relation_pairs, relation_batch_size, claims),
            "rejected_claims": rejected_claims,
            "rejected_relations": rejected_relations,
            "candidate_path": _relative(repo_root, validation_target),
            "output_path": _relative(repo_root, target),
            "failures": failures,
            "quality_status": quality_report["status"],
            "quality_score": quality_report["score"],
            "quality_report": _relative(repo_root, artifacts / "map_quality_report.json"),
            "quality_repair_prompt": _relative(repo_root, artifacts / "map_quality_repair_prompt.txt"),
            "quality_repair": _summary_repair_info(repo_root, repair_info),
        },
    )
    return StagedMapResult(
        output_path=target,
        artifact_dir=artifacts,
        claim_count=len(final_claims),
        relation_count=len(final_relations),
        rejected_claim_count=len(rejected_claims),
        rejected_relation_count=len(rejected_relations),
        failures=tuple(failures),
        quality_status=str(quality_report["status"]),
        quality_repair_ran=bool(repair_info.get("ran")),
        quality_repaired=bool(repair_info.get("accepted")),
    )


def _extract_claims(
    repo_root: Path,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    chunks: list[SourceChunk],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    max_claims_per_chunk: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    claim_index = 1
    valid_roles = set(_configured_claim_roles(case_manifest))

    for chunk in chunks:
        span_lookup = {span.span_id: span for span in chunk.spans}
        chunk_accept_count = 0
        prompt = _claim_prompt(manifest, region, case_manifest, chunk, max_claims_per_chunk)
        write_markdown(artifact_dir / "claim_chunks" / f"{chunk.chunk_id}_prompt.txt", prompt)
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
            )
            raw = result.text
        except (RuntimeError, ValueError) as exc:
            fallback = _fallback_claim_for_chunk(chunk)
            if fallback is not None:
                key = (
                    fallback["source_id"],
                    _normalize_text(fallback["excerpt"]),
                    _normalize_text(fallback["claim"]),
                )
                if key not in seen:
                    seen.add(key)
                    fallback["claim_id"] = f"{region.id_prefix}_c{claim_index:03d}"
                    claim_index += 1
                    accepted.append(fallback)
                    rejected.append(
                        {
                            "chunk_id": chunk.chunk_id,
                            "reason": "backend_error_used_deterministic_fallback",
                            "error": str(exc),
                            "span_id": fallback["span_id"],
                        }
                    )
                    continue
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "backend_error", "error": str(exc)})
            continue
        write_markdown(artifact_dir / "claim_chunks" / f"{chunk.chunk_id}_raw.txt", raw)
        payload = _parse_model_json(raw)
        write_json(artifact_dir / "claim_chunks" / f"{chunk.chunk_id}_canonical.json", payload or {})
        if not isinstance(payload, dict):
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "invalid_json"})
            continue
        proposals = payload.get("claims", [])
        if not isinstance(proposals, list) and "claim" in payload:
            proposals = [payload]
        if not isinstance(proposals, list):
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "claims_not_list"})
            continue
        for proposal in proposals:
            claim, reason = _normalize_claim_proposal(proposal, span_lookup, valid_roles)
            if claim is None:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": reason, "proposal": proposal})
                continue
            key = (
                claim["source_id"],
                _normalize_text(claim["excerpt"]),
                _normalize_text(claim["claim"]),
            )
            if key in seen:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": "duplicate_claim", "proposal": proposal})
                continue
            seen.add(key)
            claim["claim_id"] = f"{region.id_prefix}_c{claim_index:03d}"
            claim_index += 1
            accepted.append(claim)
            chunk_accept_count += 1
        if chunk_accept_count == 0:
            fallback = _fallback_claim_for_chunk(chunk)
            if fallback is not None:
                key = (
                    fallback["source_id"],
                    _normalize_text(fallback["excerpt"]),
                    _normalize_text(fallback["claim"]),
                )
                if key not in seen:
                    seen.add(key)
                    fallback["claim_id"] = f"{region.id_prefix}_c{claim_index:03d}"
                    claim_index += 1
                    accepted.append(fallback)
                    rejected.append(
                        {
                            "chunk_id": chunk.chunk_id,
                            "reason": "model_under_extracted_used_deterministic_fallback",
                            "span_id": fallback["span_id"],
                        }
                    )
    write_json(artifact_dir / "accepted_claims.json", {"claims": accepted, "rejected": rejected})
    return accepted, rejected


def _coverage_backfill_claims(
    *,
    all_chunks: list[SourceChunk],
    selected_chunks: list[SourceChunk],
    existing_claims: list[dict[str, Any]],
    id_prefix: str,
    profile_id: str = "general_decision_support",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected_ids = {chunk.chunk_id for chunk in selected_chunks}
    existing_keys = {
        (
            str(claim.get("source_id", "")),
            _normalize_text(str(claim.get("excerpt", ""))),
            _normalize_text(str(claim.get("claim", ""))),
        )
        for claim in existing_claims
    }
    next_index = _next_claim_index(existing_claims, id_prefix)
    backfilled: list[dict[str, Any]] = []
    skipped_chunk_ids: list[str] = []
    duplicate_chunk_ids: list[str] = []
    no_signal_chunk_ids: list[str] = []
    for chunk in all_chunks:
        if chunk.chunk_id in selected_ids:
            continue
        skipped_chunk_ids.append(chunk.chunk_id)
        fallback = _fallback_claim_for_chunk(chunk)
        if fallback is None:
            no_signal_chunk_ids.append(chunk.chunk_id)
            continue
        key = (
            fallback["source_id"],
            _normalize_text(fallback["excerpt"]),
            _normalize_text(fallback["claim"]),
        )
        if key in existing_keys:
            duplicate_chunk_ids.append(chunk.chunk_id)
            continue
        existing_keys.add(key)
        fallback["claim_id"] = f"{id_prefix}_c{next_index:03d}"
        next_index += 1
        fallback["extraction_method"] = "deterministic_coverage_backfill"
        fallback["coverage_backfill"] = {
            "chunk_id": chunk.chunk_id,
            "reason": "chunk_skipped_by_budget",
            "signal_score": _chunk_signal_score(chunk),
            "line_range": f"{chunk.start_line}-{chunk.end_line}",
        }
        backfilled.append(fallback)
    concept_backfilled, concept_report, next_index = _concept_gap_backfill_claims(
        all_chunks=all_chunks,
        existing_claims=[*existing_claims, *backfilled],
        existing_keys=existing_keys,
        id_prefix=id_prefix,
        next_index=next_index,
        profile_id=profile_id,
    )
    backfilled.extend(concept_backfilled)
    report = {
        "schema_id": "coverage_backfill_v1",
        "method": "deterministic_best_span_for_budget_skipped_chunks_plus_source_concept_gap_backfill",
        "skipped_chunk_count": len(skipped_chunk_ids),
        "backfilled_claim_count": len(backfilled),
        "skipped_chunk_backfilled_claim_count": len(backfilled) - len(concept_backfilled),
        "concept_gap_backfilled_claim_count": len(concept_backfilled),
        "duplicate_chunk_count": len(duplicate_chunk_ids),
        "no_signal_chunk_count": len(no_signal_chunk_ids),
        "backfilled_claim_ids": [claim["claim_id"] for claim in backfilled],
        "duplicate_chunk_ids": duplicate_chunk_ids[:50],
        "no_signal_chunk_ids": no_signal_chunk_ids[:50],
        "concept_gap_backfill": concept_report,
    }
    return backfilled, report


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
    for candidate in candidates:
        if len(backfilled) >= max_total:
            break
        family = str(candidate["family"])
        if family_counts.get(family, 0) >= max_per_family:
            continue
        span = candidate["span"]
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
) -> dict[str, Any]:
    if quality_report.get("status") == "usable_with_review":
        return {"ran": False, "accepted": False, "reason": "quality_already_usable"}
    prompt = _map_quality_repair_prompt(region, case_manifest, candidate_map, quality_report)
    prompt_path = artifact_dir / "map_quality_repair_prompt.txt"
    write_markdown(prompt_path, prompt)
    info: dict[str, Any] = {
        "ran": True,
        "accepted": False,
        "reason": "",
        "prompt_path": prompt_path,
    }
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
        )
        raw = result.text
    except (RuntimeError, ValueError) as exc:
        info["reason"] = "backend_error"
        info["error"] = str(exc)
        return info
    raw_path = artifact_dir / "map_quality_repair_raw.txt"
    write_markdown(raw_path, raw)
    info["raw_path"] = raw_path
    repaired = _parse_model_json(raw)
    canonical_path = artifact_dir / "map_quality_repaired_candidate.json"
    write_json(canonical_path, repaired or {})
    info["candidate_path"] = canonical_path
    if not isinstance(repaired, dict):
        info["reason"] = "invalid_json"
        return info
    validation_failures = validate_map_candidate(repo_root, manifest_path, region.region_id, canonical_path)
    write_json(artifact_dir / "map_quality_repair_validation.json", {"failures": validation_failures})
    info["validation_failures"] = validation_failures
    if validation_failures:
        info["reason"] = "validation_failed"
        return info
    repaired_quality = evaluate_staged_map_quality(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        selected_chunks=selected_chunks,
        skipped_chunks=skipped_chunks,
        candidate_map=repaired,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
    )
    write_json(artifact_dir / "map_quality_repaired_report.json", repaired_quality)
    write_markdown(artifact_dir / "MAP_QUALITY_REPAIRED_REPORT.md", _quality_markdown(repaired_quality))
    info["initial_status"] = quality_report.get("status")
    info["initial_score"] = quality_report.get("score")
    info["repaired_status"] = repaired_quality.get("status")
    info["repaired_score"] = repaired_quality.get("score")
    if not _repair_improves_or_preserves_quality(quality_report, repaired_quality):
        info["reason"] = "quality_not_improved_or_preserved"
        return info
    info["accepted"] = True
    info["reason"] = "accepted"
    info["candidate_map"] = repaired
    info["quality_report"] = repaired_quality
    return info


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
    summary = {
        key: value
        for key, value in repair_info.items()
        if key not in {"candidate_map", "quality_report"}
    }
    for key, value in list(summary.items()):
        if isinstance(value, Path):
            summary[key] = _relative(repo_root, value)
    return summary


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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if len(claims) < 2:
        return [], [], [{"reason": "too_few_claims"}]
    pair_packets = _candidate_relation_pairs(claims, max_relation_pairs)
    claim_ids = {claim["claim_id"] for claim in claims}
    permitted_types = manifest.relation_ontology.permitted_types()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    relation_index = 1

    for batch_index, batch in enumerate(_batches(pair_packets, relation_batch_size), start=1):
        batch_id = f"batch_{batch_index:03d}"
        prompt = (
            _relation_pair_prompt(manifest, region, case_manifest, batch[0])
            if len(batch) == 1
            else _relation_batch_prompt(manifest, region, case_manifest, batch, batch_id)
        )
        artifact_subdir = "relation_pairs" if len(batch) == 1 else "relation_batches"
        artifact_stem = batch[0]["pair_id"] if len(batch) == 1 else batch_id
        write_markdown(artifact_dir / artifact_subdir / f"{artifact_stem}_prompt.txt", prompt)
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
            )
            raw = result.text
        except (RuntimeError, ValueError) as exc:
            if len(batch) > 1:
                singleton_relations, singleton_payloads, singleton_rejected, relation_index = _classify_singleton_relations(
                    manifest=manifest,
                    region=region,
                    case_manifest=case_manifest,
                    batch=batch,
                    claim_ids=claim_ids,
                    permitted_types=permitted_types,
                    seen=seen,
                    relation_index=relation_index,
                    backend=backend,
                    backend_timeout=backend_timeout,
                    backend_retries=backend_retries,
                    artifact_dir=artifact_dir,
                    batch_id=batch_id,
                    batch_error=str(exc),
                )
                accepted.extend(singleton_relations)
                payloads.extend(singleton_payloads)
                rejected.extend(singleton_rejected)
                continue
            for packet in batch:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "backend_error", "error": str(exc)})
            continue
        write_markdown(artifact_dir / artifact_subdir / f"{artifact_stem}_raw.txt", raw)
        payload = _parse_model_json(raw)
        write_json(artifact_dir / artifact_subdir / f"{artifact_stem}_canonical.json", payload or {})
        if not isinstance(payload, dict):
            if len(batch) > 1:
                singleton_relations, singleton_payloads, singleton_rejected, relation_index = _classify_singleton_relations(
                    manifest=manifest,
                    region=region,
                    case_manifest=case_manifest,
                    batch=batch,
                    claim_ids=claim_ids,
                    permitted_types=permitted_types,
                    seen=seen,
                    relation_index=relation_index,
                    backend=backend,
                    backend_timeout=backend_timeout,
                    backend_retries=backend_retries,
                    artifact_dir=artifact_dir,
                    batch_id=batch_id,
                    batch_error="invalid_json",
                )
                accepted.extend(singleton_relations)
                payloads.extend(singleton_payloads)
                rejected.extend(singleton_rejected)
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
    if not accepted:
        fallback = _fallback_relation(pair_packets, permitted_types)
        if fallback is not None:
            fallback["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
            accepted.append(fallback)
            rejected.append(
                {
                    "reason": "model_under_related_used_deterministic_fallback",
                    "source_claim": fallback["source_claim"],
                    "target_claim": fallback["target_claim"],
                    "relation_type": fallback["relation_type"],
                }
            )
    write_json(artifact_dir / "accepted_relations.json", {"relations": accepted, "rejected": rejected})
    return accepted, payloads, rejected


def _classify_singleton_relations(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    batch: list[dict[str, Any]],
    claim_ids: set[str],
    permitted_types: set[str],
    seen: set[tuple[str, str, str]],
    relation_index: int,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    batch_id: str,
    batch_error: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    accepted: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = [
        {
            "batch_id": batch_id,
            "reason": "batch_failed_used_singleton_fallback",
            "error": batch_error,
            "pair_ids": [packet["pair_id"] for packet in batch],
        }
    ]
    for packet in batch:
        prompt = _relation_pair_prompt(manifest, region, case_manifest, packet)
        write_markdown(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_prompt.txt", prompt)
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
            )
            raw = result.text
        except (RuntimeError, ValueError) as exc:
            rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "backend_error", "error": str(exc)})
            continue
        write_markdown(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_raw.txt", raw)
        payload = _parse_model_json(raw)
        write_json(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_canonical.json", payload or {})
        if not isinstance(payload, dict):
            rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "invalid_json"})
            continue
        payloads.append(payload)
        proposals = _relation_proposals(payload)
        if not proposals:
            rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "missing_relation_proposal"})
            continue
        for proposal in proposals:
            relation, reason = _normalize_relation_proposal(proposal, claim_ids, permitted_types, packet)
            if relation is None:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": reason, "proposal": proposal})
                continue
            key = (relation["source_claim"], relation["target_claim"], relation["relation_type"])
            if key in seen:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "duplicate_relation", "proposal": proposal})
                continue
            seen.add(key)
            relation["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
            relation_index += 1
            accepted.append(relation)
            break
    return accepted, payloads, rejected, relation_index


def _sharpen_relations(
    relations: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    permitted_types: set[str],
) -> list[dict[str, Any]]:
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    sharpened: list[dict[str, Any]] = []
    for relation in relations:
        updated = dict(relation)
        original_type = str(updated.get("relation_type", ""))
        sharper_type = _sharper_relation_type(updated, claim_lookup, permitted_types)
        if sharper_type and sharper_type != original_type:
            updated["relation_type"] = sharper_type
            updated["rationale"] = _append_sharpening_note(
                str(updated.get("rationale", "")),
                original_type,
                sharper_type,
            )
            updated["deterministic_sharpening"] = {
                "from": original_type,
                "to": sharper_type,
                "method": "claim_role_and_rationale_rules_v1",
            }
        sharpened.append(updated)
    return sharpened


def _sharper_relation_type(
    relation: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
    permitted_types: set[str],
) -> str | None:
    current = str(relation.get("relation_type", ""))
    if current not in {"similar_to", "refines", "supports"}:
        return current
    source = claim_lookup.get(str(relation.get("source_claim")), {})
    target = claim_lookup.get(str(relation.get("target_claim")), {})
    source_role = str(source.get("role", ""))
    target_role = str(target.get("role", ""))
    rationale = str(relation.get("rationale", "")).lower()
    claim_text = " ".join((str(source.get("claim", "")), str(target.get("claim", "")))).lower()
    combined = f"{rationale} {claim_text}"
    if "depends_on" in permitted_types and (
        source_role == "implementation_constraint"
        or target_role == "implementation_constraint"
        or any(marker in combined for marker in ("requires", "only when", "if ", "unless", "depends", "must", "condition", "contingent", "when other", "where "))
    ):
        return "depends_on"
    if "in_tension_with" in permitted_types and any(
        marker in combined
        for marker in (
            "however",
            "unclear",
            "unproven",
            "cannot",
            "does not",
            "do not",
            "limitation",
            "small reductions",
            "not a solution",
            "not replace",
            "rather than",
            "scope limit",
            "tension",
        )
    ):
        return "in_tension_with"
    if "crux_for" in permitted_types and (
        source_role == "crux"
        or target_role == "crux"
        or any(marker in combined for marker in ("crux", "determines", "would change", "changes whether", "changes how", "turns on"))
    ):
        return "crux_for"
    if "challenges" in permitted_types and any(marker in combined for marker in ("contradicts", "undercuts", "weakens", "casts doubt")):
        return "challenges"
    return current


def _append_sharpening_note(rationale: str, original_type: str, sharper_type: str) -> str:
    base = rationale.strip()
    if not base:
        return f"Retagged from {original_type} to {sharper_type} because claim roles/rationale make the edge decision-relevant."
    return base


def _relation_sharpening_summary(relations: list[dict[str, Any]]) -> dict[str, Any]:
    changed = [
        {
            "relation_id": relation.get("relation_id"),
            "from": relation.get("deterministic_sharpening", {}).get("from"),
            "to": relation.get("deterministic_sharpening", {}).get("to"),
        }
        for relation in relations
        if isinstance(relation.get("deterministic_sharpening"), dict)
    ]
    return {"changed_count": len(changed), "changed": changed}


def _assemble_map(
    region: WorkedRegion,
    case_manifest: CaseManifest,
    claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    relation_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    cruxes = _payload_list_items(relation_payloads, "crux_candidates")
    if not cruxes and relations:
        cruxes = [
            f"{relations[0]['source_claim']} {relations[0]['relation_type']} {relations[0]['target_claim']} is a candidate crux for the question."
        ]
    distinctions = _payload_list_items(relation_payloads, "similar_but_not_identical")
    evidence_rows = [
        [
            f"Does {claim['claim_id']} quote exact source text?",
            "Survives",
            f"{claim['source_id']} {claim['source_span']}: {claim['excerpt']}",
        ]
        for claim in claims[: max(1, region.thresholds.min_evidence_rows)]
    ]
    return {
        "title": f"{case_manifest.title} Staged Map",
        "status": "human-review-needed",
        "prompt_procedure": MAP_PROMPT_VERSION,
        "pipeline": "staged_chunked_mapper_v1",
        "epistemic_config": {
            "profile_id": _case_config_profile(case_manifest).profile_id,
            "source": case_manifest.epistemic_config.get("source", "default_profile")
            if isinstance(case_manifest.epistemic_config, dict)
            else "default_profile",
        },
        "evidence_mode": "source_grounded",
        "sources": [source.source_id for source in _required_sources(case_manifest, region)],
        "claims": claims,
        "relations": relations,
        "crux_candidates": cruxes,
        "similar_but_not_identical": distinctions,
        "evidence_check": evidence_rows,
    }


def evaluate_staged_map_quality(
    *,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[SourceChunk],
    selected_chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    candidate_map: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
) -> dict[str, Any]:
    claims = [claim for claim in candidate_map.get("claims", []) if isinstance(claim, dict)]
    relations = [relation for relation in candidate_map.get("relations", []) if isinstance(relation, dict)]
    required_sources = [source.source_id for source in _required_sources(case_manifest, region)]
    source_claim_counts = {
        source_id: sum(1 for claim in claims if source_id in _claim_source_coverage_ids(claim))
        for source_id in required_sources
    }
    backfilled_claim_count = sum(
        1
        for claim in claims
        if str(claim.get("extraction_method", "")) == "deterministic_coverage_backfill"
    )
    consolidated_claim_count = sum(1 for claim in claims if claim.get("supporting_claim_ids"))
    role_counts = _counts(str(claim.get("role", "other")) for claim in claims)
    relation_type_counts = _counts(str(relation.get("relation_type", "")) for relation in relations)
    issues = _quality_issues(
        manifest=manifest,
        region=region,
        required_sources=required_sources,
        claims=claims,
        relations=relations,
        source_claim_counts=source_claim_counts,
        role_counts=role_counts,
        relation_type_counts=relation_type_counts,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
        skipped_chunks=skipped_chunks,
    )
    score = _quality_score(issues)
    status = _quality_status(issues, score)
    return {
        "schema_id": "staged_map_quality_report_v1",
        "status": status,
        "score": score,
        "summary": {
            "claim_count": len(claims),
            "relation_count": len(relations),
            "relation_type_count": len([key for key in relation_type_counts if key]),
            "required_source_count": len(required_sources),
            "sources_with_claims": sum(1 for count in source_claim_counts.values() if count > 0),
            "all_chunk_count": len(all_chunks),
            "selected_chunk_count": len(selected_chunks),
            "skipped_chunk_count": len(skipped_chunks),
            "coverage_backfilled_claim_count": backfilled_claim_count,
            "consolidated_claim_count": consolidated_claim_count,
            "rejected_claim_count": len(rejected_claims),
            "rejected_relation_count": len(rejected_relations),
        },
        "source_claim_counts": source_claim_counts,
        "claim_role_counts": role_counts,
        "relation_type_counts": relation_type_counts,
        "issues": issues,
        "scaffold": _map_quality_scaffold(manifest, region, case_manifest),
    }


def _quality_issues(
    *,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    required_sources: list[str],
    claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    source_claim_counts: dict[str, int],
    role_counts: dict[str, int],
    relation_type_counts: dict[str, int],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    skipped_chunks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not claims:
        issues.append(_quality_issue("fail", "missing_claims", "No accepted claims were produced."))
    if len(claims) < region.thresholds.min_claims:
        issues.append(
            _quality_issue(
                "risk",
                "low_claim_count",
                f"Accepted {len(claims)} claims; region target is at least {region.thresholds.min_claims}.",
            )
        )
    if len(claims) > region.thresholds.max_claims:
        issues.append(
            _quality_issue(
                "risk",
                "high_claim_count",
                f"Accepted {len(claims)} claims; region target is at most {region.thresholds.max_claims}.",
            )
        )
    missing_source_ids = [source_id for source_id, count in source_claim_counts.items() if count == 0]
    for source_id in missing_source_ids:
        issues.append(_quality_issue("fail", "missing_source_claim_coverage", f"No accepted claim from required source {source_id}."))
    uncertain_claims = [
        claim.get("claim_id", "")
        for claim in claims
        if str(claim.get("entailed_by_excerpt", "")) != "yes"
    ]
    if uncertain_claims:
        issues.append(
            _quality_issue(
                "risk",
                "uncertain_claim_entailment",
                "Claims not marked entailed by excerpt: " + ", ".join(str(item) for item in uncertain_claims[:8]),
            )
        )
    for role in ("conclusion_support", "crux", "scope_limit"):
        if role_counts.get(role, 0) == 0:
            issues.append(_quality_issue("risk", "missing_claim_role", f"No accepted claim with role {role}."))
    if len(claims) >= 2 and not relations:
        issues.append(_quality_issue("fail", "missing_relations", "At least two claims exist but no accepted relations were produced."))
    weak_relation_ids = _weak_relation_rationale_ids(relations)
    if weak_relation_ids:
        issues.append(
            _quality_issue(
                "risk",
                "weak_relation_rationales",
                "Relations with vague or low-information rationales: " + ", ".join(weak_relation_ids[:8]),
            )
        )
    if len(relation_type_counts) < region.thresholds.min_relation_types:
        issues.append(
            _quality_issue(
                "risk",
                "low_relation_type_diversity",
                f"Accepted {len(relation_type_counts)} relation types; region target is at least {region.thresholds.min_relation_types}.",
            )
        )
    relation_types = set(relation_type_counts)
    if relation_types.isdisjoint({"crux_for", "in_tension_with", "challenges"}):
        issues.append(_quality_issue("risk", "missing_crux_or_tension_relation", "No accepted crux/tension/challenge relation."))
    generic_relation_count = sum(relation_type_counts.get(kind, 0) for kind in ("similar_to", "refines", "supports"))
    if relations and len(relations) >= 4 and generic_relation_count / len(relations) > 0.7:
        issues.append(
            _quality_issue(
                "risk",
                "generic_relation_type_overuse",
                "Most accepted relations use generic supports/refines/similar_to types rather than crux, tension, challenge, or dependency edges.",
            )
        )
    duplicate_pairs = _near_duplicate_claim_pairs(claims)
    if duplicate_pairs:
        issues.append(
            _quality_issue(
                "risk",
                "near_duplicate_claims",
                "Near-duplicate claim pairs: " + ", ".join(f"{left}/{right}" for left, right in duplicate_pairs[:6]),
            )
        )
    permitted_types = manifest.relation_ontology.permitted_types()
    unsupported_relation_types = sorted(set(relation_type_counts) - permitted_types)
    for relation_type in unsupported_relation_types:
        issues.append(_quality_issue("fail", "unsupported_relation_type", f"Relation type is not in ontology: {relation_type}."))
    if rejected_claims and len(rejected_claims) > len(claims):
        issues.append(
            _quality_issue(
                "risk",
                "high_rejected_claim_ratio",
                f"Rejected {len(rejected_claims)} claim proposals vs. {len(claims)} accepted claims.",
            )
        )
    if rejected_relations and len(rejected_relations) > max(1, len(relations) * 2):
        issues.append(
            _quality_issue(
                "note",
                "high_rejected_relation_ratio",
                f"Rejected {len(rejected_relations)} relation proposals vs. {len(relations)} accepted relations.",
            )
        )
    if skipped_chunks:
        backfilled_claim_count = sum(
            1
            for claim in claims
            if str(claim.get("extraction_method", "")) == "deterministic_coverage_backfill"
        )
        if backfilled_claim_count:
            issues.append(
                _quality_issue(
                    "note",
                    "chunk_budget_backfilled_content",
                    f"Skipped {len(skipped_chunks)} source chunks due to configured chunk budgets; added {backfilled_claim_count} deterministic coverage claims.",
                )
            )
            return issues
        issues.append(
            _quality_issue(
                "note",
                "chunk_budget_skipped_content",
                f"Skipped {len(skipped_chunks)} source chunks due to configured chunk budgets.",
            )
        )
    return issues


def _quality_issue(severity: str, issue_type: str, message: str) -> dict[str, str]:
    return {"severity": severity, "issue_type": issue_type, "message": message}


def _claim_source_coverage_ids(claim: dict[str, Any]) -> set[str]:
    source_ids = {str(claim.get("source_id", ""))}
    for source_id in claim.get("supporting_sources", []):
        if isinstance(source_id, str):
            source_ids.add(source_id)
    return {source_id for source_id in source_ids if source_id}


def _weak_relation_rationale_ids(relations: list[dict[str, Any]]) -> list[str]:
    weak_ids: list[str] = []
    vague_patterns = (
        "are related",
        "is related",
        "should be read together",
        "provide context",
        "adds context",
        "similar points",
        "same topic",
        "both discuss",
    )
    for relation in relations:
        rationale = str(relation.get("rationale", "")).strip()
        normalized = re.sub(r"\s+", " ", rationale.lower())
        terms = _content_terms(normalized)
        if len(terms) < 4 or any(pattern in normalized for pattern in vague_patterns):
            weak_ids.append(str(relation.get("relation_id", "")) or "<missing_id>")
    return weak_ids


def _quality_score(issues: list[dict[str, str]]) -> int:
    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "fail":
            score -= 25
        elif severity == "risk":
            score -= 10
        elif severity == "note":
            score -= 2
    return max(0, score)


def _quality_status(issues: list[dict[str, str]], score: int) -> str:
    if any(issue.get("severity") == "fail" for issue in issues):
        return "needs_repair"
    if score < 75:
        return "review_recommended"
    return "usable_with_review"


def _quality_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Staged Map Quality Report",
        "",
        f"Status: `{report['status']}`",
        f"Score: `{report['score']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Issues", ""])
    issues = report.get("issues", [])
    if issues:
        lines.extend(
            f"- `{issue['severity']}` `{issue['issue_type']}`: {issue['message']}"
            for issue in issues
        )
    else:
        lines.append("- No deterministic map-quality issues detected.")
    lines.extend(["", "## Scaffold", "", "```json", json.dumps(report.get("scaffold", {}), indent=2), "```", ""])
    return "\n".join(lines)


def _map_quality_repair_prompt(
    region: WorkedRegion,
    case_manifest: CaseManifest,
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
) -> str:
    return "\n\n".join(
        (
            "You are repairing a source-grounded epistemic case-map candidate.",
            f"Region ID: {region.region_id}",
            f"Case question: {case_manifest.question}",
            "Return only JSON in the same map shape as the candidate.",
            "Repair rules:",
            "- Preserve accepted claims and relations that remain source-grounded.",
            "- Address fail/risk issues in the deterministic quality report before adding polish.",
            "- Add claims only when they are supported by exact excerpts already present in the candidate or staged artifacts.",
            "- Do not invent source IDs, claim IDs, relation IDs, source spans, excerpts, effect sizes, or consensus.",
            "- If a quality issue cannot be fixed from available artifacts, add an evidence_check row naming the missing source or review need.",
            "- Keep relation types within the allowed relation ontology listed in the scaffold.",
            "Deterministic quality report:\n" + json.dumps(quality_report, indent=2),
            "Candidate map:\n" + json.dumps(candidate_map, indent=2),
        )
    )


def _counts(items: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not item:
            continue
        counts[str(item)] = counts.get(str(item), 0) + 1
    return counts


def _near_duplicate_claim_pairs(claims: list[dict[str, Any]]) -> list[tuple[str, str]]:
    ids = [str(claim.get("claim_id", "")) for claim in claims]
    texts = [str(claim.get("claim", "") or claim.get("text", "")) for claim in claims]
    pair_scores = {
        (left, right): score
        for left, right, score in tfidf_near_duplicate_pairs(texts, ids, threshold=0.35)
        if left and right
    }
    for left_index, left in enumerate(claims):
        for right in claims[left_index + 1 :]:
            pair = (str(left.get("claim_id", "")), str(right.get("claim_id", "")))
            if _text_overlap_ratio(str(left.get("claim", "")), str(right.get("claim", ""))) >= 0.78:
                pair_scores.setdefault(pair, 1.0)
    return list(pair_scores)


def _case_config_profile(case_manifest: CaseManifest) -> EpistemicConfigProfile:
    return config_profile_from_manifest_payload(case_manifest.epistemic_config)


def _configured_claim_roles(case_manifest: CaseManifest) -> list[str]:
    roles = _case_config_profile(case_manifest).claim_role_ids()
    if "other" not in roles:
        roles.append("other")
    return roles


def _profile_relation_rule_text(case_manifest: CaseManifest) -> str:
    rules = _case_config_profile(case_manifest).relation_prompt_rules
    return "\n".join(f"- Profile guidance: {rule}" for rule in rules)


def _text_overlap_ratio(left: str, right: str) -> float:
    left_terms = _content_terms(left)
    right_terms = _content_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / min(len(left_terms), len(right_terms))


def _map_quality_scaffold(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    chunk: SourceChunk | None = None,
) -> dict[str, Any]:
    required_sources = _required_sources(case_manifest, region)
    profile = _case_config_profile(case_manifest)
    source_roles = {
        source.source_id: _source_role_scaffold(source)
        for source in required_sources
    }
    scaffold: dict[str, Any] = {
        "case_question": case_manifest.question,
        "epistemic_config_profile": {
            "profile_id": profile.profile_id,
            "label": profile.label,
            "description": profile.description,
        },
        "required_sources": [source.source_id for source in required_sources],
        "source_roles": source_roles,
        "source_role_taxonomy": [
            {
                "role_id": role.role_id,
                "description": role.description,
                "keyword_markers": role.keyword_markers,
                "limitations": role.limitations,
            }
            for role in profile.source_roles
        ],
        "target_claim_roles": [
            {"role_id": role.role_id, "description": role.description, "use_when": role.use_when}
            for role in profile.claim_roles
        ],
        "relation_goals": profile.relation_prompt_rules + [
            "connect at least one crux/scope-limit claim to a conclusion-support claim",
            "preserve tensions instead of flattening them",
            "use source limitations to bound claim strength",
            "prefer cross-source relations when they clarify disagreement or scope",
        ],
        "profile_evidence_sections": [
            {
                "section_id": section.section_id,
                "title": section.title,
                "description": section.description,
                "claim_roles": section.claim_roles,
                "relation_types": section.relation_types,
            }
            for section in profile.evidence_sections
        ],
        "profile_relation_types": [
            {
                "relation_type": relation.relation_type,
                "description": relation.description,
                "use_when": relation.use_when,
                "sharpness_markers": relation.sharpness_markers,
            }
            for relation in profile.relation_types
        ],
        "allowed_relation_types": sorted(manifest.relation_ontology.permitted_types()),
        "quality_checks": [
            "every required source should contribute at least one useful claim unless genuinely irrelevant",
            "claims must be entailed by exact excerpts",
            "relations must use only accepted claim IDs and ontology relation types",
            "the final map should expose cruxes, scope limits, and source-role boundaries",
            "near-duplicate claims should be merged or given distinct roles",
        ],
    }
    if chunk is not None:
        scaffold["current_chunk"] = {
            "chunk_id": chunk.chunk_id,
            "source_id": chunk.source_id,
            "line_range": f"{chunk.start_line}-{chunk.end_line}",
            "source_role": source_roles.get(chunk.source_id, {}),
        }
    return scaffold


def _source_role_scaffold(source: Source) -> dict[str, Any]:
    inferred_role, inferred_provenance, inferred_limitations = _infer_source_role(source)
    evidence_role = source.evidence_role if source.evidence_role != "unspecified" else inferred_role
    provenance_level = source.provenance_level if source.provenance_level != "unspecified" else inferred_provenance
    limitations = list(source.limitations)
    for limitation in inferred_limitations:
        if limitation not in limitations:
            limitations.append(limitation)
    return {
        "display_title": source.title,
        "evidence_role": evidence_role,
        "provenance_level": provenance_level,
        "limitations": limitations,
        "needs_upgrade": source.needs_upgrade or source.provenance_level == "unspecified",
        "inferred": source.evidence_role == "unspecified" or source.provenance_level == "unspecified",
    }


def _infer_source_role(source: Source) -> tuple[str, str, list[str]]:
    text = " ".join(
        str(part or "")
        for part in (source.source_id, source.title, source.source_type, source.notes, source.path, source.url)
    ).lower()
    if any(token in text for token in ("randomized", "rct", "trial", "cohort", "case-control", "study")):
        return "empirical study", "peer_reviewed", ["Check population, endpoint, and design limits before treating as direct decision evidence."]
    if any(token in text for token in ("meta-analysis", "systematic review", "scoping review", "review")):
        return "evidence synthesis", "secondary_summary", ["Review conclusions depend on included-study quality and inclusion criteria."]
    if any(token in text for token in ("guideline", "advisory", "recommendation", "official", "cdc", "who")):
        return "policy or guidance", "official_guidance", ["Guidance may combine evidence with policy judgment and may lag new evidence."]
    if any(token in text for token in ("forecast", "prediction", "good judgment")):
        return "forecasting aggregate", "secondary_summary", ["Forecasts summarize expectations, not direct causal evidence."]
    if any(token in text for token in ("brief", "blog", "comment", "acx", "rootclaim", "analysis")):
        return "commentary or case analysis", "secondary_summary", ["Use for framing and argument structure; verify factual claims against primary sources."]
    if any(token in text for token in ("working paper", "preprint", "nber", "ssrn")):
        return "working paper or preprint", "preprint", ["Treat as not fully peer-reviewed unless separately verified."]
    return "source document", "unspecified", ["Source role was inferred from sparse metadata and needs human review."]


def _payload_list_items(payloads: list[dict[str, Any]], key: str) -> list[str]:
    items: list[str] = []
    for payload in payloads:
        direct = payload.get(key, [])
        if isinstance(direct, list):
            items.extend(str(item) for item in direct)
        for proposal in _relation_proposals(payload):
            nested = proposal.get(key, [])
            if isinstance(nested, list):
                items.extend(str(item) for item in nested)
    return items


def _claim_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    chunk: SourceChunk,
    max_claims: int,
) -> str:
    span_catalog = "\n".join(
        f"- span_id: {span.span_id}\n  source_span: {span.source_span}\n  text: {span.text}"
        for span in chunk.spans
    )
    scaffold = json.dumps(_map_quality_scaffold(manifest, region, case_manifest, chunk), indent=2)
    role_options = "|".join(_configured_claim_roles(case_manifest))
    return f"""You are selecting source-grounded claim candidates from one bounded source-span catalog.

Prompt version: {CLAIM_EXTRACTION_PROMPT_VERSION}
Region ID: {region.region_id}
Case question: {case_manifest.question}
Source ID: {chunk.source_id}
Source title: {chunk.title}
Line range: {chunk.start_line}-{chunk.end_line}

Source span catalog:
{span_catalog}

Deterministic map-quality scaffold:
{scaffold}

Return only JSON:
{{
  "claims": [
    {{
      "claim": "one concise claim supported by the excerpt",
      "span_id": "one span_id from the catalog",
      "entailed_by_excerpt": "yes|no|uncertain",
      "role": "{role_options}"
    }}
  ]
}}

Rules:
- Return at most {max_claims} claims.
- Do not include claim_id. Deterministic code assigns IDs later.
- Do not include source_id, source_span, or excerpt. Deterministic code derives them from span_id.
- Use only span IDs shown in the catalog.
- Prefer claims that affect the case question, not bibliographic metadata.
- Use the map-quality scaffold to diversify claim roles and preserve source limitations.
- If a source limitation changes how the question should be answered, use the sharpest configured role such as scope_limit, implementation_constraint, external_validity, residual_risk, or jurisdictional_constraint when available.
- If the chunk has no useful claim, return {{"claims": []}}.
"""


def _relation_pair_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    packet: dict[str, Any],
) -> str:
    left = packet["left"]
    right = packet["right"]
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
    scaffold = json.dumps(_map_quality_scaffold(manifest, region, case_manifest), indent=2)
    profile_rules = _profile_relation_rule_text(case_manifest)
    return f"""You are classifying one possible relation between two already-validated claim cards.

Prompt version: {RELATION_PROMPT_VERSION}
Region ID: {region.region_id}
Pair ID: {packet['pair_id']}
Case question: {case_manifest.question}

Allowed relation types:
{relation_types}

Claim A:
- claim_id: {left['claim_id']}
- claim: {left['claim']}
- source_id: {left['source_id']}
- role: {left['role']}
- excerpt: {left['excerpt']}

Claim B:
- claim_id: {right['claim_id']}
- claim: {right['claim']}
- source_id: {right['source_id']}
- role: {right['role']}
- excerpt: {right['excerpt']}

Deterministic map-quality scaffold:
{scaffold}

Return only JSON:
{{
  "pair_id": "{packet['pair_id']}",
  "source_claim": "claim_id or null",
  "target_claim": "claim_id or null",
  "relation_type": "one allowed relation type or none",
  "rationale": "why this edge improves reasoning without overstating support, or why no edge is warranted",
  "crux_candidates": ["crux text naming claim IDs"],
  "similar_but_not_identical": ["distinction text naming claim IDs"]
}}

Rules:
- Do not include relation_id. Deterministic code assigns IDs later.
- Use only the two claim IDs shown above.
- Use only allowed relation types, or use relation_type "none".
- Use the map-quality scaffold to preserve cruxes, tensions, source limitations, and scope boundaries.
- Prefer decision-relevant relations over generic ones: use crux_for when one claim would change the decision read of the other, depends_on when a recommendation only works under a condition, and in_tension_with/challenges when a scope limit or contrary finding weakens a support claim.
{profile_rules}
- Use similar_to only when the claims are redundant enough that a reviewer could merge them.
- Use refines only when the rationale names the exact boundary, population, endpoint, mechanism, or implementation condition being refined.
- If no defensible relation exists, set source_claim and target_claim to null and relation_type to "none".
"""


def _relation_batch_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    packets: list[dict[str, Any]],
    batch_id: str,
) -> str:
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
    pair_blocks = "\n\n".join(_relation_pair_block(packet) for packet in packets)
    pair_ids = ", ".join(packet["pair_id"] for packet in packets)
    scaffold = json.dumps(_map_quality_scaffold(manifest, region, case_manifest), indent=2)
    profile_rules = _profile_relation_rule_text(case_manifest)
    return f"""You are classifying possible relations between already-validated claim cards.

Prompt version: {RELATION_BATCH_PROMPT_VERSION}
Region ID: {region.region_id}
Batch ID: {batch_id}
Case question: {case_manifest.question}

Allowed relation types:
{relation_types}

Pairs to classify:
{pair_blocks}

Deterministic map-quality scaffold:
{scaffold}

Return only JSON:
{{
  "relations": [
    {{
      "pair_id": "one of: {pair_ids}",
      "source_claim": "claim_id or null",
      "target_claim": "claim_id or null",
      "relation_type": "one allowed relation type or none",
      "rationale": "why this edge improves reasoning without overstating support, or why no edge is warranted",
      "crux_candidates": ["crux text naming claim IDs"],
      "similar_but_not_identical": ["distinction text naming claim IDs"]
    }}
  ]
}}

Rules:
- Return exactly one object for each pair ID in this batch.
- Do not include relation_id. Deterministic code assigns IDs later.
- Use only the two claim IDs shown for each pair.
- Use only allowed relation types, or use relation_type "none".
- Use the map-quality scaffold to preserve cruxes, tensions, source limitations, and scope boundaries.
- Prefer decision-relevant relations over generic ones: use crux_for when one claim would change the decision read of the other, depends_on when a recommendation only works under a condition, and in_tension_with/challenges when a scope limit or contrary finding weakens a support claim.
{profile_rules}
- Use similar_to only when the claims are redundant enough that a reviewer could merge them.
- Use refines only when the rationale names the exact boundary, population, endpoint, mechanism, or implementation condition being refined.
- If no defensible relation exists for a pair, set source_claim and target_claim to null and relation_type to "none".
"""


def _relation_pair_block(packet: dict[str, Any]) -> str:
    left = packet["left"]
    right = packet["right"]
    return f"""Pair ID: {packet['pair_id']}
Claim A:
- claim_id: {left['claim_id']}
- claim: {left['claim']}
- source_id: {left['source_id']}
- role: {left['role']}
- excerpt: {left['excerpt']}

Claim B:
- claim_id: {right['claim_id']}
- claim: {right['claim']}
- source_id: {right['source_id']}
- role: {right['role']}
- excerpt: {right['excerpt']}"""


def _normalize_claim_proposal(
    proposal: Any,
    span_lookup: dict[str, SourceSpan],
    valid_roles: set[str] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(proposal, dict):
        return None, "claim_not_object"
    span_id = str(proposal.get("span_id", proposal.get("spanId", ""))).strip()
    if span_id not in span_lookup:
        return None, "unknown_span_id"
    span = span_lookup[span_id]
    claim_text = str(proposal.get("claim", "")).strip()
    if not claim_text:
        return None, "missing_claim"
    entailed = str(proposal.get("entailed_by_excerpt", "uncertain")).strip().lower()
    if entailed not in VALID_ENTAILMENT:
        entailed = "uncertain"
    role = str(proposal.get("role", "other")).strip()
    allowed_roles = valid_roles or VALID_CLAIM_ROLES
    if role not in allowed_roles:
        role = "other"
    if role not in allowed_roles:
        role = sorted(allowed_roles)[0] if allowed_roles else "other"
    return (
        {
            "claim_id": "",
            "claim": claim_text,
            "source_id": span.source_id,
            "source_span": span.source_span,
            "excerpt": span.text,
            "entailed_by_excerpt": entailed,
            "role": role,
        },
        "",
    )


def _fallback_claim_for_chunk(chunk: SourceChunk) -> dict[str, Any] | None:
    span = _best_fallback_span(chunk)
    if span is None:
        return None
    return {
        "claim_id": "",
        "claim": span.text,
        "source_id": span.source_id,
        "source_span": span.source_span,
        "excerpt": span.text,
        "entailed_by_excerpt": "yes",
        "role": _fallback_role(span.text),
        "span_id": span.span_id,
        "extraction_method": "deterministic_fallback_span",
    }


def _best_fallback_span(chunk: SourceChunk) -> SourceSpan | None:
    candidates = [span for span in chunk.spans if _span_signal_score(span.text) > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda span: (_span_signal_score(span.text), len(span.text)))


def _span_signal_score(text: str) -> int:
    stripped = text.strip()
    lowered = stripped.lower()
    if not stripped or stripped.startswith("#"):
        return 0
    if lowered.startswith(("source:", "author:", "date:", "retrieved:", "use in worked region:")):
        return 0
    score = 1
    for marker in (
        "%",
        "odds",
        "bayes",
        "favor",
        "likely",
        "disagreement",
        "challenge",
        "critique",
        "not measure",
        "limitation",
        "failed",
        "won",
        "risk",
        "could",
    ):
        if marker in lowered:
            score += 2
    return score


def _fallback_role(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("not measure", "not peer reviewed", "limitation", "failed", "risk")):
        return "scope_limit"
    if any(marker in lowered for marker in ("disagreement", "critique", "challenge")):
        return "crux"
    if any(marker in lowered for marker in ("favor", "likely", "%", "odds")):
        return "conclusion_support"
    return "background"


def _normalize_relation_proposal(
    proposal: Any,
    claim_ids: set[str],
    permitted_types: set[str],
    packet: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(proposal, dict):
        return None, "relation_not_object"
    if str(proposal.get("pair_id", packet["pair_id"])).strip() != packet["pair_id"]:
        return None, "wrong_pair_id"
    source_claim = str(proposal.get("source_claim", "")).strip()
    target_claim = str(proposal.get("target_claim", "")).strip()
    relation_type = str(proposal.get("relation_type", "")).strip()
    rationale = str(proposal.get("rationale", "")).strip()
    if relation_type == "none":
        return None, "no_relation"
    if source_claim not in claim_ids or target_claim not in claim_ids:
        return None, "unknown_endpoint"
    packet_ids = {packet["left"]["claim_id"], packet["right"]["claim_id"]}
    if source_claim not in packet_ids or target_claim not in packet_ids:
        return None, "endpoint_not_in_pair"
    if source_claim == target_claim:
        return None, "self_relation"
    if relation_type not in permitted_types:
        return None, "unknown_relation_type"
    if not rationale:
        return None, "missing_rationale"
    return (
        {
            "relation_id": "",
            "source_claim": source_claim,
            "target_claim": target_claim,
            "relation_type": relation_type,
            "rationale": rationale,
        },
        "",
    )


def _candidate_relation_pairs(claims: list[dict[str, Any]], max_pairs: int) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, int, dict[str, Any], dict[str, Any]]] = []
    for left_index, left in enumerate(claims):
        for right_index, right in enumerate(claims):
            if left_index >= right_index:
                continue
            score = _pair_score(left, right)
            if score <= 0:
                continue
            scored.append((score, left_index, right_index, left, right))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    packets = []
    for index, (_score, _left_index, _right_index, left, right) in enumerate(scored[:max_pairs], start=1):
        packets.append({"pair_id": f"pair_{index:03d}", "left": left, "right": right})
    return packets


def _fallback_relation(pair_packets: list[dict[str, Any]], permitted_types: set[str]) -> dict[str, Any] | None:
    if not pair_packets:
        return None
    packet = pair_packets[0]
    left = packet["left"]
    right = packet["right"]
    relation_type = _fallback_relation_type(left, right, permitted_types)
    if relation_type is None:
        return None
    return {
        "relation_id": "",
        "source_claim": left["claim_id"],
        "target_claim": right["claim_id"],
        "relation_type": relation_type,
        "rationale": (
            "Deterministic fallback edge: these high-priority cross-source claims were selected as a likely "
            "reasoning dependency after model relation classification produced no accepted edge. Human review "
            "should confirm the exact relation type before treating it as substantive."
        ),
        "extraction_method": "deterministic_fallback_pair",
    }


def _fallback_relation_type(left: dict[str, Any], right: dict[str, Any], permitted_types: set[str]) -> str | None:
    left_text = _normalize_text(f"{left.get('claim', '')} {left.get('excerpt', '')}")
    right_text = _normalize_text(f"{right.get('claim', '')} {right.get('excerpt', '')}")
    combined = f"{left_text} {right_text}"
    if "in_tension_with" in permitted_types and _looks_like_tension(left_text, right_text):
        return "in_tension_with"
    if "challenges" in permitted_types and any(
        marker in combined
        for marker in (
            "flawed",
            "no evidence",
            "not require",
            "without requiring",
            "critique",
            "reject",
            "failed",
        )
    ):
        return "challenges"
    if "crux_for" in permitted_types and {left.get("role"), right.get("role")} & {"crux"}:
        return "crux_for"
    if "refines" in permitted_types:
        return "refines"
    return next(iter(sorted(permitted_types)), None)


def _looks_like_tension(left_text: str, right_text: str) -> bool:
    lab_markers = ("lab leak", "research-related accident", "accidental lab")
    zoonosis_markers = ("zoonosis", "zoonotic", "natural")
    lab_left = any(marker in left_text for marker in lab_markers)
    lab_right = any(marker in right_text for marker in lab_markers)
    zoonosis_left = any(marker in left_text for marker in zoonosis_markers)
    zoonosis_right = any(marker in right_text for marker in zoonosis_markers)
    return (lab_left and zoonosis_right) or (lab_right and zoonosis_left)


def _pair_score(left: dict[str, Any], right: dict[str, Any]) -> int:
    score = 0
    if left.get("source_id") != right.get("source_id"):
        score += 3
    left_role = str(left.get("role", ""))
    right_role = str(right.get("role", ""))
    if "crux" in {left_role, right_role}:
        score += 4
    if {left_role, right_role} & {"scope_limit", "implementation_constraint"}:
        score += 3
    if {left_role, right_role} & {"conclusion_support"}:
        score += 2
    shared_terms = _content_terms(str(left.get("claim", ""))) & _content_terms(str(right.get("claim", "")))
    score += min(3, len(shared_terms))
    return score


def _content_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "but",
        "for",
        "from",
        "has",
        "have",
        "into",
        "not",
        "that",
        "the",
        "their",
        "this",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]{4,}", text.lower())
        if token not in stopwords
    }


def _source_chunks(
    repo_root: Path,
    case_manifest: CaseManifest,
    region: WorkedRegion,
    chunk_lines: int,
    chunk_overlap_lines: int,
) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    ordinal = 0
    step = max(1, chunk_lines - chunk_overlap_lines)
    for source in _required_sources(case_manifest, region):
        lines = _source_text(repo_root, source).splitlines()
        if not lines:
            continue
        for start in range(0, len(lines), step):
            selected = lines[start : start + chunk_lines]
            if not selected:
                continue
            start_line = start + 1
            end_line = start + len(selected)
            chunk_id = f"{source.source_id}_lines_{start_line}_{end_line}"
            numbered = "\n".join(f"{line_no}: {line}" for line_no, line in enumerate(selected, start=start_line))
            spans = tuple(
                SourceSpan(
                    span_id=f"{_safe_filename(source.source_id)}_s{line_no:04d}",
                    source_id=source.source_id,
                    source_span=f"lines {line_no}-{line_no}",
                    text=line.strip(),
                )
                for line_no, line in enumerate(selected, start=start_line)
                if line.strip()
            )
            ordinal += 1
            chunks.append(
                SourceChunk(
                    chunk_id=_safe_filename(chunk_id),
                    source_id=source.source_id,
                    title=source.title,
                    start_line=start_line,
                    end_line=end_line,
                    ordinal=ordinal,
                    numbered_text=numbered,
                    plain_text="\n".join(selected),
                    spans=spans,
                )
            )
    return chunks


def _chunk_summary(chunk: SourceChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "title": chunk.title,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "ordinal": chunk.ordinal,
        "signal_score": _chunk_signal_score(chunk),
        "span_count": len(chunk.spans),
        "spans": [span.__dict__ for span in chunk.spans],
    }


def _budget_chunks(
    chunks: list[SourceChunk],
    max_chunks_per_source: int | None,
    max_total_chunks: int | None,
) -> tuple[list[SourceChunk], list[dict[str, Any]]]:
    selected = list(chunks)
    skipped: list[dict[str, Any]] = []
    if max_chunks_per_source is not None:
        selected_ids: set[str] = set()
        by_source: dict[str, list[SourceChunk]] = {}
        for chunk in selected:
            by_source.setdefault(chunk.source_id, []).append(chunk)
        for source_chunks in by_source.values():
            ranked = sorted(source_chunks, key=_chunk_priority)
            kept = set(ranked[:max_chunks_per_source])
            selected_ids.update(chunk.chunk_id for chunk in kept)
            for chunk in source_chunks:
                if chunk not in kept:
                    skipped.append(_skipped_chunk_summary(chunk, "max_chunks_per_source"))
        selected = [chunk for chunk in selected if chunk.chunk_id in selected_ids]
    if max_total_chunks is not None and len(selected) > max_total_chunks:
        selected_set = _select_total_budget(selected, max_total_chunks)
        for chunk in selected:
            if chunk.chunk_id not in selected_set:
                skipped.append(_skipped_chunk_summary(chunk, "max_total_chunks"))
        selected = [chunk for chunk in selected if chunk.chunk_id in selected_set]
    selected.sort(key=lambda chunk: chunk.ordinal)
    skipped.sort(key=lambda item: int(item["ordinal"]))
    return selected, skipped


def _select_total_budget(chunks: list[SourceChunk], max_total_chunks: int) -> set[str]:
    by_source: dict[str, list[SourceChunk]] = {}
    for chunk in chunks:
        by_source.setdefault(chunk.source_id, []).append(chunk)
    if max_total_chunks < len(by_source):
        return {chunk.chunk_id for chunk in sorted(chunks, key=_chunk_priority)[:max_total_chunks]}
    selected_order: list[str] = []
    selected: set[str] = set()
    for source_chunks in sorted(by_source.values(), key=lambda items: min(chunk.ordinal for chunk in items)):
        if len(selected) >= max_total_chunks:
            break
        chunk_id = min(source_chunks, key=_chunk_priority).chunk_id
        selected.add(chunk_id)
        selected_order.append(chunk_id)
    if len(selected) >= max_total_chunks:
        return set(selected_order[:max_total_chunks])
    for chunk in sorted(chunks, key=_chunk_priority):
        if len(selected) >= max_total_chunks:
            break
        if chunk.chunk_id not in selected:
            selected.add(chunk.chunk_id)
            selected_order.append(chunk.chunk_id)
    return selected


def _skipped_chunk_summary(chunk: SourceChunk, reason: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "ordinal": chunk.ordinal,
        "signal_score": _chunk_signal_score(chunk),
        "span_count": len(chunk.spans),
        "reason": reason,
    }


def _chunk_priority(chunk: SourceChunk) -> tuple[int, int, int]:
    return (-_chunk_signal_score(chunk), -len(chunk.spans), chunk.ordinal)


def _chunk_signal_score(chunk: SourceChunk) -> int:
    return sum(_span_signal_score(span.text) for span in chunk.spans)


def _parse_model_json(text: str) -> dict[str, Any] | list[Any] | None:
    canonical = canonical_json_output(text)
    try:
        return json.loads(canonical)
    except json.JSONDecodeError:
        return None


def _relation_proposals(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "pair_id" in payload:
        return [payload]
    proposals = payload.get("relations", [])
    if isinstance(proposals, list):
        return [proposal for proposal in proposals if isinstance(proposal, dict)]
    return []


def _batches(items: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _relation_batch_count(max_relation_pairs: int, relation_batch_size: int, claims: list[dict[str, Any]]) -> int:
    if len(claims) < 2:
        return 0
    pair_count = len(_candidate_relation_pairs(claims, max_relation_pairs))
    if pair_count == 0:
        return 0
    return (pair_count + relation_batch_size - 1) // relation_batch_size


def _line_span_for_excerpt(chunk: SourceChunk, excerpt: str) -> str:
    chunk_lines = chunk.plain_text.splitlines()
    for offset, line in enumerate(chunk_lines):
        if excerpt in line:
            line_no = chunk.start_line + offset
            return f"lines {line_no}-{line_no}"
    return f"lines {chunk.start_line}-{chunk.end_line}"


def _excerpt_from_source_span(chunk: SourceChunk, source_span: str) -> str | None:
    match = re.search(r"lines?\s+(\d+)(?:\s*-\s*(\d+))?", source_span)
    if not match:
        return None
    start_line = int(match.group(1))
    end_line = int(match.group(2) or match.group(1))
    if start_line < chunk.start_line or end_line > chunk.end_line or end_line < start_line:
        return None
    lines = chunk.plain_text.splitlines()
    start_index = start_line - chunk.start_line
    end_index = end_line - chunk.start_line + 1
    excerpt = "\n".join(lines[start_index:end_index]).strip()
    return excerpt or None


def _load_context(repo_root: Path, manifest_path: str, region_id: str) -> tuple[SubmissionManifest, WorkedRegion, CaseManifest]:
    manifest = load_submission_manifest(repo_root, manifest_path)
    region = manifest.region_for_id(region_id)
    case = manifest.case_for_key(region.case_key)
    case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    return manifest, region, case_manifest


def _required_sources(case_manifest: CaseManifest, region: WorkedRegion) -> list[Source]:
    if not region.required_sources:
        return case_manifest.sources
    lookup = {source.source_id: source for source in case_manifest.sources}
    return [lookup[source_id] for source_id in region.required_sources if source_id in lookup]


def _source_text(repo_root: Path, source: Source) -> str:
    if source.text:
        return source.text
    if source.path:
        path = repo_root / source.path
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return source.excerpt or source.notes or ""


def _artifact_dir(repo_root: Path, region_id: str, artifact_dir: str | Path | None) -> Path:
    path = Path(artifact_dir or f"artifacts/semantic/{region_id}/staged")
    if not path.is_absolute():
        path = repo_root / path
    return path


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()
