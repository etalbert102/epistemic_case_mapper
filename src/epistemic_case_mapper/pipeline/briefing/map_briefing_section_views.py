from __future__ import annotations

from collections import defaultdict
from typing import Any


SECTION_ORDER = [
    "Decision Brief",
    "Why This Read",
    "Evidence Carrying the Conclusion",
    "Practical Read",
    "Practical Scope and Exceptions",
    "Decision Cruxes",
    "Limits of the Current Map",
]


def build_section_views(bundles: list[dict[str, Any]], retain_ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_section: dict[str, dict[str, list[str]]] = {
        title: {"primary_bundle_ids": [], "contrast_bundle_ids": [], "boundary_bundle_ids": [], "context_bundle_ids": [], "must_retain_item_ids": []}
        for title in SECTION_ORDER
    }
    for bundle in bundles:
        bundle_id = str(bundle.get("bundle_id"))
        for section in _string_list(bundle.get("section_targets")) or _default_sections_for_role(str(bundle.get("decision_role", ""))):
            slot = _section_slot_for_role(str(bundle.get("decision_role", "")))
            by_section.setdefault(section, {"primary_bundle_ids": [], "contrast_bundle_ids": [], "boundary_bundle_ids": [], "context_bundle_ids": [], "must_retain_item_ids": []})
            by_section[section][slot].append(bundle_id)
    for item in retain_ledger:
        for section in _string_list(item.get("section_targets")) or ["Evidence Carrying the Conclusion"]:
            by_section.setdefault(section, {"primary_bundle_ids": [], "contrast_bundle_ids": [], "boundary_bundle_ids": [], "context_bundle_ids": [], "must_retain_item_ids": []})
            by_section[section]["must_retain_item_ids"].append(str(item.get("item_id")))
    _add_job_aware_section_routes(by_section, bundles)
    views = []
    for title, rows in by_section.items():
        view = {
            "section": title,
            "section_job": _section_job(title),
            "primary_bundle_ids": _dedupe(rows["primary_bundle_ids"])[:8],
            "contrast_bundle_ids": _dedupe(rows["contrast_bundle_ids"])[:5],
            "boundary_bundle_ids": _dedupe(rows["boundary_bundle_ids"])[:5],
            "context_bundle_ids": _dedupe(rows["context_bundle_ids"])[:4],
            "must_retain_item_ids": _dedupe(rows["must_retain_item_ids"])[:8],
        }
        if any(view[key] for key in ("primary_bundle_ids", "contrast_bundle_ids", "boundary_bundle_ids", "context_bundle_ids", "must_retain_item_ids")):
            views.append(view)
    return views


def _add_job_aware_section_routes(by_section: dict[str, dict[str, list[str]]], bundles: list[dict[str, Any]]) -> None:
    by_role: dict[str, list[str]] = defaultdict(list)
    for bundle in bundles:
        bundle_id = str(bundle.get("bundle_id") or "")
        role = str(bundle.get("decision_role") or "")
        if bundle_id and role:
            by_role[role].append(bundle_id)
    _ensure_section_routes(
        by_section,
        "Why This Read",
        primary=by_role.get("strongest_support", [])[:3] + by_role.get("quantitative_anchor", [])[:2],
        contrast=by_role.get("counterweight", [])[:3],
        boundary=by_role.get("scope_boundary", [])[:2],
    )
    _ensure_section_routes(
        by_section,
        "Evidence Carrying the Conclusion",
        primary=by_role.get("strongest_support", [])[:5] + by_role.get("quantitative_anchor", [])[:4],
        contrast=by_role.get("counterweight", [])[:2],
    )
    _ensure_section_routes(
        by_section,
        "Practical Read",
        primary=by_role.get("strongest_support", [])[:2],
        contrast=by_role.get("counterweight", [])[:2],
        boundary=by_role.get("scope_boundary", [])[:3],
    )


def _ensure_section_routes(
    by_section: dict[str, dict[str, list[str]]],
    section: str,
    *,
    primary: list[str] | None = None,
    contrast: list[str] | None = None,
    boundary: list[str] | None = None,
) -> None:
    by_section.setdefault(section, {"primary_bundle_ids": [], "contrast_bundle_ids": [], "boundary_bundle_ids": [], "context_bundle_ids": [], "must_retain_item_ids": []})
    by_section[section]["primary_bundle_ids"].extend(primary or [])
    by_section[section]["contrast_bundle_ids"].extend(contrast or [])
    by_section[section]["boundary_bundle_ids"].extend(boundary or [])


def _default_sections_for_role(role: str) -> list[str]:
    if role in {"strongest_support", "quantitative_anchor", "mechanism"}:
        return ["Evidence Carrying the Conclusion"]
    if role == "counterweight":
        return ["Why This Read", "Decision Cruxes"]
    if role == "scope_boundary":
        return ["Practical Scope and Exceptions"]
    if role == "decision_crux":
        return ["Decision Cruxes"]
    return ["Why This Read"]


def _section_slot_for_role(role: str) -> str:
    if role == "counterweight":
        return "contrast_bundle_ids"
    if role == "scope_boundary":
        return "boundary_bundle_ids"
    if role == "context":
        return "context_bundle_ids"
    return "primary_bundle_ids"


def _section_job(title: str) -> str:
    if title == "Decision Brief":
        return "State the answer, confidence, and central reason."
    if title == "Why This Read":
        return "Explain the reasoning path and most important tension."
    if title == "Evidence Carrying the Conclusion":
        return "Identify the evidence doing the most work and its quantitative anchors."
    if title == "Practical Read":
        return "Translate the answer into decision-relevant practical implications."
    if title == "Practical Scope and Exceptions":
        return "Bound the answer and name exceptions or population limits."
    if title == "Decision Cruxes":
        return "Name what would change the answer."
    return "Name map limits, uncertainty, and missing evidence."


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
