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
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.pipeline.map.semantic_pipeline import validate_map_candidate
from epistemic_case_mapper.pipeline.map.staged_semantic_claim_consolidation import consolidate_claims_with_vector_llm
from epistemic_case_mapper.pipeline.map.staged_semantic_claim_metadata import claims_with_relation_role_metadata
from epistemic_case_mapper.pipeline.map.staged_semantic_claim_triage import triage_claims_for_relation_building
from epistemic_case_mapper.pipeline.map.staged_semantic_decision_questions import region_decision_question
from epistemic_case_mapper.pipeline.map.staged_semantic_label_audit import label_audit_bucket_counts, label_audit_warning_counts
from epistemic_case_mapper.pipeline.map.staged_semantic_progress import PipelineProgress
from epistemic_case_mapper.pipeline.map.staged_semantic_contracts import (
    CLAIM_EXTRACTION_METHOD,
    CONSOLIDATION_OVERLAP_THRESHOLD,
    CONSOLIDATION_SIMILARITY_THRESHOLD,
    RELATION_BATCH_PROMPT_VERSION,
    RELATION_PROMPT_VERSION,
    SourceChunk,
    SourceSpan,
)
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest

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
    max_claims_per_source: int = 4,
    max_relation_pairs: int = 12,
    relation_batch_size: int = 4,
    backend_timeout: int | None = 90,
    backend_retries: int = 1,
    validate: bool = True,
    repair_quality: bool = False,
    reuse_claim_cache: bool = True,
    claim_consolidation: str = "deterministic",
    decision_question: str | None = None,
) -> StagedMapResult:
    _validate_staged_map_options(
        chunk_lines=chunk_lines,
        chunk_overlap_lines=chunk_overlap_lines,
        max_chunks_per_source=max_chunks_per_source,
        max_total_chunks=max_total_chunks,
        relation_batch_size=relation_batch_size,
        claim_consolidation=claim_consolidation,
    )
    manifest, region, case_manifest = _load_context(repo_root, manifest_path, region_id)
    artifacts = _artifact_dir(repo_root, region_id, artifact_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    config_profile = _case_config_profile(case_manifest)
    selected_decision_question = region_decision_question(region, case_manifest, decision_question)
    progress = PipelineProgress(
        artifacts / "pipeline_progress.json",
        backend_timeout=backend_timeout,
        metadata={
            "region_id": region.region_id,
            "backend": backend,
            "claim_extraction_method": CLAIM_EXTRACTION_METHOD,
            "claim_consolidation": claim_consolidation,
            "decision_question": selected_decision_question,
        },
    )

    try:
        progress.start_stage("chunk_selection")
        all_chunks = _source_chunks(repo_root, case_manifest, region, chunk_lines, chunk_overlap_lines)
        chunks, skipped_chunks = _budget_chunks(all_chunks, max_chunks_per_source, max_total_chunks)
        progress.finish_stage(
            "chunk_selection",
            all_chunk_count=len(all_chunks),
            selected_chunk_count=len(chunks),
            skipped_chunk_count=len(skipped_chunks),
        )
        outputs = _run_mapping_stages(
            repo_root=repo_root, manifest_path=manifest_path, region_id=region_id,
            manifest=manifest, region=region, case_manifest=case_manifest,
            all_chunks=all_chunks, chunks=chunks, skipped_chunks=skipped_chunks,
            backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries,
            artifacts=artifacts, max_claims_per_source=max_claims_per_source,
            config_profile_id=config_profile.profile_id, reuse_claim_cache=reuse_claim_cache,
            claim_consolidation=claim_consolidation,
            max_relation_pairs=max_relation_pairs, relation_batch_size=relation_batch_size,
            repair_quality=repair_quality, validate=validate, output_path=output_path,
            decision_question=selected_decision_question, progress=progress,
        )
        return _complete_staged_map_run(
            repo_root=repo_root,
            region=region,
            backend=backend,
            decision_question=selected_decision_question,
            chunk_options={
                "chunk_lines": chunk_lines,
                "chunk_overlap_lines": chunk_overlap_lines,
                "max_chunks_per_source": max_chunks_per_source,
                "max_total_chunks": max_total_chunks,
                "max_claims_per_source": max_claims_per_source,
                "max_relation_pairs": max_relation_pairs,
                "relation_batch_size": relation_batch_size,
            },
            backend_options={"backend_timeout": backend_timeout, "backend_retries": backend_retries},
            extraction_options={"claim_extraction_method": CLAIM_EXTRACTION_METHOD, "claim_consolidation": claim_consolidation},
            config_profile_id=config_profile.profile_id,
            all_chunks=all_chunks,
            chunks=chunks,
            skipped_chunks=skipped_chunks,
            claim_stage=outputs["claim_stage"],
            claims=outputs["claims"],
            relation_claims=outputs["relation_claims"],
            relations=outputs["relations"],
            final_outputs=outputs["final_outputs"],
            rejected_claims=outputs["rejected_claims"],
            rejected_relations=outputs["rejected_relations"],
            quality_report=outputs["quality_report"],
            repair_info=outputs["repair_info"],
            artifacts=artifacts,
            progress=progress,
        )
    except Exception as exc:
        progress.fail(str(exc))
        raise

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

def _run_mapping_stages(
    *,
    repo_root: Path,
    manifest_path: str,
    region_id: str,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[SourceChunk],
    chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifacts: Path,
    max_claims_per_source: int,
    config_profile_id: str,
    reuse_claim_cache: bool,
    claim_consolidation: str,
    max_relation_pairs: int,
    relation_batch_size: int,
    repair_quality: bool,
    validate: bool,
    output_path: str | Path | None,
    decision_question: str,
    progress: PipelineProgress,
) -> dict[str, Any]:
    claim_stage = _extract_consolidated_claims(
        repo_root=repo_root, manifest=manifest, region=region, case_manifest=case_manifest,
        all_chunks=all_chunks, chunks=chunks, backend=backend, backend_timeout=backend_timeout,
        backend_retries=backend_retries, artifacts=artifacts, max_claims_per_source=max_claims_per_source,
        config_profile_id=config_profile_id, reuse_claim_cache=reuse_claim_cache,
        claim_consolidation=claim_consolidation,
        decision_question=decision_question, progress=progress,
    )
    extracted_claims = claim_stage["claims"]
    if progress:
        progress.start_stage("claim_relation_triage", claim_count=len(extracted_claims))
    triaged_claims, relation_claims, claim_relation_triage_report = triage_claims_for_relation_building(extracted_claims)
    claims = [claim for claim in triaged_claims if claim.get("included_in_final_map") is True]
    claim_stage["claims"] = claims
    claim_stage["triaged_claims"] = triaged_claims
    claim_stage["relation_claims"] = relation_claims
    claim_stage["routed_away_claims"] = claim_relation_triage_report.get("routed_away_claims", [])
    claim_stage["claim_relation_triage_report"] = claim_relation_triage_report
    write_json(artifacts / "claim_relation_triage_report.json", claim_relation_triage_report)
    if progress:
        progress.finish_stage(
            "claim_relation_triage",
            eligible_claim_count=len(relation_claims),
            excluded_claim_count=claim_relation_triage_report["excluded_claim_count"],
            final_map_claim_count=len(claims),
            routed_away_claim_count=claim_relation_triage_report.get("routed_away_claim_count", 0),
            fallback_used=claim_relation_triage_report["fallback_used"],
        )
    rejected_claims = claim_stage["rejected_claims"]
    initial = _build_initial_staged_map(
        repo_root=repo_root,
        manifest=manifest, region=region, case_manifest=case_manifest, claims=claims, relation_claims=relation_claims,
        all_chunks=all_chunks, chunks=chunks, skipped_chunks=skipped_chunks,
        rejected_claims=rejected_claims, backend=backend, backend_timeout=backend_timeout,
        backend_retries=backend_retries, artifacts=artifacts, max_relation_pairs=max_relation_pairs,
        relation_batch_size=relation_batch_size, decision_question=decision_question, progress=progress,
    )
    progress.start_stage("quality_repair", requested=repair_quality)
    repair = _maybe_repair_staged_map_quality(
        repair_quality=repair_quality, repo_root=repo_root, manifest_path=manifest_path,
        manifest=manifest, region=region, case_manifest=case_manifest,
        all_chunks=all_chunks, chunks=chunks, skipped_chunks=skipped_chunks,
        final_map=initial["final_map"], quality_report=initial["quality_report"],
        rejected_claims=rejected_claims, rejected_relations=initial["rejected_relations"],
        backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries,
        artifacts=artifacts, decision_question=decision_question,
    )
    progress.finish_stage("quality_repair", requested=repair_quality, accepted=bool(repair["repair_info"].get("accepted")))
    progress.start_stage("write_outputs", validate=validate)
    final_outputs = _write_staged_map_outputs(
        repo_root=repo_root, manifest_path=manifest_path, region_id=region_id,
        region=region, case_manifest=case_manifest, artifacts=artifacts, output_path=output_path,
        final_map=repair["final_map"], quality_report=repair["quality_report"],
        validate=validate, decision_question=decision_question,
    )
    progress.finish_stage("write_outputs", failure_count=len(final_outputs["failures"]), output_path=str(final_outputs["target"]))
    return {
        "claim_stage": claim_stage,
        "claims": claims,
        "relation_claims": relation_claims,
        "relations": initial["relations"],
        "rejected_claims": rejected_claims,
        "rejected_relations": initial["rejected_relations"],
        "quality_report": repair["quality_report"],
        "repair_info": repair["repair_info"],
        "final_outputs": final_outputs,
    }

def _complete_staged_map_run(
    *,
    repo_root: Path,
    region: WorkedRegion,
    backend: str,
    decision_question: str,
    chunk_options: dict[str, Any],
    backend_options: dict[str, Any],
    extraction_options: dict[str, Any],
    config_profile_id: str,
    all_chunks: list[SourceChunk],
    chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    claim_stage: dict[str, Any],
    claims: list[dict[str, Any]],
    relation_claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    final_outputs: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    quality_report: dict[str, Any],
    repair_info: dict[str, Any],
    artifacts: Path,
    progress: PipelineProgress,
) -> StagedMapResult:
    _write_staged_run_summary(
        repo_root=repo_root, region=region, backend=backend, decision_question=decision_question,
        chunk_lines=int(chunk_options["chunk_lines"]), chunk_overlap_lines=int(chunk_options["chunk_overlap_lines"]),
        max_chunks_per_source=chunk_options["max_chunks_per_source"], max_total_chunks=chunk_options["max_total_chunks"],
        max_claims_per_source=int(chunk_options["max_claims_per_source"]),
        claim_extraction_method=str(extraction_options["claim_extraction_method"]),
        claim_consolidation=str(extraction_options["claim_consolidation"]),
        max_relation_pairs=int(chunk_options["max_relation_pairs"]), relation_batch_size=int(chunk_options["relation_batch_size"]),
        backend_timeout=backend_options["backend_timeout"], backend_retries=int(backend_options["backend_retries"]),
        config_profile_id=config_profile_id,
        all_chunks=all_chunks, chunks=chunks, skipped_chunks=skipped_chunks,
        claim_stage=claim_stage, claims=claims, relation_claims=relation_claims, relations=relations, final_outputs=final_outputs,
        rejected_claims=rejected_claims, rejected_relations=rejected_relations,
        quality_report=quality_report, repair_info=repair_info, artifacts=artifacts,
    )
    progress.complete(
        claim_count=len(final_outputs["final_claims"]),
        relation_count=len(final_outputs["final_relations"]),
        rejected_claim_count=len(rejected_claims),
        rejected_relation_count=len(rejected_relations),
        quality_status=str(quality_report["status"]),
    )
    return _staged_map_result(
        final_outputs=final_outputs, artifacts=artifacts, rejected_claims=rejected_claims,
        rejected_relations=rejected_relations, quality_report=quality_report, repair_info=repair_info,
    )

def _validate_staged_map_options(
    *,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int | None,
    max_total_chunks: int | None,
    claim_consolidation: str,
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
    if claim_consolidation not in {"deterministic", "vector-llm"}:
        raise ValueError("claim_consolidation must be deterministic or vector-llm")

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
    max_claims_per_source: int,
    claim_extraction_method: str,
    claim_consolidation: str,
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
    relation_claims: list[dict[str, Any]],
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
            max_claims_per_source=max_claims_per_source,
            claim_extraction_method=claim_extraction_method,
            claim_consolidation=claim_consolidation,
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
            claim_relation_triage_report=claim_stage.get("claim_relation_triage_report", {}),
            claims=claims,
            relation_claims=relation_claims,
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
    max_claims_per_source: int,
    config_profile_id: str,
    reuse_claim_cache: bool,
    claim_consolidation: str,
    decision_question: str,
    progress: PipelineProgress | None = None,
) -> dict[str, Any]:
    claims, rejected_claims = _extract_claims(
        repo_root=repo_root,
        region=region,
        case_manifest=case_manifest,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifacts,
        max_claims_per_source=max_claims_per_source,
        reuse_claim_cache=reuse_claim_cache,
        decision_question=decision_question,
        pipeline_progress=progress,
    )
    llm_claim_count = len(claims)
    if progress:
        progress.start_stage("coverage_backfill", existing_claim_count=len(claims), all_chunk_count=len(all_chunks))
    coverage_claims, coverage_report = _coverage_backfill_claims(
        all_chunks=all_chunks,
        selected_chunks=chunks,
        existing_claims=claims,
        id_prefix=region.id_prefix,
        profile_id=config_profile_id,
    )
    if coverage_claims:
        claims.extend(coverage_claims)
    if progress:
        progress.finish_stage("coverage_backfill", coverage_claim_count=len(coverage_claims), claim_count=len(claims))
    pre_consolidation_claim_count = len(claims)
    write_json(artifacts / "coverage_backfill_claims.json", coverage_report)
    if progress:
        progress.start_stage("claim_consolidation", method=claim_consolidation, claim_count=len(claims))
    if claim_consolidation == "vector-llm":
        if progress:
            progress.start_backend_call(
                stage="claim_consolidation",
                item_id="vector_llm_claim_consolidation",
                timeout_seconds=backend_timeout,
                input_claim_count=len(claims),
            )
        claims, consolidation_report = consolidate_claims_with_vector_llm(
            claims, backend=backend, artifact_dir=artifacts, decision_question=decision_question,
            backend_timeout=backend_timeout, backend_retries=backend_retries,
            min_claims=max(2, region.thresholds.min_claims),
        )
        if progress:
            progress.finish_backend_call(status="completed", output_claim_count=len(claims))
    else:
        claims, consolidation_report = consolidate_claims_for_map(claims, min_claims=max(2, region.thresholds.min_claims))
    if progress:
        progress.finish_stage(
            "claim_consolidation",
            method=claim_consolidation,
            pre_consolidation_claim_count=pre_consolidation_claim_count,
            post_consolidation_claim_count=len(claims),
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

def _extract_claims(
    *,
    repo_root: Path,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    max_claims_per_source: int,
    reuse_claim_cache: bool = True,
    decision_question: str | None = None,
    pipeline_progress: PipelineProgress | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from epistemic_case_mapper.pipeline.map.staged_semantic_whole_doc_pipeline import _extract_whole_doc_claims

    return _extract_whole_doc_claims(
        repo_root=repo_root,
        region=region,
        case_manifest=case_manifest,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifact_dir,
        max_claims_per_source=max_claims_per_source,
        reuse_claim_cache=reuse_claim_cache,
        decision_question=decision_question,
        progress=pipeline_progress,
    )

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
    repo_root: Path,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    claims: list[dict[str, Any]],
    relation_claims: list[dict[str, Any]],
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
    progress: PipelineProgress | None = None,
) -> dict[str, Any]:
    relations, relation_payloads, rejected_relations, prepared_relation_claims = _extract_relations(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        claims=relation_claims,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifacts,
        max_relation_pairs=max_relation_pairs,
        relation_batch_size=relation_batch_size,
        decision_question=decision_question,
        progress=progress,
    )
    final_map = _assemble_map(
        region=region,
        case_manifest=case_manifest,
        claims=claims_with_relation_role_metadata(claims, prepared_relation_claims),
        relations=relations,
        relation_payloads=relation_payloads,
        decision_question=decision_question,
        repo_root=repo_root,
    )
    if progress:
        progress.start_stage(
            "map_quality",
            claim_count=len(claims),
            relation_claim_count=len(relation_claims),
            relation_count=len(relations),
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
    if progress:
        progress.finish_stage("map_quality", status=quality_report["status"], score=quality_report["score"])
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
    max_claims_per_source: int,
    claim_extraction_method: str,
    claim_consolidation: str,
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
    claim_relation_triage_report: dict[str, Any],
    claims: list[dict[str, Any]],
    relation_claims: list[dict[str, Any]],
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
        "max_claims_per_source": max_claims_per_source,
        "claim_extraction_method": claim_extraction_method,
        "claim_consolidation": claim_consolidation,
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
        "post_triage_extracted_claim_count": int(claim_relation_triage_report.get("input_claim_count", len(claims)) or len(claims)),
        "routed_away_claim_count": int(claim_relation_triage_report.get("routed_away_claim_count", 0) or 0),
        "initial_claim_count": len(claims),
        "relation_eligible_claim_count": len(relation_claims),
        "initial_relation_count": len(relations),
        "relation_sharpening": _relation_sharpening_summary(relations),
        "claim_count": len(final_claims),
        "relation_count": len(final_relations),
        "relation_batch_count": _relation_batch_count(max_relation_pairs, relation_batch_size, relation_claims),
        "claim_relation_triage": {
            "schema_id": "claim_relation_triage_summary_v1",
            "artifact": _relative(repo_root, artifacts / "claim_relation_triage_report.json"),
            "bucket_counts": dict(claim_relation_triage_report.get("bucket_counts", {})),
            "eligible_claim_count": len(relation_claims),
            "relation_excluded_claim_count": int(claim_relation_triage_report.get("relation_excluded_claim_count", 0) or 0),
            "routed_away_claim_count": int(claim_relation_triage_report.get("routed_away_claim_count", 0) or 0),
            "excluded_claim_count": int(claim_relation_triage_report.get("excluded_claim_count", 0) or 0),
        },
        "rejected_claims": rejected_claims,
        "rejected_relations": rejected_relations,
        "candidate_path": _relative(repo_root, validation_target),
        "output_path": _relative(repo_root, target),
        "failures": failures,
        "quality_status": quality_report["status"],
        "quality_score": quality_report["score"],
        "label_audit_bucket_counts": label_audit_bucket_counts(final_claims),
        "label_audit_warning_counts": label_audit_warning_counts(final_claims),
        "quality_report": _relative(repo_root, artifacts / "map_quality_report.json"),
        "quality_repair_prompt": _relative(repo_root, artifacts / "map_quality_repair_prompt.txt"),
        "quality_repair": _summary_repair_info(repo_root, repair_info),
    }

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

# Public facade dependency imports.
from epistemic_case_mapper.pipeline.map.staged_semantic_claims_relations import (
    _extract_relations,
    _run_quality_repair,
    _summary_repair_info,
    consolidate_claims_for_map,
)
from epistemic_case_mapper.pipeline.map.staged_semantic_quality import (
    _assemble_map,
    _case_config_profile,
    _map_quality_repair_prompt,
    _quality_markdown,
    _relation_sharpening_summary,
    evaluate_staged_map_quality,
)
from epistemic_case_mapper.pipeline.map.staged_semantic_relation_candidates import _relation_batch_count
from epistemic_case_mapper.pipeline.map.staged_semantic_sources import (
    _artifact_dir,
    _budget_chunks,
    _chunk_signal_score,
    _chunk_summary,
    _fallback_claim_for_chunk,
    _load_context,
    _parse_model_json,
    _relative,
    _source_chunks,
)
