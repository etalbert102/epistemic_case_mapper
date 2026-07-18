from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.config_profiles import config_profile_from_manifest_payload
from epistemic_case_mapper.io import write_json
from epistemic_case_mapper.model_backends import model_parallelism, run_parallel
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.staged_semantic_claim_cache import write_claim_progress
from epistemic_case_mapper.staged_semantic_decision_questions import attach_decision_relevance_validation, region_decision_question
from epistemic_case_mapper.staged_semantic_evidence_routing import build_evidence_unit_routing
from epistemic_case_mapper.staged_semantic_evidence_units import (
    build_quantity_tuple_binding_report,
    build_quantity_tuple_mutation_eval,
)
from epistemic_case_mapper.staged_semantic_label_audit import attach_label_audit
from epistemic_case_mapper.staged_semantic_progress import PipelineProgress
from epistemic_case_mapper.staged_semantic_sources import (
    _normalize_claim_proposal,
    _normalize_text,
    _required_sources,
    _safe_filename,
    _source_text,
)
from epistemic_case_mapper.staged_semantic_whole_doc import whole_doc_claim_payload_for_source
from epistemic_case_mapper.submission_manifest import WorkedRegion


@dataclass(frozen=True)
class WholeDocSourceSpan:
    span_id: str
    source_id: str
    source_span: str
    text: str


@dataclass(frozen=True)
class WholeDocSourceChunk:
    chunk_id: str
    source_id: str
    title: str
    start_line: int
    end_line: int
    ordinal: int
    numbered_text: str
    plain_text: str
    spans: tuple[WholeDocSourceSpan, ...]


