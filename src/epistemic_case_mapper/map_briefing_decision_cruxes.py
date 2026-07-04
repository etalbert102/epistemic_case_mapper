from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from epistemic_case_mapper.config_profiles import DEFAULT_PROFILE_ID, infer_profile_id_from_text, profile_vocabulary
from epistemic_case_mapper.model_schemas import DecisionCrux


def build_decision_cruxes(
    *,
    scaffold: dict[str, Any],
    central_tensions: list[dict[str, str]],
    scope_boundaries: list[dict[str, str]],
    exceptions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    vocabulary = _profile_vocabulary_for_scaffold(scaffold)
    cruxes: list[dict[str, Any]] = []
    for tension in graph_packet.get("central_tensions", []) if isinstance(graph_packet.get("central_tensions"), list) else []:
        if isinstance(tension, dict):
            cruxes.append(_crux_from_graph_tension(tension, vocabulary=vocabulary))
    for claim in graph_packet.get("bridge_claims", []) if isinstance(graph_packet.get("bridge_claims"), list) else []:
        if isinstance(claim, dict):
            cruxes.append(_crux_from_bridge_claim(claim, vocabulary=vocabulary))
    for tension in central_tensions:
        cruxes.append(_crux_from_synthesis_tension(tension, vocabulary=vocabulary))
    for boundary in scope_boundaries:
        cruxes.append(_crux_from_boundary(boundary))
    for exception in exceptions:
        cruxes.append(_crux_from_exception(exception))
    known_claim_ids = _known_claim_ids(scaffold)
    known_relation_ids = _known_relation_ids(scaffold)
    return _validated_cruxes(
        _dedupe_cruxes([row for row in cruxes if _valid_crux(row)])[:5],
        known_claim_ids=known_claim_ids,
        known_relation_ids=known_relation_ids,
    )


def _crux_from_graph_tension(tension: dict[str, Any], *, vocabulary: dict[str, Any]) -> dict[str, Any]:
    left = tension.get("left", {}) if isinstance(tension.get("left"), dict) else {}
    right = tension.get("right", {}) if isinstance(tension.get("right"), dict) else {}
    pattern = _relation_pattern(left, right, tension, vocabulary=vocabulary)
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


def _crux_from_bridge_claim(claim: dict[str, Any], *, vocabulary: dict[str, Any]) -> dict[str, Any]:
    text = _clean_claim(str(claim.get("claim", "")))
    pattern = _claim_pattern(claim, vocabulary=vocabulary)
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


def _crux_from_synthesis_tension(tension: dict[str, str], *, vocabulary: dict[str, Any]) -> dict[str, Any]:
    label = _clean_claim(str(tension.get("tension", "")))
    pattern = _text_pattern(label + " " + str(tension.get("why_reasonable_people_disagree", "")), vocabulary=vocabulary)
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


def _relation_pattern(left: dict[str, Any], right: dict[str, Any], tension: dict[str, Any], *, vocabulary: dict[str, Any]) -> str:
    combined = " ".join((_claim_bundle(left), _claim_bundle(right), str(tension.get("rationale", "")), str(tension.get("why_it_matters", ""))))
    concepts = set(_strings(left.get("decision_concepts"))) | set(_strings(right.get("decision_concepts")))
    if "surrogate_or_biomarker_endpoint" in concepts and "hard_outcome_endpoint" in concepts:
        return "biomarker_vs_hard_outcome"
    if _has_subgroup_signal(concepts, combined, vocabulary=vocabulary):
        return "subgroup_exception"
    if "dose_or_threshold" in concepts or _has_any(combined, ("dose", "threshold", "intake", "consumption", "exposure")):
        return "dose_boundary"
    if "alternative_or_comparator" in concepts or "substitution_or_comparator" in concepts or _has_any(combined, ("replace", "substitut", "comparator", "versus")):
        return "comparator_dependency"
    if _has_any(combined, ("adjust", "confound", "causal", "attribut")):
        return "causal_attribution"
    return "scope_boundary"


def _claim_pattern(claim: dict[str, Any], *, vocabulary: dict[str, Any]) -> str:
    concepts = set(_strings(claim.get("decision_concepts")))
    text = _claim_bundle(claim)
    if "surrogate_or_biomarker_endpoint" in concepts:
        return "biomarker_vs_hard_outcome"
    if _has_subgroup_signal(concepts, text, vocabulary=vocabulary):
        return "subgroup_exception"
    if "dose_or_threshold" in concepts or _has_any(text, ("dose", "threshold", "intake", "consumption", "exposure")):
        return "dose_boundary"
    if "alternative_or_comparator" in concepts or "substitution_or_comparator" in concepts or _has_any(text, ("replace", "substitut", "comparator")):
        return "comparator_dependency"
    if _has_any(text, ("adjust", "confound", "causal", "attribut")):
        return "causal_attribution"
    return "scope_boundary"


def _text_pattern(text: str, *, vocabulary: dict[str, Any]) -> str:
    lowered = text.lower()
    if _has_any(lowered, ("biomarker", "surrogate", "proxy")):
        return "biomarker_vs_hard_outcome"
    if _has_subgroup_signal(set(), lowered, vocabulary=vocabulary) or _has_any(lowered, ("subgroup", "exception", "high-risk", "high risk")):
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


def _validated_cruxes(
    rows: list[dict[str, Any]],
    *,
    known_claim_ids: set[str],
    known_relation_ids: set[str],
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for row in rows:
        cleaned = dict(row)
        cleaned["supporting_claim_ids"] = _known_ids(cleaned.get("supporting_claim_ids"), known_claim_ids)
        cleaned["challenging_claim_ids"] = [
            claim_id
            for claim_id in _known_ids(cleaned.get("challenging_claim_ids"), known_claim_ids)
            if claim_id not in set(cleaned["supporting_claim_ids"])
        ]
        cleaned["relation_ids"] = _known_ids(cleaned.get("relation_ids"), known_relation_ids)
        try:
            validated.append(DecisionCrux.model_validate(cleaned).model_dump())
        except ValidationError:
            continue
    return validated


def _known_ids(value: Any, known: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        identifier = str(item).strip()
        if identifier and identifier in known and identifier not in ids:
            ids.append(identifier)
    return ids


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


def _has_subgroup_signal(concepts: set[str], text: str, *, vocabulary: dict[str, Any]) -> bool:
    if any(_concept_is_subgroup(concept) for concept in concepts):
        return True
    markers = _subgroup_markers(vocabulary)
    return _has_any(text, tuple(markers))


def _concept_is_subgroup(concept: str) -> bool:
    normalized = str(concept).lower()
    return any(marker in normalized for marker in ("subgroup", "high_risk", "higher_risk", "risk_group"))


def _subgroup_markers(vocabulary: dict[str, Any]) -> list[str]:
    markers = ["subgroup", "high-risk", "higher-risk", "high risk", "risk profile"]
    concept_markers = vocabulary.get("claim_concept_markers", {}) if isinstance(vocabulary.get("claim_concept_markers"), dict) else {}
    for concept, concept_values in concept_markers.items():
        if not _concept_is_subgroup(str(concept)) or not isinstance(concept_values, list):
            continue
        markers.extend(str(item).lower() for item in concept_values if str(item).strip())
    return _dedupe_strings(markers)


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


def _known_claim_ids(scaffold: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    for row in ledger.get("all_evidence", []) if isinstance(ledger.get("all_evidence"), list) else []:
        if isinstance(row, dict) and str(row.get("claim_id", "")).strip():
            ids.add(str(row["claim_id"]).strip())
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    for key in ("central_tensions", "load_bearing_claims"):
        for row in graph_packet.get(key, []) if isinstance(graph_packet.get(key), list) else []:
            _collect_claim_ids(row, ids)
    return ids


def _known_relation_ids(scaffold: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    for key in ("central_tensions",):
        for row in graph_packet.get(key, []) if isinstance(graph_packet.get(key), list) else []:
            if isinstance(row, dict) and str(row.get("relation_id", "")).strip():
                ids.add(str(row["relation_id"]).strip())
    return ids


def _collect_claim_ids(value: Any, ids: set[str]) -> None:
    if isinstance(value, dict):
        if str(value.get("claim_id", "")).strip():
            ids.add(str(value["claim_id"]).strip())
        for child in value.values():
            _collect_claim_ids(child, ids)
    elif isinstance(value, list):
        for child in value:
            _collect_claim_ids(child, ids)


def _profile_vocabulary_for_scaffold(scaffold: dict[str, Any]) -> dict[str, Any]:
    explicit = _profile_id_from_payload(scaffold.get("epistemic_config"))
    profile_id = infer_profile_id_from_text(_scaffold_profile_detection_text(scaffold), fallback_profile_id=explicit or DEFAULT_PROFILE_ID)
    return profile_vocabulary(profile_id)


def _profile_id_from_payload(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("profile_id", "")).strip()
    return ""


def _scaffold_profile_detection_text(scaffold: dict[str, Any]) -> str:
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    claims = " ".join(str(row.get("claim", "")) for row in ledger.get("all_evidence", []) if isinstance(row, dict))
    return " ".join((str(scaffold.get("question", "")), claims))


def _dedupe_strings(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        value = str(item).strip().lower()
        if value and value not in out:
            out.append(value)
    return out


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))
