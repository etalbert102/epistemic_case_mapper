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
from epistemic_case_mapper.staged_semantic_claim_cache import claim_payload_for_chunk, write_claim_progress
from epistemic_case_mapper.staged_semantic_decision_questions import claim_decision_relevance_rejection_reason, region_decision_question
from epistemic_case_mapper.staged_semantic_langextract import langextract_claim_payload_for_chunk
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest

CLAIM_EXTRACTION_PROMPT_VERSION = "staged_claim_extraction_prompt_v1_json"

RELATION_PROMPT_VERSION = "staged_relation_prompt_v2_contract_json"

RELATION_BATCH_PROMPT_VERSION = "staged_relation_batch_prompt_v2_contract_json"

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
    reuse_claim_cache: bool = True,
    claim_extractor: str = "native",
    decision_question: str | None = None,
) -> StagedMapResult:
    _validate_staged_map_options(
        chunk_lines=chunk_lines,
        chunk_overlap_lines=chunk_overlap_lines,
        max_chunks_per_source=max_chunks_per_source,
        max_total_chunks=max_total_chunks,
        claim_extractor=claim_extractor,
        relation_batch_size=relation_batch_size,
    )
    manifest, region, case_manifest = _load_context(repo_root, manifest_path, region_id)
    artifacts = _artifact_dir(repo_root, region_id, artifact_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    config_profile = _case_config_profile(case_manifest)
    selected_decision_question = region_decision_question(region, case_manifest, decision_question)

    all_chunks = _source_chunks(repo_root, case_manifest, region, chunk_lines, chunk_overlap_lines)
    chunks, skipped_chunks = _budget_chunks(all_chunks, max_chunks_per_source, max_total_chunks)
    claim_stage = _extract_consolidated_claims(
        repo_root=repo_root,
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        chunks=chunks,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifacts=artifacts,
        max_claims_per_chunk=max_claims_per_chunk,
        config_profile_id=config_profile.profile_id,
        reuse_claim_cache=reuse_claim_cache,
        claim_extractor=claim_extractor,
        decision_question=selected_decision_question,
    )
    claims = claim_stage["claims"]
    rejected_claims = claim_stage["rejected_claims"]
    initial_map_stage = _build_initial_staged_map(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        claims=claims,
        all_chunks=all_chunks,
        chunks=chunks,
        skipped_chunks=skipped_chunks,
        rejected_claims=rejected_claims,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifacts=artifacts,
        max_relation_pairs=max_relation_pairs,
        relation_batch_size=relation_batch_size,
        decision_question=selected_decision_question,
    )
    relations = initial_map_stage["relations"]
    rejected_relations = initial_map_stage["rejected_relations"]
    final_map = initial_map_stage["final_map"]
    quality_report = initial_map_stage["quality_report"]
    repair_stage = _maybe_repair_staged_map_quality(
        repair_quality=repair_quality,
        repo_root=repo_root,
        manifest_path=manifest_path,
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        chunks=chunks,
        skipped_chunks=skipped_chunks,
        final_map=final_map,
        quality_report=quality_report,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifacts=artifacts,
        decision_question=selected_decision_question,
    )
    final_map = repair_stage["final_map"]
    quality_report = repair_stage["quality_report"]
    repair_info = repair_stage["repair_info"]
    final_outputs = _write_staged_map_outputs(
        repo_root=repo_root,
        manifest_path=manifest_path,
        region_id=region_id,
        region=region,
        case_manifest=case_manifest,
        artifacts=artifacts,
        output_path=output_path,
        final_map=final_map,
        quality_report=quality_report,
        validate=validate,
        decision_question=selected_decision_question,
    )
    _write_staged_run_summary(
        repo_root=repo_root, region=region, backend=backend, decision_question=selected_decision_question,
        chunk_lines=chunk_lines, chunk_overlap_lines=chunk_overlap_lines,
        max_chunks_per_source=max_chunks_per_source, max_total_chunks=max_total_chunks,
        max_claims_per_chunk=max_claims_per_chunk, claim_extractor=claim_extractor,
        max_relation_pairs=max_relation_pairs, relation_batch_size=relation_batch_size,
        backend_timeout=backend_timeout, backend_retries=backend_retries,
        config_profile_id=config_profile.profile_id,
        all_chunks=all_chunks, chunks=chunks, skipped_chunks=skipped_chunks,
        claim_stage=claim_stage, claims=claims, relations=relations, final_outputs=final_outputs,
        rejected_claims=rejected_claims, rejected_relations=rejected_relations,
        quality_report=quality_report, repair_info=repair_info, artifacts=artifacts,
    )
    return _staged_map_result(
        final_outputs=final_outputs, artifacts=artifacts, rejected_claims=rejected_claims,
        rejected_relations=rejected_relations, quality_report=quality_report, repair_info=repair_info,
    )

def _staged_map_result(
    *,
    final_outputs: dict[str, Any],
    artifacts: Path,
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    quality_report: dict[str, Any],
    repair_info: dict[str, Any],
) -> StagedMapResult:
    return StagedMapResult(
        output_path=final_outputs["target"],
        artifact_dir=artifacts,
        claim_count=len(final_outputs["final_claims"]),
        relation_count=len(final_outputs["final_relations"]),
        rejected_claim_count=len(rejected_claims),
        rejected_relation_count=len(rejected_relations),
        failures=tuple(final_outputs["failures"]),
        quality_status=str(quality_report["status"]),
        quality_repair_ran=bool(repair_info.get("ran")),
        quality_repaired=bool(repair_info.get("accepted")),
    )

def _validate_staged_map_options(
    *,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int | None,
    max_total_chunks: int | None,
    claim_extractor: str,
    relation_batch_size: int,
) -> None:
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
    if claim_extractor not in {"native", "langextract"}:
        raise ValueError("claim_extractor must be native or langextract")

def _write_staged_run_summary(
    *,
    repo_root: Path,
    region: WorkedRegion,
    backend: str,
    decision_question: str,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int | None,
    max_total_chunks: int | None,
    max_claims_per_chunk: int,
    claim_extractor: str,
    max_relation_pairs: int,
    relation_batch_size: int,
    backend_timeout: int | None,
    backend_retries: int,
    config_profile_id: str,
    all_chunks: list[SourceChunk],
    chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    claim_stage: dict[str, Any],
    claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    final_outputs: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    quality_report: dict[str, Any],
    repair_info: dict[str, Any],
    artifacts: Path,
) -> None:
    write_json(
        artifacts / "run_summary.json",
        _staged_run_summary(
            repo_root=repo_root,
            region=region,
            backend=backend,
            decision_question=decision_question,
            chunk_lines=chunk_lines,
            chunk_overlap_lines=chunk_overlap_lines,
            max_chunks_per_source=max_chunks_per_source,
            max_total_chunks=max_total_chunks,
            max_claims_per_chunk=max_claims_per_chunk,
            claim_extractor=claim_extractor,
            max_relation_pairs=max_relation_pairs,
            relation_batch_size=relation_batch_size,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            config_profile_id=config_profile_id,
            all_chunks=all_chunks,
            chunks=chunks,
            skipped_chunks=skipped_chunks,
            coverage_report=claim_stage["coverage_report"],
            consolidation_report=claim_stage["consolidation_report"],
            llm_claim_count=claim_stage["llm_claim_count"],
            coverage_claims=claim_stage["coverage_claims"],
            pre_consolidation_claim_count=claim_stage["pre_consolidation_claim_count"],
            claims=claims,
            relations=relations,
            final_claims=final_outputs["final_claims"],
            final_relations=final_outputs["final_relations"],
            rejected_claims=rejected_claims,
            rejected_relations=rejected_relations,
            validation_target=final_outputs["validation_target"],
            target=final_outputs["target"],
            failures=final_outputs["failures"],
            quality_report=quality_report,
            repair_info=repair_info,
            artifacts=artifacts,
        ),
    )

def _extract_consolidated_claims(
    *,
    repo_root: Path,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[SourceChunk],
    chunks: list[SourceChunk],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifacts: Path,
    max_claims_per_chunk: int,
    config_profile_id: str,
    reuse_claim_cache: bool,
    claim_extractor: str,
    decision_question: str,
) -> dict[str, Any]:
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
        reuse_claim_cache=reuse_claim_cache,
        claim_extractor=claim_extractor,
        decision_question=decision_question,
    )
    llm_claim_count = len(claims)
    coverage_claims, coverage_report = _coverage_backfill_claims(
        all_chunks=all_chunks,
        selected_chunks=chunks,
        existing_claims=claims,
        id_prefix=region.id_prefix,
        profile_id=config_profile_id,
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
    return {
        "claims": claims,
        "rejected_claims": rejected_claims,
        "coverage_report": coverage_report,
        "consolidation_report": consolidation_report,
        "llm_claim_count": llm_claim_count,
        "coverage_claims": coverage_claims,
        "pre_consolidation_claim_count": pre_consolidation_claim_count,
    }

def _maybe_repair_staged_map_quality(
    *,
    repair_quality: bool,
    repo_root: Path,
    manifest_path: str,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[SourceChunk],
    chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    final_map: dict[str, Any],
    quality_report: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifacts: Path,
    decision_question: str,
) -> dict[str, Any]:
    if not repair_quality:
        return {
            "final_map": final_map,
            "quality_report": quality_report,
            "repair_info": {"ran": False, "accepted": False, "reason": "not_requested"},
        }
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
        decision_question=decision_question,
    )
    if repair_info.get("accepted") and isinstance(repair_info.get("candidate_map"), dict):
        return {
            "final_map": repair_info["candidate_map"],
            "quality_report": repair_info["quality_report"],
            "repair_info": repair_info,
        }
    return {"final_map": final_map, "quality_report": quality_report, "repair_info": repair_info}

