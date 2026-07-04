from __future__ import annotations

import re
from typing import Any


def build_decision_cruxes(
    *,
    scaffold: dict[str, Any],
    central_tensions: list[dict[str, str]],
    scope_boundaries: list[dict[str, str]],
    exceptions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    cruxes: list[dict[str, Any]] = []
    for tension in graph_packet.get("central_tensions", []) if isinstance(graph_packet.get("central_tensions"), list) else []:
        if isinstance(tension, dict):
            cruxes.append(_crux_from_graph_tension(tension))
    for claim in graph_packet.get("bridge_claims", []) if isinstance(graph_packet.get("bridge_claims"), list) else []:
        if isinstance(claim, dict):
            cruxes.append(_crux_from_bridge_claim(claim))
    for tension in central_tensions:
        cruxes.append(_crux_from_synthesis_tension(tension))
    for boundary in scope_boundaries:
        cruxes.append(_crux_from_boundary(boundary))
    for exception in exceptions:
        cruxes.append(_crux_from_exception(exception))
    return _dedupe_cruxes([row for row in cruxes if _valid_crux(row)])[:5]


def _crux_from_graph_tension(tension: dict[str, Any]) -> dict[str, Any]:
    left = tension.get("left", {}) if isinstance(tension.get("left"), dict) else {}
    right = tension.get("right", {}) if isinstance(tension.get("right"), dict) else {}
    pattern = _relation_pattern(left, right, tension)
    left_claim = _clean_claim(str(left.get("claim", "")))
    right_claim = _clean_claim(str(right.get("claim", "")))
    uncertainty = _uncertainty_for_pattern(pattern, left_claim, right_claim)
    current = _current_read_for_pattern(pattern, left_claim, right_claim, str(tension.get("rationale") or tension.get("why_it_matters") or ""))
    effect = _decision_effect_for_pattern(pattern)
    return {
        "crux": uncertainty,
        "uncertainty": uncertainty,
        "current_read": current,
        "decision_effect": effect,
        "would_change_if": _would_change_for_pattern(pattern),
        "supporting_claim_ids": _ids_for_direction(left, right, support=True),
        "challenging_claim_ids": _ids_for_direction(left, right, support=False),
        "relation_ids": [str(tension.get("relation_id", "")).strip()] if str(tension.get("relation_id", "")).strip() else [],
        "crux_type": pattern,
    }


def _crux_from_bridge_claim(claim: dict[str, Any]) -> dict[str, Any]:
    text = _clean_claim(str(claim.get("claim", "")))
    pattern = _claim_pattern(claim)
    uncertainty = _uncertainty_from_claim(pattern, text)
    return {
        "crux": uncertainty,
        "uncertainty": uncertainty,
        "current_read": text,
        "decision_effect": _decision_effect_for_pattern(pattern),
        "would_change_if": _would_change_for_pattern(pattern),
        "supporting_claim_ids": [str(claim.get("claim_id", "")).strip()] if str(claim.get("claim_id", "")).strip() else [],
        "challenging_claim_ids": [],
        "relation_ids": [],
        "crux_type": pattern,
    }


def _crux_from_synthesis_tension(tension: dict[str, str]) -> dict[str, Any]:
    label = _clean_claim(str(tension.get("tension", "")))
    pattern = _text_pattern(label + " " + str(tension.get("why_reasonable_people_disagree", "")))
    uncertainty = _uncertainty_from_claim(pattern, label)
    return {
        "crux": uncertainty,
        "uncertainty": uncertainty,
        "current_read": _clean_claim(str(tension.get("current_resolution", ""))) or label,
        "decision_effect": _decision_effect_for_pattern(pattern),
        "would_change_if": _would_change_for_pattern(pattern),
        "supporting_claim_ids": [],
        "challenging_claim_ids": [],
        "relation_ids": [],
        "crux_type": pattern,
    }


def _crux_from_boundary(boundary: dict[str, str]) -> dict[str, Any]:
    boundary_type = str(boundary.get("boundary_type", "scope")).replace("_", " ")
    current = _clean_claim(str(boundary.get("current_read", "")))
    pattern = "dose_boundary" if "dose" in boundary_type else "scope_boundary"
    return {
        "crux": f"Whether the mapped {boundary_type} boundary is the right boundary for the target decision",
        "uncertainty": f"Whether the mapped {boundary_type} boundary is the right boundary for the target decision",
        "current_read": current,
        "decision_effect": "This determines how far the default recommendation can be generalized.",
        "would_change_if": "The recommendation would change if direct evidence showed the mapped boundary fails inside the target case or safely extends beyond it.",
        "supporting_claim_ids": [],
        "challenging_claim_ids": [],
        "relation_ids": [],
        "crux_type": pattern,
    }


def _crux_from_exception(exception: dict[str, str]) -> dict[str, Any]:
    current = _clean_claim(str(exception.get("current_read", "")))
    return {
        "crux": "Whether the named exception is strong enough to narrow the default recommendation",
        "uncertainty": "Whether the named exception is strong enough to narrow the default recommendation",
        "current_read": current,
        "decision_effect": "This determines whether the default answer applies broadly or must be split by subgroup or risk profile.",
        "would_change_if": "The recommendation would change if direct evidence showed the exception is immaterial, applies at ordinary exposure levels, or applies to a broader target group.",
        "supporting_claim_ids": [],
        "challenging_claim_ids": [],
        "relation_ids": [],
        "crux_type": "subgroup_exception",
    }


def _relation_pattern(left: dict[str, Any], right: dict[str, Any], tension: dict[str, Any]) -> str:
    combined = " ".join((_claim_bundle(left), _claim_bundle(right), str(tension.get("rationale", "")), str(tension.get("why_it_matters", ""))))
    concepts = set(_strings(left.get("decision_concepts"))) | set(_strings(right.get("decision_concepts")))
    if "surrogate_or_biomarker_endpoint" in concepts and "hard_outcome_endpoint" in concepts:
        return "biomarker_vs_hard_outcome"
    if "subgroup_diabetes_or_metabolic_risk" in concepts or _has_any(combined, ("subgroup", "diabetes", "high-risk", "high risk")):
        return "subgroup_exception"
    if "dose_or_threshold" in concepts or _has_any(combined, ("dose", "threshold", "intake", "consumption", "exposure")):
        return "dose_boundary"
    if "alternative_or_comparator" in concepts or "substitution_or_comparator" in concepts or _has_any(combined, ("replace", "substitut", "comparator", "versus")):
        return "comparator_dependency"
    if _has_any(combined, ("adjust", "confound", "causal", "attribut")):
        return "causal_attribution"
    return "scope_boundary"


def _claim_pattern(claim: dict[str, Any]) -> str:
    concepts = set(_strings(claim.get("decision_concepts")))
    text = _claim_bundle(claim)
    if "surrogate_or_biomarker_endpoint" in concepts:
        return "biomarker_vs_hard_outcome"
    if "subgroup_diabetes_or_metabolic_risk" in concepts or _has_any(text, ("subgroup", "diabetes", "high-risk", "high risk")):
        return "subgroup_exception"
    if "dose_or_threshold" in concepts or _has_any(text, ("dose", "threshold", "intake", "consumption", "exposure")):
        return "dose_boundary"
    if "alternative_or_comparator" in concepts or "substitution_or_comparator" in concepts or _has_any(text, ("replace", "substitut", "comparator")):
        return "comparator_dependency"
    if _has_any(text, ("adjust", "confound", "causal", "attribut")):
        return "causal_attribution"
    return "scope_boundary"


def _text_pattern(text: str) -> str:
    lowered = text.lower()
    if _has_any(lowered, ("biomarker", "surrogate", "proxy")):
        return "biomarker_vs_hard_outcome"
    if _has_any(lowered, ("subgroup", "exception", "high-risk", "high risk")):
        return "subgroup_exception"
    if _has_any(lowered, ("dose", "threshold", "intake", "consumption", "exposure")):
        return "dose_boundary"
    if _has_any(lowered, ("replace", "substitut", "comparator", "alternative")):
        return "comparator_dependency"
    if _has_any(lowered, ("adjust", "confound", "causal", "attribut")):
        return "causal_attribution"
    return "scope_boundary"


def _uncertainty_for_pattern(pattern: str, left_claim: str, right_claim: str) -> str:
    if pattern == "biomarker_vs_hard_outcome":
        return "Whether biomarker evidence should constrain the recommendation when direct outcome evidence points differently"
    if pattern == "subgroup_exception":
        return "Whether the subgroup or risk exception is strong enough to narrow the default recommendation"
    if pattern == "dose_boundary":
        return "Whether the mapped dose boundary separates acceptable use from meaningfully higher risk"
    if pattern == "comparator_dependency":
        return "Whether the recommendation depends on what the option replaces or is compared against"
    if pattern == "causal_attribution":
        return "Whether the observed association is caused by the exposure rather than confounding or concurrent changes"
    return "Whether the mapped scope boundary transfers to the target decision"


def _uncertainty_from_claim(pattern: str, claim: str) -> str:
    if pattern == "biomarker_vs_hard_outcome":
        return "Whether proxy or biomarker evidence should change advice when hard outcomes are less concerning"
    if pattern == "subgroup_exception":
        return "Whether the exception applies strongly enough to split the recommendation by subgroup"
    if pattern == "dose_boundary":
        return "Whether risk changes materially beyond the mapped dose or intensity boundary"
    if pattern == "comparator_dependency":
        return "Whether the practical recommendation changes when the comparator changes"
    if pattern == "causal_attribution":
        return "Whether confounding explains the observed association enough to change the recommendation"
    return "Whether the mapped scope limit should change the target recommendation"


def _current_read_for_pattern(pattern: str, left_claim: str, right_claim: str, rationale: str) -> str:
    if pattern == "biomarker_vs_hard_outcome":
        return f"The map separates proxy or biomarker concern from direct outcome evidence: {_join_claim_sides(left_claim, right_claim)}"
    if pattern == "subgroup_exception":
        return f"The default read is conditional because a subgroup or risk exception remains visible: {_prefer_risk_claim(left_claim, right_claim)}"
    if pattern == "dose_boundary":
        return f"The current read is scoped to the mapped dose or intensity rather than all possible exposure levels: {_prefer_shorter(left_claim, right_claim)}"
    if pattern == "comparator_dependency":
        return f"The practical read can change with the comparator or substitution: {_prefer_shorter(left_claim, right_claim)}"
    if pattern == "causal_attribution":
        return f"The current read depends on whether adjustment and attribution are adequate: {_prefer_shorter(left_claim, right_claim)}"
    return _clean_claim(rationale) or f"The map treats the scope boundary as material: {_prefer_shorter(left_claim, right_claim)}"


def _decision_effect_for_pattern(pattern: str) -> str:
    return {
        "biomarker_vs_hard_outcome": "This determines whether mechanistic caution should override, merely bound, or leave unchanged the practical recommendation.",
        "subgroup_exception": "This determines whether the default recommendation applies broadly or must be split by subgroup or risk profile.",
        "dose_boundary": "This determines the intensity at which the recommendation stops being acceptable.",
        "comparator_dependency": "This determines whether the option is acceptable only relative to a worse alternative.",
        "causal_attribution": "This determines whether the association should drive advice or be treated as confounded.",
        "scope_boundary": "This determines whether the mapped evidence transfers to the target decision.",
    }.get(pattern, "This determines whether the evidence changes the recommendation.")


def _would_change_for_pattern(pattern: str) -> str:
    return {
        "biomarker_vs_hard_outcome": "The recommendation would change if direct outcome evidence showed that the biomarker change reliably produces clinically important harm in the target population.",
        "subgroup_exception": "The recommendation would change if direct evidence showed the subgroup risk is immaterial, appears at ordinary exposure levels, or applies to the default population.",
        "dose_boundary": "The recommendation would change if higher-quality evidence moved the risk threshold below or above the mapped dose boundary.",
        "comparator_dependency": "The recommendation would change if the option no longer looked acceptable against the relevant real-world comparator.",
        "causal_attribution": "The recommendation would change if better evidence separated the exposure effect from confounding, substitution, or concurrent lifestyle changes.",
        "scope_boundary": "The recommendation would change if direct evidence showed the mapped scope boundary fails inside the target case or safely extends beyond it.",
    }.get(pattern, "The recommendation would change if stronger evidence showed this uncertainty is immaterial or more broadly applicable.")


def _ids_for_direction(left: dict[str, Any], right: dict[str, Any], *, support: bool) -> list[str]:
    row = left if support else right
    claim_id = str(row.get("claim_id", "")).strip()
    return [claim_id] if claim_id else []


def _valid_crux(row: dict[str, Any]) -> bool:
    if len(str(row.get("crux", "")).split()) < 5:
        return False
    would = str(row.get("would_change_if", "")).strip().lower()
    if would in {"", "if"}:
        return False
    return "recommendation would change if" in would or "would change if" in would


def _dedupe_cruxes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    distinct: list[dict[str, Any]] = []
    backfill: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    seen_keys: set[str] = set()
    for row in rows:
        key = _norm(str(row.get("crux", "")))
        crux_type = str(row.get("crux_type", ""))
        if key in seen_keys:
            continue
        target = backfill if crux_type and crux_type in seen_types else distinct
        target.append(row)
        seen_keys.add(key)
        if crux_type:
            seen_types.add(crux_type)
    return [*distinct, *backfill]


def _clean_claim(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"\s*\.\.\.$", "", cleaned).strip()
    if len(cleaned) <= 260:
        return cleaned.rstrip(".")
    words = cleaned.split()
    out: list[str] = []
    for word in words:
        candidate = " ".join([*out, word])
        if out and len(candidate) > 260:
            break
        out.append(word)
    return " ".join(out).rstrip(" ,.;")


def _claim_bundle(claim: dict[str, Any]) -> str:
    return " ".join(str(claim.get(key, "") or "") for key in ("claim", "role", "evidence_family", "section")).lower()


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _prefer_risk_claim(left: str, right: str) -> str:
    for claim in (left, right):
        if _has_any(claim, ("risk", "harm", "adverse", "higher", "exception", "subgroup")):
            return claim
    return _prefer_shorter(left, right)


def _prefer_shorter(left: str, right: str) -> str:
    candidates = [item for item in (left, right) if item]
    return min(candidates, key=len) if candidates else ""


def _join_claim_sides(left: str, right: str) -> str:
    candidates = [item for item in (left, right) if item]
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]
    return f"{candidates[0]}; contrasted with {candidates[1]}"


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))
