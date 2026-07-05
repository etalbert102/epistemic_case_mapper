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
    section_titles = [section["title"] for section in body_sections]
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
        reference_styles = {title: _reference_style_for_section(title, owner, row) for title in section_titles if title != owner}
        ownership["rows"][key] = {
            "owner": owner,
            "primary_owner_section": owner,
            "mentioned_sections": mentioned,
            "allowed_reference_sections": [title for title, style in reference_styles.items() if style != "do_not_repeat"],
            "reference_style_by_section": reference_styles,
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
    owner = str(item.get("owner", "")).strip()
    return {
        "slot": row.get("slot"),
        "owner_section": owner,
        "reference_style": "short_reference" if owner else "full",
        "reference_instruction": (
            f"Do not restate this evidence here; if needed, use a short cross-reference to {owner}."
            if owner
            else "This section may carry the full evidence."
        ),
        "role_summary": _short_text(str(row.get("claim", "")), 120),
        "source": row.get("source"),
    }


def repeated_owned_evidence_issues(title: str, text: str, full_contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    rows = full_contract.get("owned_elsewhere_evidence")
    if not isinstance(rows, list):
        rows = [
            row for row in full_contract.get("required_evidence", [])
            if isinstance(row, dict) and not section_owns_evidence(title, row, full_contract)
        ]
    for row in rows:
        if not isinstance(row, dict):
            continue
        policy = row.get("reference_policy", {}) if isinstance(row.get("reference_policy"), dict) else evidence_reference_policy(title, row, full_contract)
        if policy.get("reference_style") == "full":
            continue
        if _rewrite_mentions_anchor_row(text, row):
            owner = str(policy.get("owner_section", "")).strip() or "another section"
            issues.append(f"section repeats evidence owned by {owner}: {str(row.get('claim', ''))[:90]}")
    return issues[:6]


def evidence_reference_policy(title: str, row: dict[str, Any], full_contract: dict[str, Any]) -> dict[str, Any]:
    item = _ownership_item(row, full_contract)
    owner = str(item.get("owner", "")).strip()
    if not owner or owner == title:
        return {"owner_section": owner, "reference_style": "full", "allowed": True}
    styles = item.get("reference_style_by_section", {}) if isinstance(item.get("reference_style_by_section"), dict) else {}
    style = str(styles.get(title, _reference_style_for_section(title, owner, row))).strip() or "short_reference"
    return {
        "owner_section": owner,
        "reference_style": style,
        "allowed": style != "do_not_repeat",
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


def _reference_style_for_section(title: str, owner: str, row: dict[str, Any]) -> str:
    if title == owner:
        return "full"
    lowered_title = title.lower()
    slot = str(row.get("slot", "")).lower()
    if "decision brief" in lowered_title:
        return "short_reference"
    if "evidence carrying" in lowered_title and owner in {"Why This Read", "Practical Scope and Exceptions"}:
        return "short_reference"
    if "why this read" in lowered_title and owner == "Evidence Carrying the Conclusion":
        return "short_reference"
    if "scope" in lowered_title and any(marker in slot for marker in ("scope", "subgroup", "dose", "default population")):
        return "short_reference"
    if "limits" in lowered_title:
        return "short_reference"
    return "do_not_repeat"


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."