def _build_initial_staged_map(
    *,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    claims: list[dict[str, Any]],
    all_chunks: list[SourceChunk],
    chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    rejected_claims: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifacts: Path,
    max_relation_pairs: int,
    relation_batch_size: int,
    decision_question: str,
) -> dict[str, Any]:
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
        decision_question=decision_question,
    )
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
        decision_question=decision_question,
    )
    write_json(artifacts / "candidate_map_initial.json", final_map)
    write_json(artifacts / "map_quality_report_initial.json", quality_report)
    write_markdown(artifacts / "MAP_QUALITY_REPORT_INITIAL.md", _quality_markdown(quality_report))
    return {
        "relations": relations,
        "rejected_relations": rejected_relations,
        "final_map": final_map,
        "quality_report": quality_report,
    }

def _write_staged_map_outputs(
    *,
    repo_root: Path,
    manifest_path: str,
    region_id: str,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    artifacts: Path,
    output_path: str | Path | None,
    final_map: dict[str, Any],
    quality_report: dict[str, Any],
    validate: bool,
    decision_question: str,
) -> dict[str, Any]:
    target = Path(output_path or region.map_path)
    if not target.is_absolute():
        target = repo_root / target
    validation_target = artifacts / "candidate_map.json"
    write_json(validation_target, final_map)
    failures = validate_map_candidate(repo_root, manifest_path, region_id, validation_target) if validate else []
    if failures and validate:
        target = artifacts / "failed_candidate.json"
    write_json(target, final_map)
    write_json(artifacts / "map_quality_report.json", quality_report)
    write_markdown(artifacts / "MAP_QUALITY_REPORT.md", _quality_markdown(quality_report))
    repair_prompt_path = artifacts / "map_quality_repair_prompt.txt"
    if not repair_prompt_path.exists():
        write_markdown(repair_prompt_path, _map_quality_repair_prompt(region, case_manifest, final_map, quality_report, decision_question=decision_question))
    return {
        "target": target,
        "validation_target": validation_target,
        "failures": failures,
        "final_claims": [claim for claim in final_map.get("claims", []) if isinstance(claim, dict)],
        "final_relations": [relation for relation in final_map.get("relations", []) if isinstance(relation, dict)],
    }

