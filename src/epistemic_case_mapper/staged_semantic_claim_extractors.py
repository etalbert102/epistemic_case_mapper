from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_case_mapper.staged_semantic_claim_cache import claim_payload_for_chunk
from epistemic_case_mapper.staged_semantic_langextract import langextract_claim_payload_for_chunk


def claim_payload_for_extractor(
    *,
    claim_extractor: str,
    prompt: str,
    chunk: Any,
    selected_question: str,
    valid_roles: set[str],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    max_claims_per_chunk: int,
    canonical_path: Path,
    chunk_dir: Path,
    reuse_claim_cache: bool,
) -> tuple[dict[str, Any] | None, bool, str]:
    if claim_extractor == "native":
        return claim_payload_for_chunk(
            prompt=prompt,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            canonical_path=canonical_path,
            raw_path=chunk_dir / f"{chunk.chunk_id}_raw.txt",
            reuse_claim_cache=reuse_claim_cache,
        )
    if claim_extractor == "langextract":
        return langextract_claim_payload_for_chunk(
            chunk=chunk,
            case_question=selected_question,
            role_options=sorted(valid_roles),
            backend=backend,
            max_claims=max_claims_per_chunk,
            canonical_path=canonical_path,
            report_path=chunk_dir / f"{chunk.chunk_id}_langextract_report.json",
            reuse_claim_cache=reuse_claim_cache,
        )
    raise ValueError(f"unknown claim_extractor={claim_extractor!r}")
