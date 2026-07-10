from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import model_parallelism, run_model_backend
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.staged_semantic_prompt_schemas import relation_json_schema
from epistemic_case_mapper.staged_semantic_sources import (
    _parse_relation_model_json,
    _relation_batch_prompt,
    _relation_pair_prompt,
)
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion


@dataclass(frozen=True)
class RelationBatchResult:
    batch_index: int
    batch_id: str
    batch: list[dict[str, Any]]
    artifact_subdir: str
    artifact_stem: str
    payload: dict[str, Any] | None
    raw: str | None = None
    backend_error: str = ""


def run_relation_batch_backend(
    item: tuple[int, list[dict[str, Any]]],
    *,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    decision_question: str | None,
) -> RelationBatchResult:
    batch_index, batch = item
    batch_id = f"batch_{batch_index:03d}"
    prompt = (
        _relation_pair_prompt(manifest, region, case_manifest, batch[0], decision_question=decision_question)
        if len(batch) == 1
        else _relation_batch_prompt(manifest, region, case_manifest, batch, batch_id, decision_question=decision_question)
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
            response_schema=relation_json_schema(batch=len(batch) > 1),
        )
    except (RuntimeError, ValueError) as exc:
        return RelationBatchResult(
            batch_index=batch_index,
            batch_id=batch_id,
            batch=batch,
            artifact_subdir=artifact_subdir,
            artifact_stem=artifact_stem,
            payload=None,
            backend_error=str(exc),
        )
    raw = result.text
    write_markdown(artifact_dir / artifact_subdir / f"{artifact_stem}_raw.txt", raw)
    payload = _parse_relation_model_json(raw)
    write_json(artifact_dir / artifact_subdir / f"{artifact_stem}_canonical.json", payload or {})
    return RelationBatchResult(
        batch_index=batch_index,
        batch_id=batch_id,
        batch=batch,
        artifact_subdir=artifact_subdir,
        artifact_stem=artifact_stem,
        payload=payload,
        raw=raw,
    )


def write_relation_batch_report(artifact_dir: Path, backend: str, batch_results: list[RelationBatchResult]) -> None:
    write_json(
        artifact_dir / "relation_batch_report.json",
        {
            "schema_id": "relation_batch_report_v1",
            "parallelism": model_parallelism(backend),
            "batch_count": len(batch_results),
            "backend_error_count": sum(1 for result in batch_results if result.backend_error),
            "invalid_json_count": sum(1 for result in batch_results if _invalid_payload(result)),
            "batches": [_relation_batch_report_row(result) for result in batch_results],
        },
    )


def _invalid_payload(result: RelationBatchResult) -> bool:
    return not result.backend_error and not isinstance(result.payload, dict)


def _relation_batch_report_row(result: RelationBatchResult) -> dict[str, Any]:
    return {
        "batch_index": result.batch_index,
        "batch_id": result.batch_id,
        "pair_count": len(result.batch),
        "pair_ids": [packet["pair_id"] for packet in result.batch],
        "status": _relation_batch_status(result),
        "backend_error": result.backend_error,
        "prompt_path": f"{result.artifact_subdir}/{result.artifact_stem}_prompt.txt",
        "raw_path": f"{result.artifact_subdir}/{result.artifact_stem}_raw.txt" if result.raw is not None else "",
        "canonical_path": f"{result.artifact_subdir}/{result.artifact_stem}_canonical.json" if result.raw is not None else "",
    }


def _relation_batch_status(result: RelationBatchResult) -> str:
    if result.backend_error:
        return "backend_error"
    if isinstance(result.payload, dict):
        return "completed"
    return "invalid_json"