def _staged_run_summary(
    *,
    repo_root: Path,
    region: WorkedRegion,
    backend: str,
    decision_question: str,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int | None,
    max_total_chunks: int | None,
    max_claims_per_chunk: int,
    claim_extractor: str,
    max_relation_pairs: int,
    relation_batch_size: int,
    backend_timeout: int | None,
    backend_retries: int,
    config_profile_id: str,
    all_chunks: list[SourceChunk],
    chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    coverage_report: dict[str, Any],
    consolidation_report: dict[str, Any],
    llm_claim_count: int,
    coverage_claims: list[dict[str, Any]],
    pre_consolidation_claim_count: int,
    claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    final_claims: list[dict[str, Any]],
    final_relations: list[dict[str, Any]],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    validation_target: Path,
    target: Path,
    failures: list[str],
    quality_report: dict[str, Any],
    repair_info: dict[str, Any],
    artifacts: Path,
) -> dict[str, Any]:
    return {
        "region_id": region.region_id,
        "decision_question": decision_question,
        "backend": backend,
        "chunk_lines": chunk_lines,
        "chunk_overlap_lines": chunk_overlap_lines,
        "max_chunks_per_source": max_chunks_per_source,
        "max_total_chunks": max_total_chunks,
        "max_claims_per_chunk": max_claims_per_chunk,
        "claim_extractor": claim_extractor,
        "max_relation_pairs": max_relation_pairs,
        "relation_batch_size": relation_batch_size,
        "backend_timeout": backend_timeout,
        "backend_retries": backend_retries,
        "epistemic_config_profile": config_profile_id,
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
    }

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
    reuse_claim_cache: bool = True,
    claim_extractor: str = "native",
    decision_question: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    claim_index = 1
    valid_roles = set(_configured_claim_roles(case_manifest))
    progress = {
        "schema_id": "claim_extraction_progress_v1",
        "stage": "claim_extraction",
        "total_chunks": len(chunks),
        "processed_chunks": 0,
        "cache_hit_count": 0,
        "backend_call_count": 0,
        "fallback_claim_count": 0,
        "accepted_claim_count": 0,
        "rejected_claim_count": 0,
        "claim_alignment_status_counts": {},
        "current_chunk_id": "",
        "complete": False,
        "claim_extractor": claim_extractor,
    }
    progress_path = artifact_dir / "claim_extraction_progress.json"

    for chunk_index, chunk in enumerate(chunks, start=1):
        span_lookup = {span.span_id: span for span in chunk.spans}
        chunk_accept_count = 0
        selected_question = region_decision_question(region, case_manifest, decision_question)
        prompt = _claim_prompt(manifest, region, case_manifest, chunk, max_claims_per_chunk, decision_question=selected_question)
        chunk_dir = artifact_dir / "claim_chunks"
        canonical_suffix = "canonical" if claim_extractor == "native" else f"{claim_extractor}_canonical"
        canonical_path = chunk_dir / f"{chunk.chunk_id}_{canonical_suffix}.json"
        write_markdown(chunk_dir / f"{chunk.chunk_id}_prompt.txt", prompt)
        if claim_extractor == "native":
            payload, cache_hit, backend_error = claim_payload_for_chunk(
                prompt=prompt,
                backend=backend,
                backend_timeout=backend_timeout,
                backend_retries=backend_retries,
                canonical_path=canonical_path,
                raw_path=chunk_dir / f"{chunk.chunk_id}_raw.txt",
                reuse_claim_cache=reuse_claim_cache,
            )
        elif claim_extractor == "langextract":
            payload, cache_hit, backend_error = langextract_claim_payload_for_chunk(
                chunk=chunk,
                case_question=selected_question,
                role_options=sorted(valid_roles),
                backend=backend,
                max_claims=max_claims_per_chunk,
                canonical_path=canonical_path,
                report_path=chunk_dir / f"{chunk.chunk_id}_langextract_report.json",
                reuse_claim_cache=reuse_claim_cache,
            )
        else:
            raise ValueError(f"unknown claim_extractor={claim_extractor!r}")
        if cache_hit:
            progress["cache_hit_count"] += 1
        else:
            progress["backend_call_count"] += 1
        if backend_error:
            fallback = _fallback_claim_for_chunk(chunk)
            if fallback is not None:
                key = _claim_dedupe_key(fallback)
                if key not in seen:
                    seen.add(key)
                    claim_index = _record_accepted_claim(fallback, accepted, progress, region.id_prefix, claim_index)
                    progress["fallback_claim_count"] += 1
                    rejected.append(
                        {
                            "chunk_id": chunk.chunk_id,
                            "reason": "backend_error_used_deterministic_fallback",
                            "error": backend_error,
                            "span_id": fallback["span_id"],
                        }
                    )
                    write_claim_progress(progress_path, progress, chunk_index, chunk.chunk_id, accepted, rejected)
                    continue
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "backend_error", "error": backend_error})
            write_claim_progress(progress_path, progress, chunk_index, chunk.chunk_id, accepted, rejected)
            continue
        if not isinstance(payload, dict):
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "invalid_json"})
            write_claim_progress(progress_path, progress, chunk_index, chunk.chunk_id, accepted, rejected)
            continue
        proposals = payload.get("claims", [])
        if not isinstance(proposals, list) and "claim" in payload:
            proposals = [payload]
        if not isinstance(proposals, list):
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "claims_not_list"})
            write_claim_progress(progress_path, progress, chunk_index, chunk.chunk_id, accepted, rejected)
            continue
        for proposal in proposals:
            claim, reason = _normalize_claim_proposal(proposal, span_lookup, valid_roles)
            if claim is None:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": reason, "proposal": proposal})
                continue
            relevance_reason = claim_decision_relevance_rejection_reason(claim, selected_question)
            if relevance_reason:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": relevance_reason, "proposal": proposal})
                continue
            key = _claim_dedupe_key(claim)
            if key in seen:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": "duplicate_claim", "proposal": proposal})
                continue
            seen.add(key)
            claim_index = _record_accepted_claim(claim, accepted, progress, region.id_prefix, claim_index)
            chunk_accept_count += 1
        write_claim_progress(progress_path, progress, chunk_index, chunk.chunk_id, accepted, rejected)
    progress["complete"] = True
    progress["current_chunk_id"] = ""
    progress["processed_chunks"] = len(chunks)
    progress["accepted_claim_count"] = len(accepted)
    progress["rejected_claim_count"] = len(rejected)
    write_json(progress_path, progress)
    write_json(artifact_dir / "accepted_claims.json", {"claims": accepted, "rejected": rejected})
    return accepted, rejected

