from __future__ import annotations

import re
from typing import Any


def normalize_recommended_edit(edit: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(edit)
    target_ids = _string_list(normalized.get("target_ids"))
    if not target_ids and str(normalized.get("target_id", "")).strip():
        target_ids = [str(normalized.get("target_id", "")).strip()]
    if not target_ids and str(normalized.get("bundle_id", "")).strip():
        target_ids = [str(normalized.get("bundle_id", "")).strip()]
    if target_ids:
        normalized["target_ids"] = target_ids
    if not normalized.get("rationale") and normalized.get("description"):
        normalized["rationale"] = normalized.get("description")
    if normalized.get("edit_type") == "insufficiency_warning":
        normalized["edit_type"] = "add_warning"
        if normalized.get("description") and not normalized.get("warning"):
            normalized["warning"] = normalized.get("description")
    if normalized.get("edit_type") == "relabel" and not str(normalized.get("recommended_role", "")).strip():
        inferred = _infer_recommended_role_from_text(
            " ".join(
                item
                for item in (
                    str(normalized.get("rationale", "")),
                    str(normalized.get("description", "")),
                    str(normalized.get("warning", "")),
                )
                if item.strip()
            )
        )
        if inferred:
            normalized["recommended_role"] = inferred
    return normalized


def _infer_recommended_role_from_text(text: str) -> str:
    lowered = text.lower()
    roles = (
        "strongest_support",
        "counterweight",
        "scope_boundary",
        "quantitative_anchor",
        "decision_crux",
        "mechanism/context",
        "mechanism",
        "context",
    )
    phrase_map = {
        "strongest support": "strongest_support",
        "primary support": "strongest_support",
        "scope boundary": "scope_boundary",
        "quantitative anchor": "quantitative_anchor",
        "decision crux": "decision_crux",
    }
    for role in roles:
        if re.search(rf"\bto\s+{re.escape(role)}\b", lowered):
            return role
    for phrase, role in phrase_map.items():
        if re.search(rf"\bto\s+{re.escape(phrase)}\b", lowered):
            return role
    for role in roles:
        if role in lowered:
            return role
    for phrase, role in phrase_map.items():
        if phrase in lowered:
            return role
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
