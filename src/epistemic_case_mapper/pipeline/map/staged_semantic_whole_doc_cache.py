from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


WHOLE_DOC_CLAIM_PROMPT_VERSION = "whole_doc_source_card_claim_extraction_v12_explicit_entailment_cache_identity_json"
WHOLE_DOC_REPAIR_PROMPT_VERSION = "whole_doc_source_card_schema_repair_v12_explicit_entailment_cache_identity_json"
DEFAULT_WHOLE_DOC_NUM_PREDICT = 8192
DEFAULT_WHOLE_DOC_NUM_PREDICT_MAX = 16384


def whole_doc_extraction_cache_context(
    source_id: str,
    source_title: str,
    source_text: str,
    decision_question: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    requested_max_claims: int,
) -> tuple[int, int, dict[str, Any]]:
    effective_max_claims = effective_whole_doc_claim_cap(source_text, requested_max_claims)
    num_predict = whole_doc_num_predict(source_text, effective_max_claims)
    identity = whole_doc_cache_identity(
        source_id=source_id,
        source_title=source_title,
        source_text=source_text,
        decision_question=decision_question,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        requested_max_claims=requested_max_claims,
        effective_max_claims=effective_max_claims,
        num_predict=num_predict,
    )
    return effective_max_claims, num_predict, identity


def effective_whole_doc_claim_cap(source_text: str, requested_max_claims: int) -> int:
    """Allow long documents to preserve distinct result clusters."""

    base = max(1, int(requested_max_claims))
    hard_cap = max(base, _int_env("ECM_WHOLE_DOC_MAX_CLAIMS_CAP", 24))
    extra = (max(0, len(source_text)) // 20_000) * 2
    return min(hard_cap, base + extra)


def whole_doc_num_predict(source_text: str, effective_max_claims: int) -> int:
    override = _int_env("ECM_WHOLE_DOC_OLLAMA_NUM_PREDICT", 0)
    if override > 0:
        return override
    global_default = _int_env("ECM_OLLAMA_NUM_PREDICT", 2048)
    max_budget = max(
        DEFAULT_WHOLE_DOC_NUM_PREDICT,
        _int_env("ECM_WHOLE_DOC_OLLAMA_NUM_PREDICT_MAX", DEFAULT_WHOLE_DOC_NUM_PREDICT_MAX),
    )
    long_doc_extra = (max(0, len(source_text)) // 50_000) * 2048
    claim_extra = max(0, int(effective_max_claims) - 8) * 512
    budget = max(DEFAULT_WHOLE_DOC_NUM_PREDICT, global_default) + long_doc_extra + claim_extra
    return min(max_budget, max(1024, budget))


def whole_doc_cache_identity(
    *,
    source_id: str,
    source_title: str,
    source_text: str,
    decision_question: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    requested_max_claims: int,
    effective_max_claims: int,
    num_predict: int,
) -> dict[str, Any]:
    return {
        "schema_id": "whole_doc_claim_cache_identity_v1",
        "source_id": str(source_id),
        "source_sha256": _text_sha256(source_text),
        "source_title_sha256": _text_sha256(source_title),
        "decision_question_sha256": _text_sha256(decision_question),
        "backend_identity_sha256": _text_sha256(backend),
        "prompt_version": WHOLE_DOC_CLAIM_PROMPT_VERSION,
        "repair_prompt_version": WHOLE_DOC_REPAIR_PROMPT_VERSION,
        "settings": {
            "backend_timeout": backend_timeout,
            "backend_retries": int(backend_retries),
            "requested_max_claims": int(requested_max_claims),
            "effective_max_claims": int(effective_max_claims),
            "num_predict": int(num_predict),
        },
    }


def read_cached_whole_doc_payload(path: Path, *, expected_identity: dict[str, Any]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        isinstance(payload, dict)
        and isinstance(payload.get("claims"), list)
        and payload.get("cache_identity") == expected_identity
        and payload.get("prompt_version") == WHOLE_DOC_CLAIM_PROMPT_VERSION
    ):
        return payload
    return None


def _text_sha256(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default