def _claim_dedupe_key(claim: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(claim.get("source_id", "")),
        _normalize_text(str(claim.get("excerpt", ""))),
        _normalize_text(str(claim.get("claim", ""))),
    )


def _record_accepted_claim(
    claim: dict[str, Any],
    accepted: list[dict[str, Any]],
    progress: dict[str, Any],
    id_prefix: str,
    claim_index: int,
) -> int:
    claim["claim_id"] = f"{id_prefix}_c{claim_index:03d}"
    accepted.append(claim)
    _increment_progress_count(
        progress,
        "claim_alignment_status_counts",
        str(claim.get("source_alignment", {}).get("status", "unknown")),
    )
    return claim_index + 1


def _increment_progress_count(progress: dict[str, Any], key: str, value: str) -> None:
    bucket = progress.setdefault(key, {})
    if not isinstance(bucket, dict):
        bucket = {}
        progress[key] = bucket
    label = value or "unknown"
    bucket[label] = int(bucket.get(label, 0)) + 1

def _coverage_backfill_claims(
    *,
    all_chunks: list[SourceChunk],
    selected_chunks: list[SourceChunk],
    existing_claims: list[dict[str, Any]],
    id_prefix: str,
    profile_id: str = "general_decision_support",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    del existing_claims, id_prefix, profile_id
    selected_ids = {chunk.chunk_id for chunk in selected_chunks}
    skipped_chunk_ids: list[str] = []
    no_signal_chunk_ids: list[str] = []
    suppressed_candidate_rows: list[dict[str, Any]] = []
    for chunk in all_chunks:
        if chunk.chunk_id in selected_ids:
            continue
        skipped_chunk_ids.append(chunk.chunk_id)
        fallback = _fallback_claim_for_chunk(chunk)
        if fallback is None:
            no_signal_chunk_ids.append(chunk.chunk_id)
            continue
        suppressed_candidate_rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "source_id": fallback["source_id"],
                "source_span": fallback["source_span"],
                "role": fallback["role"],
                "excerpt": fallback["excerpt"],
                "reason": "deterministic_backfill_disabled",
                "signal_score": _chunk_signal_score(chunk),
                "line_range": f"{chunk.start_line}-{chunk.end_line}",
            }
        )
    report = {
        "schema_id": "coverage_backfill_v2",
        "method": "warnings_only_for_budget_skipped_chunks",
        "deterministic_claim_insertion": "disabled",
        "warning": (
            "Some source chunks were skipped by budget. The runner reports coverage risk but does not "
            "insert deterministic backfill claims into the map."
        ),
        "skipped_chunk_count": len(skipped_chunk_ids),
        "backfilled_claim_count": 0,
        "skipped_chunk_backfilled_claim_count": 0,
        "concept_gap_backfilled_claim_count": 0,
        "suppressed_candidate_count": len(suppressed_candidate_rows),
        "backfilled_claim_ids": [],
        "skipped_chunk_ids": skipped_chunk_ids[:100],
        "no_signal_chunk_count": len(no_signal_chunk_ids),
        "no_signal_chunk_ids": no_signal_chunk_ids[:50],
        "suppressed_candidates": suppressed_candidate_rows[:50],
        "concept_gap_backfill": {
            "schema_id": "source_concept_gap_backfill_v1",
            "method": "disabled",
            "backfilled_claim_count": 0,
            "rejection_counts": {},
            "selected": [],
            "rejected": [],
        },
    }
    return [], report

# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.staged_semantic_claims_relations import (
    _extract_relations,
    _run_quality_repair,
    _summary_repair_info,
    consolidate_claims_for_map,
)
from epistemic_case_mapper.staged_semantic_quality import (
    _assemble_map,
    _case_config_profile,
    _claim_prompt,
    _claim_prompt_json_schema,
    _configured_claim_roles,
    _map_quality_repair_prompt,
    _quality_markdown,
    _relation_sharpening_summary,
    evaluate_staged_map_quality,
)
from epistemic_case_mapper.staged_semantic_relation_candidates import _relation_batch_count
from epistemic_case_mapper.staged_semantic_sources import (
    _artifact_dir,
    _budget_chunks,
    _chunk_signal_score,
    _chunk_summary,
    _fallback_claim_for_chunk,
    _load_context,
    _normalize_claim_proposal,
    _normalize_text,
    _parse_model_json,
    _relative,
    _source_chunks,
)