def _extract_whole_doc_claims(
    *,
    repo_root: Path,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    max_claims_per_source: int,
    reuse_claim_cache: bool,
    decision_question: str | None,
    progress: PipelineProgress | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    evidence_units: list[dict[str, Any]] = []
    quantity_tuples: list[dict[str, Any]] = []
    evidence_unit_reports: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    claim_index = 1
    valid_roles = set(_configured_claim_roles(case_manifest))
    source_chunks = _whole_doc_source_chunks(repo_root, case_manifest, region)
    claim_progress = _initial_claim_progress(total_chunks=len(source_chunks))
    progress_path = artifact_dir / "claim_extraction_progress.json"
    selected_question = region_decision_question(region, case_manifest, decision_question)
    source_dir = artifact_dir / "claim_sources"
    parallelism = claim_extraction_parallelism(backend)
    if progress:
        progress.start_stage(
            "claim_extraction",
            extractor="whole-doc",
            total_items=len(source_chunks),
            total_sources=len(source_chunks),
            parallelism=parallelism,
        )
    extraction_results = run_parallel(
        list(enumerate(source_chunks, start=1)),
        lambda item: _fetch_whole_doc_payload(
            item,
            selected_question=selected_question,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            max_claims_per_source=max_claims_per_source,
            source_dir=source_dir,
            reuse_claim_cache=reuse_claim_cache,
        ),
        max_workers=parallelism,
    )
    retry_report = _retry_failed_whole_doc_results_serially(
        extraction_results,
        selected_question=selected_question,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        max_claims_per_source=max_claims_per_source,
        source_dir=source_dir,
    )
    claim_progress["parallelism"] = parallelism
    claim_progress.update(retry_report)
    for result in extraction_results:
        claim_index = _process_whole_doc_result(
            result,
            selected_question=selected_question,
            id_prefix=region.id_prefix,
            valid_roles=valid_roles,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            claim_progress=claim_progress,
            progress_path=progress_path,
            evidence_units=evidence_units,
            quantity_tuples=quantity_tuples,
            evidence_unit_reports=evidence_unit_reports,
            claim_index=claim_index,
        )
    _write_whole_doc_extraction_artifacts(
        artifact_dir=artifact_dir,
        progress_path=progress_path,
        selected_question=selected_question,
        source_chunks=source_chunks,
        accepted=accepted,
        rejected=rejected,
        claim_progress=claim_progress,
        evidence_units=evidence_units,
        quantity_tuples=quantity_tuples,
        evidence_unit_reports=evidence_unit_reports,
    )
    if progress:
        progress.finish_stage(
            "claim_extraction",
            accepted_claim_count=len(accepted),
            rejected_claim_count=len(rejected),
            total_sources=len(source_chunks),
            parallelism=parallelism,
            serial_retry_attempt_count=retry_report["serial_retry_attempt_count"],
            serial_retry_recovered_count=retry_report["serial_retry_recovered_count"],
            serial_retry_failed_count=retry_report["serial_retry_failed_count"],
        )
    return accepted, rejected


def _initial_claim_progress(*, total_chunks: int) -> dict[str, Any]:
    return {
        "schema_id": "claim_extraction_progress_v1",
        "stage": "whole_doc_claim_extraction",
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
        "serial_retry_attempt_count": 0,
        "serial_retry_recovered_count": 0,
        "serial_retry_failed_count": 0,
        "current_chunk_id": "",
        "complete": False,
        "claim_extraction_method": "whole_doc_source_card",
    }


def _process_whole_doc_result(
    result: dict[str, Any],
    *,
    selected_question: str,
    id_prefix: str,
    valid_roles: set[str],
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    claim_progress: dict[str, Any],
    progress_path: Path,
    evidence_units: list[dict[str, Any]],
    quantity_tuples: list[dict[str, Any]],
    evidence_unit_reports: list[dict[str, Any]],
    claim_index: int,
) -> int:
    source_index = int(result["source_index"])
    chunk = result["chunk"]
    payload = result["payload"]
    _record_backend_progress(result, claim_progress)
    if _record_result_rejection(result, chunk, rejected):
        write_claim_progress(progress_path, claim_progress, source_index, chunk.chunk_id, accepted, rejected)
        return claim_index
    _collect_evidence_unit_artifacts(
        payload,
        evidence_units=evidence_units,
        quantity_tuples=quantity_tuples,
        reports=evidence_unit_reports,
    )
    span_lookup = {span.span_id: span for span in chunk.spans}
    for proposal in payload["claims"]:
        claim_index = _process_claim_proposal(
            proposal,
            chunk=chunk,
            selected_question=selected_question,
            id_prefix=id_prefix,
            valid_roles=valid_roles,
            span_lookup=span_lookup,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            claim_progress=claim_progress,
            claim_index=claim_index,
        )
    write_claim_progress(progress_path, claim_progress, source_index, chunk.chunk_id, accepted, rejected)
    return claim_index


def _record_backend_progress(result: dict[str, Any], claim_progress: dict[str, Any]) -> None:
    if bool(result["cache_hit"]):
        claim_progress["cache_hit_count"] += 1
    else:
        claim_progress["backend_call_count"] += int(result.get("backend_call_count") or 1)


def _record_result_rejection(result: dict[str, Any], chunk: WholeDocSourceChunk, rejected: list[dict[str, Any]]) -> bool:
    backend_error = str(result["backend_error"])
    if backend_error:
        rejection = {"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": "backend_error", "error": backend_error}
        if result.get("serial_retry_attempted"):
            rejection["serial_retry_attempted"] = True
            rejection["initial_error"] = result.get("initial_backend_error", "")
        rejected.append(rejection)
        return True
    payload = result["payload"]
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        rejected.append({"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": "invalid_whole_doc_payload"})
        return True
    return False


def _process_claim_proposal(
    proposal: Any,
    *,
    chunk: WholeDocSourceChunk,
    selected_question: str,
    id_prefix: str,
    valid_roles: set[str],
    span_lookup: dict[str, WholeDocSourceSpan],
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    claim_progress: dict[str, Any],
    claim_index: int,
) -> int:
    claim, reason = _normalize_claim_proposal(proposal, span_lookup, valid_roles)
    if claim is None:
        rejected.append({"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": reason, "proposal": proposal})
        return claim_index
    relevance_reason = attach_decision_relevance_validation(claim, selected_question)
    if relevance_reason:
        _increment_progress_count(claim_progress, "relevance_validation_warning_counts", relevance_reason)
    audit = attach_label_audit(claim)
    _increment_progress_count(claim_progress, "label_audit_bucket_counts", str(audit.get("synthesis_bucket", "unknown")))
    for warning in audit.get("warnings", []):
        _increment_progress_count(claim_progress, "label_audit_warning_counts", str(warning))
    key = _claim_dedupe_key(claim)
    if key in seen:
        rejected.append({"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": "duplicate_claim", "proposal": proposal})
        return claim_index
    seen.add(key)
    claim["extraction_method"] = "whole_doc_source_card"
    return _record_accepted_claim(claim, accepted, claim_progress, id_prefix, claim_index)


def _write_whole_doc_extraction_artifacts(
    *,
    artifact_dir: Path,
    progress_path: Path,
    selected_question: str,
    source_chunks: list[WholeDocSourceChunk],
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    claim_progress: dict[str, Any],
    evidence_units: list[dict[str, Any]],
    quantity_tuples: list[dict[str, Any]],
    evidence_unit_reports: list[dict[str, Any]],
) -> None:
    claim_progress["complete"] = True
    claim_progress["current_chunk_id"] = ""
    claim_progress["processed_chunks"] = len(source_chunks)
    claim_progress["accepted_claim_count"] = len(accepted)
    claim_progress["rejected_claim_count"] = len(rejected)
    write_json(progress_path, claim_progress)
    write_json(artifact_dir / "accepted_claims.json", {"claims": accepted, "rejected": rejected})
    _write_evidence_unit_artifacts(
        artifact_dir=artifact_dir,
        selected_question=selected_question,
        source_ids=[chunk.source_id for chunk in source_chunks],
        evidence_units=evidence_units,
        quantity_tuples=quantity_tuples,
        evidence_unit_reports=evidence_unit_reports,
    )


def _write_evidence_unit_artifacts(
    *,
    artifact_dir: Path,
    selected_question: str,
    source_ids: list[str],
    evidence_units: list[dict[str, Any]],
    quantity_tuples: list[dict[str, Any]],
    evidence_unit_reports: list[dict[str, Any]],
) -> None:
    write_json(
        artifact_dir / "source_evidence_units.json",
        {"schema_id": "source_evidence_units_aggregate_v1", "decision_question": selected_question, "unit_count": len(evidence_units), "units": evidence_units},
    )
    write_json(
        artifact_dir / "source_quantity_tuples.json",
        {
            "schema_id": "source_quantity_tuples_aggregate_v1",
            "decision_question": selected_question,
            "canonical_record_type": "source_result_quantity_tuple_v1",
            "tuple_count": len(quantity_tuples),
            "tuples": quantity_tuples,
        },
    )
    write_json(artifact_dir / "quantity_tuple_binding_report.json", build_quantity_tuple_binding_report(quantity_tuples))
    write_json(artifact_dir / "quantity_tuple_mutation_eval.json", build_quantity_tuple_mutation_eval(quantity_tuples))
    write_json(
        artifact_dir / "source_evidence_unit_quality_report.json",
        _aggregate_evidence_unit_quality_report(evidence_unit_reports, unit_count=len(evidence_units), quantity_tuple_count=len(quantity_tuples)),
    )
    routing = build_evidence_unit_routing(evidence_units, decision_question=selected_question, source_ids=source_ids)
    write_json(artifact_dir / "evidence_relevance_ledger.json", routing["evidence_relevance_ledger"])
    write_json(artifact_dir / "evidence_routing_report.json", routing["evidence_routing_report"])
    write_json(artifact_dir / "deferred_evidence_audit.json", routing["deferred_evidence_audit"])


def _collect_evidence_unit_artifacts(
    payload: dict[str, Any],
    *,
    evidence_units: list[dict[str, Any]],
    quantity_tuples: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> None:
    units = payload.get("source_evidence_units")
    if isinstance(units, dict) and isinstance(units.get("units"), list):
        evidence_units.extend(row for row in units["units"] if isinstance(row, dict))
    tuples = payload.get("source_quantity_tuples")
    if isinstance(tuples, dict) and isinstance(tuples.get("tuples"), list):
        quantity_tuples.extend(row for row in tuples["tuples"] if isinstance(row, dict))
    report = payload.get("source_evidence_unit_quality_report")
    if isinstance(report, dict):
        reports.append(report)


def _aggregate_evidence_unit_quality_report(
    reports: list[dict[str, Any]],
    *,
    unit_count: int,
    quantity_tuple_count: int,
) -> dict[str, Any]:
    warning_counts: dict[str, int] = {}
    issue_count = 0
    exact_quote_count = 0
    quote_count = 0
    for report in reports:
        issue_count += len(report.get("issues", [])) if isinstance(report.get("issues"), list) else 0
        exact_quote_count += int(report.get("exact_quote_count") or 0)
        quote_count += int(report.get("quote_count") or 0)
        for key, value in (report.get("warning_counts") if isinstance(report.get("warning_counts"), dict) else {}).items():
            warning_counts[str(key)] = warning_counts.get(str(key), 0) + int(value or 0)
    return {
        "schema_id": "source_evidence_unit_quality_report_aggregate_v1",
        "status": "ready" if unit_count and not issue_count else "warning",
        "source_report_count": len(reports),
        "unit_count": unit_count,
        "quantity_tuple_count": quantity_tuple_count,
        "quote_count": quote_count,
        "exact_quote_count": exact_quote_count,
        "warning_counts": warning_counts,
        "issues": ["source_evidence_unit_source_report_issue"] * issue_count,
    }


def claim_extraction_parallelism(backend: str | None = None) -> int:
    override = os.environ.get("ECM_CLAIM_EXTRACTION_PARALLELISM")
    backend_parallelism = model_parallelism(backend)
    if override is not None:
        try:
            return max(1, int(override))
        except ValueError:
            return min(backend_parallelism, 2) if str(backend or "").strip().startswith("ollama:") else backend_parallelism
    if str(backend or "").strip().startswith("ollama:"):
        return min(backend_parallelism, 2)
    return backend_parallelism


def _retry_failed_whole_doc_results_serially(
    extraction_results: list[dict[str, Any]],
    *,
    selected_question: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    max_claims_per_source: int,
    source_dir: Path,
) -> dict[str, int]:
    attempts = 0
    recovered = 0
    failed = 0
    for index, result in enumerate(extraction_results):
        initial_error = str(result.get("backend_error") or "")
        if not initial_error:
            continue
        attempts += 1
        retry = _fetch_whole_doc_payload(
            (int(result["source_index"]), result["chunk"]),
            selected_question=selected_question,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            max_claims_per_source=max_claims_per_source,
            source_dir=source_dir,
            reuse_claim_cache=False,
        )
        retry["serial_retry_attempted"] = True
        retry["initial_backend_error"] = initial_error
        retry["backend_call_count"] = int(result.get("backend_call_count") or 0) + int(retry.get("backend_call_count") or 0)
        if retry.get("backend_error"):
            failed += 1
        else:
            recovered += 1
        extraction_results[index] = retry
    return {
        "serial_retry_attempt_count": attempts,
        "serial_retry_recovered_count": recovered,
        "serial_retry_failed_count": failed,
    }


def _fetch_whole_doc_payload(
    item: tuple[int, WholeDocSourceChunk],
    *,
    selected_question: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    max_claims_per_source: int,
    source_dir: Path,
    reuse_claim_cache: bool,
) -> dict[str, Any]:
    source_index, chunk = item
    source_file_stem = _safe_filename(chunk.source_id)
    canonical_path = source_dir / f"{source_file_stem}_whole_doc_canonical.json"
    payload, cache_hit, backend_error = whole_doc_claim_payload_for_source(
        source_id=chunk.source_id,
        source_title=chunk.title,
        source_text=chunk.plain_text,
        decision_question=selected_question,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        max_claims=max_claims_per_source,
        canonical_path=canonical_path,
        raw_path=source_dir / f"{source_file_stem}_whole_doc_raw.txt",
        repair_raw_path=source_dir / f"{source_file_stem}_whole_doc_repair_raw.txt",
        report_path=source_dir / f"{source_file_stem}_whole_doc_report.json",
        reuse_claim_cache=reuse_claim_cache,
    )
    return {
        "source_index": source_index,
        "chunk": chunk,
        "payload": payload,
        "cache_hit": cache_hit,
        "backend_error": backend_error,
        "backend_call_count": 0 if cache_hit else 1,
    }


def _whole_doc_source_chunks(repo_root: Path, case_manifest: CaseManifest, region: WorkedRegion) -> list[WholeDocSourceChunk]:
    chunks: list[WholeDocSourceChunk] = []
    for ordinal, source in enumerate(_required_sources(case_manifest, region), start=1):
        text = _source_text(repo_root, source)
        lines = text.splitlines()
        if not lines:
            continue
        spans = tuple(
            WholeDocSourceSpan(
                span_id=f"{_safe_filename(source.source_id)}_s{line_no:04d}",
                source_id=source.source_id,
                source_span=f"lines {line_no}-{line_no}",
                text=line.strip(),
            )
            for line_no, line in enumerate(lines, start=1)
            if line.strip()
        )
        chunks.append(
            WholeDocSourceChunk(
                chunk_id=_safe_filename(f"{source.source_id}_whole_doc"),
                source_id=source.source_id,
                title=source.title,
                start_line=1,
                end_line=len(lines),
                ordinal=ordinal,
                numbered_text="\n".join(f"{line_no}: {line}" for line_no, line in enumerate(lines, start=1)),
                plain_text=text,
                spans=spans,
            )
        )
    return chunks


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


def _configured_claim_roles(case_manifest: CaseManifest) -> list[str]:
    roles = config_profile_from_manifest_payload(case_manifest.epistemic_config).claim_role_ids()
    if "other" not in roles:
        roles.append("other")
    return roles
