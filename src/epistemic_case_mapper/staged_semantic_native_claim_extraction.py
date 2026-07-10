from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.staged_semantic_claim_cache import write_claim_progress
from epistemic_case_mapper.staged_semantic_claim_extractors import claim_payload_for_extractor
from epistemic_case_mapper.staged_semantic_decision_questions import attach_decision_relevance_validation, region_decision_question
from epistemic_case_mapper.staged_semantic_label_audit import attach_label_audit
from epistemic_case_mapper.staged_semantic_progress import PipelineProgress
from epistemic_case_mapper.staged_semantic_quality import _claim_prompt, _configured_claim_roles
from epistemic_case_mapper.staged_semantic_sources import _fallback_claim_for_chunk, _normalize_claim_proposal, _normalize_text
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion


def _extract_claims(
    repo_root: Path,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    chunks: list[Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    max_claims_per_chunk: int,
    reuse_claim_cache: bool = True,
    claim_extractor: str = "native",
    decision_question: str | None = None,
    pipeline_progress: PipelineProgress | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if claim_extractor == "whole-doc":
        from epistemic_case_mapper.staged_semantic_whole_doc_pipeline import _extract_whole_doc_claims

        return _extract_whole_doc_claims(
            repo_root=repo_root,
            region=region,
            case_manifest=case_manifest,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            artifact_dir=artifact_dir,
            max_claims_per_source=max_claims_per_chunk,
            reuse_claim_cache=reuse_claim_cache,
            decision_question=decision_question,
            progress=pipeline_progress,
        )
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    claim_index = 1
    valid_roles = set(_configured_claim_roles(case_manifest))
    claim_progress = _initial_claim_progress(claim_extractor, len(chunks))
    progress_path = artifact_dir / "claim_extraction_progress.json"
    if pipeline_progress:
        pipeline_progress.start_stage("claim_extraction", extractor=claim_extractor, total_items=len(chunks), total_chunks=len(chunks))

    for chunk_index, chunk in enumerate(chunks, start=1):
        span_lookup = {span.span_id: span for span in chunk.spans}
        selected_question = region_decision_question(region, case_manifest, decision_question)
        prompt = _claim_prompt(manifest, region, case_manifest, chunk, max_claims_per_chunk, decision_question=selected_question)
        chunk_dir = artifact_dir / "claim_chunks"
        canonical_suffix = "canonical" if claim_extractor == "native" else f"{claim_extractor}_canonical"
        canonical_path = chunk_dir / f"{chunk.chunk_id}_{canonical_suffix}.json"
        write_markdown(chunk_dir / f"{chunk.chunk_id}_prompt.txt", prompt)
        if pipeline_progress:
            pipeline_progress.start_backend_call(
                stage="claim_extraction",
                item_id=chunk.chunk_id,
                item_index=chunk_index,
                total_items=len(chunks),
                timeout_seconds=backend_timeout,
                source_id=chunk.source_id,
                extractor=claim_extractor,
            )
        payload, cache_hit, backend_error = claim_payload_for_extractor(
            claim_extractor=claim_extractor,
            prompt=prompt,
            chunk=chunk,
            selected_question=selected_question,
            valid_roles=valid_roles,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            max_claims_per_chunk=max_claims_per_chunk,
            canonical_path=canonical_path,
            chunk_dir=chunk_dir,
            reuse_claim_cache=reuse_claim_cache,
        )
        if pipeline_progress:
            pipeline_progress.finish_backend_call(
                status="cache_hit" if cache_hit else ("backend_error" if backend_error else "completed"),
                error=backend_error,
                cache_hit=cache_hit,
            )
        if _handle_extractor_failure(
            backend_error=backend_error,
            cache_hit=cache_hit,
            chunk=chunk,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            claim_progress=claim_progress,
            progress_path=progress_path,
            chunk_index=chunk_index,
            id_prefix=region.id_prefix,
            claim_index_ref=[claim_index],
        ):
            claim_index = len(accepted) + 1
            continue
        if not _payload_is_claim_list(payload, chunk.chunk_id, rejected, claim_progress, progress_path, chunk_index, accepted):
            continue
        proposals = payload.get("claims", []) if isinstance(payload, dict) else []
        if not isinstance(proposals, list) and isinstance(payload, dict) and "claim" in payload:
            proposals = [payload]
        for proposal in proposals:
            claim, reason = _normalize_claim_proposal(proposal, span_lookup, valid_roles)
            if claim is None:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": reason, "proposal": proposal})
                continue
            _attach_claim_routing_metadata(claim, claim_progress, selected_question)
            key = _claim_dedupe_key(claim)
            if key in seen:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": "duplicate_claim", "proposal": proposal})
                continue
            seen.add(key)
            claim_index = _record_accepted_claim(claim, accepted, claim_progress, region.id_prefix, claim_index)
        write_claim_progress(progress_path, claim_progress, chunk_index, chunk.chunk_id, accepted, rejected)
    _finish_claim_progress(claim_progress, progress_path, artifact_dir, accepted, rejected, len(chunks))
    if pipeline_progress:
        pipeline_progress.finish_stage("claim_extraction", accepted_claim_count=len(accepted), rejected_claim_count=len(rejected), total_chunks=len(chunks))
    return accepted, rejected


def _initial_claim_progress(claim_extractor: str, total_chunks: int) -> dict[str, Any]:
    return {
        "schema_id": "claim_extraction_progress_v1",
        "stage": "claim_extraction",
        "total_chunks": total_chunks,
        "processed_chunks": 0,
        "cache_hit_count": 0,
        "backend_call_count": 0,
        "fallback_claim_count": 0,
        "accepted_claim_count": 0,
        "rejected_claim_count": 0,
        "claim_alignment_status_counts": {},
        "relevance_validation_warning_counts": {},
        "label_audit_bucket_counts": {},
        "label_audit_warning_counts": {},
        "current_chunk_id": "",
        "complete": False,
        "claim_extractor": claim_extractor,
    }


def _handle_extractor_failure(
    *,
    backend_error: str,
    cache_hit: bool,
    chunk: Any,
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    claim_progress: dict[str, Any],
    progress_path: Path,
    chunk_index: int,
    id_prefix: str,
    claim_index_ref: list[int],
) -> bool:
    if cache_hit:
        claim_progress["cache_hit_count"] += 1
        return False
    claim_progress["backend_call_count"] += 1
    if not backend_error:
        return False
    fallback = _fallback_claim_for_chunk(chunk)
    if fallback is not None:
        key = _claim_dedupe_key(fallback)
        if key not in seen:
            seen.add(key)
            claim_index_ref[0] = _record_accepted_claim(fallback, accepted, claim_progress, id_prefix, claim_index_ref[0])
            claim_progress["fallback_claim_count"] += 1
            rejected.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "reason": "backend_error_used_deterministic_fallback",
                    "error": backend_error,
                    "span_id": fallback["span_id"],
                }
            )
            write_claim_progress(progress_path, claim_progress, chunk_index, chunk.chunk_id, accepted, rejected)
            return True
    rejected.append({"chunk_id": chunk.chunk_id, "reason": "backend_error", "error": backend_error})
    write_claim_progress(progress_path, claim_progress, chunk_index, chunk.chunk_id, accepted, rejected)
    return True


