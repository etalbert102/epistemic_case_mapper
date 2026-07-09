from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.config_profiles import config_profile_from_manifest_payload
from epistemic_case_mapper.io import write_json
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.staged_semantic_claim_cache import write_claim_progress
from epistemic_case_mapper.staged_semantic_decision_questions import claim_decision_relevance_rejection_reason, region_decision_question
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    claim_index = 1
    valid_roles = set(_configured_claim_roles(case_manifest))
    source_chunks = _whole_doc_source_chunks(repo_root, case_manifest, region)
    progress = {
        "schema_id": "claim_extraction_progress_v1",
        "stage": "whole_doc_claim_extraction",
        "total_chunks": len(source_chunks),
        "processed_chunks": 0,
        "cache_hit_count": 0,
        "backend_call_count": 0,
        "fallback_claim_count": 0,
        "accepted_claim_count": 0,
        "rejected_claim_count": 0,
        "claim_alignment_status_counts": {},
        "current_chunk_id": "",
        "complete": False,
        "claim_extractor": "whole-doc",
    }
    progress_path = artifact_dir / "claim_extraction_progress.json"
    selected_question = region_decision_question(region, case_manifest, decision_question)
    source_dir = artifact_dir / "claim_sources"
    for source_index, chunk in enumerate(source_chunks, start=1):
        span_lookup = {span.span_id: span for span in chunk.spans}
        canonical_path = source_dir / f"{chunk.chunk_id}_whole_doc_canonical.json"
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
            raw_path=source_dir / f"{chunk.chunk_id}_whole_doc_raw.txt",
            repair_raw_path=source_dir / f"{chunk.chunk_id}_whole_doc_repair_raw.txt",
            report_path=source_dir / f"{chunk.chunk_id}_whole_doc_report.json",
            reuse_claim_cache=reuse_claim_cache,
        )
        if cache_hit:
            progress["cache_hit_count"] += 1
        else:
            progress["backend_call_count"] += 1
        if backend_error:
            rejected.append({"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": "backend_error", "error": backend_error})
            write_claim_progress(progress_path, progress, source_index, chunk.chunk_id, accepted, rejected)
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
            rejected.append({"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": "invalid_whole_doc_payload"})
            write_claim_progress(progress_path, progress, source_index, chunk.chunk_id, accepted, rejected)
            continue
        for proposal in payload["claims"]:
            claim, reason = _normalize_claim_proposal(proposal, span_lookup, valid_roles)
            if claim is None:
                rejected.append({"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": reason, "proposal": proposal})
                continue
            relevance_reason = claim_decision_relevance_rejection_reason(claim, selected_question)
            if relevance_reason:
                rejected.append({"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": relevance_reason, "proposal": proposal})
                continue
            key = _claim_dedupe_key(claim)
            if key in seen:
                rejected.append({"chunk_id": chunk.chunk_id, "source_id": chunk.source_id, "reason": "duplicate_claim", "proposal": proposal})
                continue
            seen.add(key)
            claim["extraction_method"] = "whole_doc_source_card"
            claim_index = _record_accepted_claim(claim, accepted, progress, region.id_prefix, claim_index)
        write_claim_progress(progress_path, progress, source_index, chunk.chunk_id, accepted, rejected)
    progress["complete"] = True
    progress["current_chunk_id"] = ""
    progress["processed_chunks"] = len(source_chunks)
    progress["accepted_claim_count"] = len(accepted)
    progress["rejected_claim_count"] = len(rejected)
    write_json(progress_path, progress)
    write_json(artifact_dir / "accepted_claims.json", {"claims": accepted, "rejected": rejected})
    return accepted, rejected


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
