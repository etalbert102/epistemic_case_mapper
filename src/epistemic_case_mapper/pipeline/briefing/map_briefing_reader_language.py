from __future__ import annotations

import re
from typing import Any


PROTECTED_TEXT_KEYS = {
    "audit_claim",
    "card_id",
    "item_id",
    "method",
    "obligation_id",
    "obligation_type",
    "quantity_type",
    "heading",
    "primary_section",
    "retention_phrase",
    "role",
    "schema_id",
    "section",
    "source_id",
    "source_ids",
    "source_label",
    "source_labels",
    "status",
    "title",
    "validation_mode",
    "validation_terms",
    "value",
}


def project_reader_language_for_model(payload: Any) -> Any:
    """Return a model-facing copy with internal prose terms translated for readers."""

    return _project(payload, key="")


def normalize_reader_language(text: str) -> str:
    normalized = str(text or "")
    for pattern, replacement in _READER_LANGUAGE_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized


def _project(value: Any, *, key: str) -> Any:
    if isinstance(value, dict):
        return {str(child_key): _project(child_value, key=str(child_key)) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_project(item, key=key) for item in value]
    if isinstance(value, str) and key not in PROTECTED_TEXT_KEYS:
        return normalize_reader_language(value)
    return value


_READER_LANGUAGE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bdefault read\b", "default answer"),
    (r"\bcurrent read\b", "current answer"),
    (r"\bfinal read\b", "final answer"),
    (r"\bdecision read\b", "answer"),
    (r"\bbaseline risk read\b", "risk interpretation"),
    (r"\bbaseline low-concern read\b", "default low-concern interpretation"),
    (r"\bevidence-bounded reference point\b", "practical reference point"),
    (r"\bmust-write cards\b", "required points"),
    (r"\bmust-write card\b", "required point"),
    (r"\bretention contract\b", "required evidence to preserve"),
    (r"\bchecklist rhythm\b", "list-like rhythm"),
    (r"\bsource-label-as-subject patterns?\b", "source names as repeated sentence subjects"),
    (r"\bcounterweights\b", "limiting evidence"),
    (r"\bcounterweight\b", "limiting evidence"),
)