def _payload_is_claim_list(
    payload: Any,
    chunk_id: str,
    rejected: list[dict[str, Any]],
    claim_progress: dict[str, Any],
    progress_path: Path,
    chunk_index: int,
    accepted: list[dict[str, Any]],
) -> bool:
    if not isinstance(payload, dict):
        rejected.append({"chunk_id": chunk_id, "reason": "invalid_json"})
        write_claim_progress(progress_path, claim_progress, chunk_index, chunk_id, accepted, rejected)
        return False
    proposals = payload.get("claims", [])
    if isinstance(proposals, list) or "claim" in payload:
        return True
    rejected.append({"chunk_id": chunk_id, "reason": "claims_not_list"})
    write_claim_progress(progress_path, claim_progress, chunk_index, chunk_id, accepted, rejected)
    return False


def _finish_claim_progress(
    claim_progress: dict[str, Any],
    progress_path: Path,
    artifact_dir: Path,
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    total_chunks: int,
) -> None:
    claim_progress.update(
        complete=True,
        current_chunk_id="",
        processed_chunks=total_chunks,
        accepted_claim_count=len(accepted),
        rejected_claim_count=len(rejected),
    )
    write_json(progress_path, claim_progress)
    write_json(artifact_dir / "accepted_claims.json", {"claims": accepted, "rejected": rejected})


def _attach_claim_routing_metadata(claim: dict[str, Any], progress: dict[str, Any], selected_question: str) -> None:
    relevance_reason = attach_decision_relevance_validation(claim, selected_question)
    if relevance_reason:
        _increment_progress_count(progress, "relevance_validation_warning_counts", relevance_reason)
    audit = attach_label_audit(claim)
    _increment_progress_count(progress, "label_audit_bucket_counts", str(audit.get("synthesis_bucket", "unknown")))
    for warning in audit.get("warnings", []):
        _increment_progress_count(progress, "label_audit_warning_counts", str(warning))


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
