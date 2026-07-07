from __future__ import annotations

import re
from typing import Any


def build_section_use_projections(title: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project reusable evidence cards into section-specific discourse uses."""
    section_kind = _section_kind(title)
    projections: list[dict[str, Any]] = []
    for row in evidence:
        if not isinstance(row, dict):
            continue
        projection = _section_use_projection(section_kind, row)
        if projection:
            projections.append(projection)
    return projections[:8]


def projection_guidance(title: str) -> str:
    section_kind = _section_kind(title)
    if section_kind == "practical_read":
        return "Convert reused evidence into bounded decision implications; do not restate study details unless needed to name a boundary."
    if section_kind == "why_this_read":
        return "Use reused evidence to explain the reasoning path; do not list studies or write practical advice."
    if section_kind == "evidence_carrying":
        return "Use reused evidence to compare weight, direction, and limits; this is the main place for source-level detail."
    if section_kind == "scope":
        return "Use reused evidence to state where the answer applies, fails, or needs exception handling."
    if section_kind == "decision_brief":
        return "Use reused evidence only as top support or top caveat for the answer frame."
    if section_kind == "cruxes":
        return "Use reused evidence to form decision-changing conditions, not evidence summaries."
    if section_kind == "limits":
        return "Use reused evidence only to identify missing evidence, uncertainty, or confidence limits."
    return "Use reused evidence only when it adds this section's distinct analytic value."


def _section_use_projection(section_kind: str, row: dict[str, Any]) -> dict[str, Any]:
    card_id = str(row.get("candidate_card_id") or row.get("spine_field_id") or "").strip()
    claim = str(row.get("claim") or row.get("source_excerpt") or "").strip()
    role = _source_role(row)
    section_use = _section_use(section_kind, role)
    value = _expected_value(section_kind, role)
    avoid = _avoid_repeating_as(section_kind)
    return _drop_empty(
        {
            "candidate_card_id": card_id,
            "source_role": role,
            "section_use": section_use,
            "expected_section_value": value,
            "avoid_repeating_as": avoid,
            "claim_hint": _short_text(claim, 180),
        }
    )


def _section_kind(title: str) -> str:
    key = str(title).lower()
    if "decision brief" in key:
        return "decision_brief"
    if "practical read" in key:
        return "practical_read"
    if "why this read" in key:
        return "why_this_read"
    if "evidence carrying" in key:
        return "evidence_carrying"
    if "scope" in key or "exception" in key:
        return "scope"
    if "crux" in key:
        return "cruxes"
    if "limit" in key:
        return "limits"
    return "general"


def _source_role(row: dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(key, ""))
        for key in ("intended_role", "slot", "spine_field_id", "quality", "claim", "limitations")
    ).lower()
    if any(term in text for term in ("counter", "higher risk", "harm", "challenge", "weakens", "tension")):
        return "counterweight"
    if any(term in text for term in ("scope", "boundary", "population", "subgroup", "dose", "exception")):
        return "scope_boundary"
    if any(term in text for term in ("mechanism", "pathway", "surrogate", "biomarker", "marker", "endpoint")):
        return "mechanism"
    if row.get("quantity_values") or re.search(r"\b\d+(?:\.\d+)?\b|%|percent|fold|per day|per week", text):
        return "quantity_anchor"
    if any(term in text for term in ("indirect", "heterogeneity", "missing", "limit", "uncertain")):
        return "method_limit"
    if any(term in text for term in ("crux", "would change", "decision-changing")):
        return "crux_input"
    if any(term in text for term in ("recommend", "guidance", "practical", "implementation")):
        return "practical_implication"
    return "answer_support"


def _section_use(section_kind: str, source_role: str) -> str:
    if section_kind == "practical_read":
        return "practical_implication" if source_role != "method_limit" else "confidence_boundary"
    if section_kind == "why_this_read":
        return "reasoning_support" if source_role != "counterweight" else "reasoning_counterweight"
    if section_kind == "evidence_carrying":
        return "evidence_weight"
    if section_kind == "scope":
        return "scope_boundary" if source_role != "counterweight" else "exception_case"
    if section_kind == "decision_brief":
        return "top_caveat" if source_role in {"counterweight", "method_limit"} else "top_support"
    if section_kind == "cruxes":
        return "crux_input"
    if section_kind == "limits":
        return "method_limit"
    return source_role


def _expected_value(section_kind: str, source_role: str) -> str:
    if section_kind == "practical_read":
        return "State what bounded decision implication follows from this evidence."
    if section_kind == "why_this_read":
        return "Explain why this evidence changes or bounds the reasoning path."
    if section_kind == "evidence_carrying":
        return "Describe the evidence direction, strength, and limitation."
    if section_kind == "scope":
        return "Translate this evidence into an applicability boundary or exception."
    if section_kind == "decision_brief":
        return "Use as one concise support or caveat for the answer."
    if section_kind == "cruxes":
        return "Convert this evidence into a condition that could change the decision."
    if section_kind == "limits":
        return "Use this evidence to name an uncertainty or missing-evidence boundary."
    return f"Use as {source_role} only if it adds local analytic value."


def _avoid_repeating_as(section_kind: str) -> list[str]:
    common = ["generic source summary", "study-by-study restatement"]
    if section_kind == "practical_read":
        return common + ["evidence weighing paragraph", "imperative advice unsupported by the packet"]
    if section_kind == "why_this_read":
        return common + ["practical advice", "scope exception list"]
    if section_kind == "evidence_carrying":
        return ["recommendation", "decision action", "scope-only exception list"]
    if section_kind == "scope":
        return common + ["full evidence weighing", "bottom-line recommendation"]
    if section_kind == "decision_brief":
        return common + ["multi-study literature review"]
    return common


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    return cleaned if len(cleaned) <= max_chars else cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ({}, [], "", None)}
