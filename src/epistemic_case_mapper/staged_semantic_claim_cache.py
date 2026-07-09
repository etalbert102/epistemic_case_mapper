from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output


def claim_payload_for_chunk(
    *,
    prompt: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    canonical_path: Path,
    raw_path: Path,
    reuse_claim_cache: bool,
) -> tuple[dict[str, Any] | None, bool, str]:
    if reuse_claim_cache:
        cached = read_cached_claim_payload(canonical_path)
        if cached is not None:
            return cached, True, ""
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            response_schema=claim_prompt_json_schema(),
        )
        raw = result.text
    except (RuntimeError, ValueError) as exc:
        return None, False, str(exc)
    write_markdown(raw_path, raw)
    payload = _parse_model_json_local(raw)
    write_json(canonical_path, payload or {})
    return payload if isinstance(payload, dict) else None, False, ""


def _parse_model_json_local(text: str) -> dict[str, Any] | None:
    canonical = canonical_json_output(text)
    try:
        parsed = json.loads(canonical)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def read_cached_claim_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and (isinstance(payload.get("claims"), list) or "claim" in payload):
        return payload
    return None


def write_claim_progress(
    path: Path,
    progress: dict[str, Any],
    processed_chunks: int,
    current_chunk_id: str,
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> None:
    progress["processed_chunks"] = processed_chunks
    progress["current_chunk_id"] = current_chunk_id
    progress["accepted_claim_count"] = len(accepted)
    progress["rejected_claim_count"] = len(rejected)
    write_json(path, progress)


def claim_prompt_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "source_quote": {"type": "string"},
                        "span_id": {"type": "string"},
                        "entailed_by_excerpt": {"type": "string", "enum": ["yes", "no", "uncertain"]},
                        "role": {"type": "string"},
                        "question_relevance": {"type": "string", "enum": ["direct", "indirect", "scope_limit", "background", "irrelevant"]},
                        "relevance_rationale": {"type": "string"},
                        "scope_flags": {"type": "array", "items": {"type": "string"}},
                        "decision_importance": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                        "decision_function": {
                            "type": "string",
                            "enum": [
                                "answer_bearing",
                                "crux",
                                "scope_boundary",
                                "mechanism",
                                "confounder_or_bias",
                                "implementation_constraint",
                                "source_quality_caveat",
                                "background_context",
                            ],
                        },
                        "default_use": {"type": "string", "enum": ["main_map", "supporting_map", "appendix", "exclude_unless_gap"]},
                        "importance_rationale": {"type": "string"},
                    },
                    "required": ["source_quote", "claim", "span_id", "entailed_by_excerpt", "role"],
                },
            }
        },
        "required": ["claims"],
    }
