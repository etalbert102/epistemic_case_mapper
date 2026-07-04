from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_slots import _rewrite_mentions_anchor_row


def build_section_evidence_ownership(sections: list[dict[str, str]], contract: dict[str, Any]) -> dict[str, Any]:
    ownership: dict[str, Any] = {
        "schema_id": "section_evidence_ownership_v1",
        "rows": {},
        "owner_counts": {},
    }
    body_sections = [section for section in sections if section["title"] != "Decision Brief"]
    for row in contract.get("required_evidence", []) if isinstance(contract.get("required_evidence"), list) else []:
        if not isinstance(row, dict):
            continue
        key = evidence_row_key(row)
        if not key:
            continue
        mentioned = [
            section["title"]
            for section in body_sections
            if _rewrite_mentions_anchor_row(section["markdown"], row)
        ]
        owner = _preferred_evidence_owner(row, mentioned)
        if not owner and mentioned:
            owner = mentioned[0]
        if not owner:
            continue
        ownership["rows"][key] = {
            "owner": owner,
            "mentioned_sections": mentioned,
            "slot": row.get("slot"),
            "claim": row.get("claim"),
            "source": row.get("source"),
        }
        ownership["owner_counts"][owner] = int(ownership["owner_counts"].get(owner, 0)) + 1
    return ownership


def section_owns_evidence(title: str, row: dict[str, Any], full_contract: dict[str, Any]) -> bool:
    item = _ownership_item(row, full_contract)
    owner = str(item.get("owner", "")).strip()
    return not owner or owner == title


def compact_evidence_reference(row: dict[str, Any], full_contract: dict[str, Any]) -> dict[str, Any]:
    item = _ownership_item(row, full_contract)
    return {
        "slot": row.get("slot"),
        "owner_section": item.get("owner"),
        "role_summary": _short_text(str(row.get("claim", "")), 120),
        "source": row.get("source"),
    }


def evidence_row_key(row: dict[str, Any]) -> str:
    source = re.sub(r"\s+", " ", str(row.get("source", "")).strip().lower())
    claim = re.sub(r"\s+", " ", str(row.get("claim", "")).strip().lower())
    return f"{source}::{claim}" if claim else ""


def _ownership_item(row: dict[str, Any], full_contract: dict[str, Any]) -> dict[str, Any]:
    ownership = (
        full_contract.get("_section_evidence_ownership", {})
        if isinstance(full_contract.get("_section_evidence_ownership"), dict)
        else {}
    )
    rows = ownership.get("rows", {}) if isinstance(ownership.get("rows"), dict) else {}
    item = rows.get(evidence_row_key(row), {})
    return item if isinstance(item, dict) else {}


def _preferred_evidence_owner(row: dict[str, Any], mentioned: list[str]) -> str:
    if not mentioned:
        return ""
    slot = str(row.get("slot", "")).lower()
    claim = str(row.get("claim", "")).lower()
    preference: list[str] = []
    if any(marker in slot for marker in ("high-risk", "subgroup", "default population", "dose boundary", "scope")):
        preference = ["Practical Scope and Exceptions", "Practical Read", "Evidence Carrying the Conclusion", "Why This Read"]
    elif any(marker in slot for marker in ("mechanism", "surrogate", "hard-outcome", "study-design", "support", "counterevidence")):
        preference = ["Evidence Carrying the Conclusion", "Why This Read", "Practical Scope and Exceptions"]
    elif any(marker in claim for marker in ("associated with", "risk", "cohort", "trial", "meta-analysis")):
        preference = ["Evidence Carrying the Conclusion", "Why This Read", "Practical Scope and Exceptions"]
    else:
        preference = ["Why This Read", "Evidence Carrying the Conclusion", "Practical Scope and Exceptions"]
    for title in preference:
        if title in mentioned:
            return title
    return mentioned[0]


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."
