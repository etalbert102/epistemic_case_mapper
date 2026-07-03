from __future__ import annotations

import re
from typing import Any


def build_decision_synthesis_model(scaffold: dict[str, Any]) -> dict[str, Any]:
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)]
    evidence_lines = _graph_evidence_lines(graph_packet) + _evidence_lines(rows)
    evidence_lines = _dedupe_dicts(evidence_lines)[:9]
    central_tensions = _graph_central_tensions(graph_packet) or _central_tensions(decision_model, evidence_lines, rows)
    scope_boundaries = _scope_boundaries(decision_model)
    exceptions = _exceptions(decision_model, evidence_lines)
    recommendations = _recommendations(decision_model, scaffold, scope_boundaries, exceptions)
    cruxes = _synthesis_cruxes(decision_model, central_tensions, scope_boundaries, exceptions)
    return {
        "schema_id": "decision_synthesis_model_v1",
        "method": "generic_decision_support_slots_from_weighted_evidence",
        "question": str(scaffold.get("question", "")).strip(),
        "bottom_line": _bottom_line(decision_model),
        "graph_summary": graph_packet.get("graph_summary", {}),
        "evidence_lines": evidence_lines,
        "central_tensions": central_tensions,
        "scope_boundaries": scope_boundaries,
        "exceptions": exceptions,
        "recommendations": recommendations,
        "cruxes": cruxes,
        "quantitative_anchors": _quantitative_anchors(rows),
        "limits": _limits(scaffold),
    }


def _graph_evidence_lines(graph_packet: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for cluster in graph_packet.get("issue_clusters", []) if isinstance(graph_packet.get("issue_clusters"), list) else []:
        if not isinstance(cluster, dict):
            continue
        representatives = [item for item in cluster.get("representative_claims", []) if isinstance(item, dict)]
        if not representatives:
            continue
        label = str(cluster.get("label", "Issue cluster"))
        lines.append(
            {
                "role": "graph_issue_cluster",
                "label": label,
                "current_read": _graph_cluster_read(label, representatives),
                "support_direction": "graph_structures_synthesis",
                "source_claims": [_graph_source_claim(row) for row in representatives[:3]],
            }
        )
    return lines[:4]


def _graph_cluster_read(label: str, representatives: list[dict[str, Any]]) -> str:
    first = representatives[0]
    claim = _sentence(str(first.get("claim", "")))
    source = str(first.get("source", "")).strip()
    return f"{label}: {claim}" + (f" ({source})." if source and source not in claim else ".")


def _graph_source_claim(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": row.get("claim_id"),
        "claim": _sentence(str(row.get("claim", ""))),
        "source": row.get("source", ""),
        "weight": row.get("weight", "medium"),
        "evidence_family": row.get("evidence_family", "general_evidence"),
    }


def _graph_central_tensions(graph_packet: dict[str, Any]) -> list[dict[str, str]]:
    tensions: list[dict[str, str]] = []
    for item in graph_packet.get("central_tensions", []) if isinstance(graph_packet.get("central_tensions"), list) else []:
        if not isinstance(item, dict):
            continue
        left = item.get("left", {}) if isinstance(item.get("left"), dict) else {}
        right = item.get("right", {}) if isinstance(item.get("right"), dict) else {}
        left_claim = _sentence(str(left.get("claim", "")))
        right_claim = _sentence(str(right.get("claim", "")))
        if not left_claim or not right_claim:
            continue
        tensions.append(
            {
                "tension": _tension_label(left_claim, right_claim),
                "why_reasonable_people_disagree": _graph_tension_why(item, left_claim, right_claim),
                "current_resolution": _graph_tension_resolution(item),
                "would_change_if": str(item.get("failure_condition") or "Stronger evidence showed one side does not apply to the decision-relevant population, comparator, endpoint, or scope.").strip(),
            }
        )
    return _dedupe_dicts(tensions)[:4]


def _tension_label(left_claim: str, right_claim: str) -> str:
    return f"{_short_phrase(left_claim)} versus {_short_phrase(right_claim)}"


def _graph_tension_why(item: dict[str, Any], left_claim: str, right_claim: str) -> str:
    why = str(item.get("why_it_matters", "")).strip()
    if why and not _artifact_language(why):
        return why
    relation_type = str(item.get("relation_type", "in_tension_with")).replace("_", " ")
    return f"The graph marks a {relation_type} edge between two decision-relevant claims: {left_claim}; {right_claim}."


def _graph_tension_resolution(item: dict[str, Any]) -> str:
    rationale = str(item.get("rationale", "")).strip()
    if rationale and not _artifact_language(rationale):
        return rationale
    return "Keep both claims visible and treat the bottom line as conditional until the tension is resolved."


def _short_phrase(text: str) -> str:
    words = text.split()
    return " ".join(words[:11]).rstrip(" ,.;") + ("..." if len(words) > 11 else "")


def _bottom_line(decision_model: dict[str, Any]) -> dict[str, str]:
    default = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    return {
        "classification": str(default.get("classification", "mixed_or_context_dependent")),
        "current_read": str(default.get("plain_language_instruction") or default.get("why_this_frame") or "").strip(),
        "confidence": str(default.get("confidence_cap", "medium")),
        "why_this_frame": str(default.get("why_this_frame", "")).strip(),
    }


def _evidence_lines(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in sorted((row for row in rows if _usable_evidence_row(row)), key=_row_rank):
        role = _evidence_line_role(row)
        grouped.setdefault(role, []).append(row)
    lines: list[dict[str, Any]] = []
    for role in _role_order(grouped):
        role_rows = grouped[role][:4]
        if not role_rows:
            continue
        lines.append(
            {
                "role": role,
                "label": _role_label(role),
                "current_read": _line_current_read(role, role_rows),
                "support_direction": _support_direction(role_rows),
                "source_claims": [_source_claim(row) for row in role_rows[:3]],
            }
        )
    return lines[:9]


def _evidence_line_role(row: dict[str, Any]) -> str:
    concepts = _string_set(row.get("decision_concepts"))
    slots = _string_set(row.get("decision_slots"))
    evidence_slots = _string_set(row.get("evidence_slots"))
    family = str(row.get("evidence_family", "general_evidence"))
    section = str(row.get("section", ""))
    if section == "conflicting_evidence":
        return "counterevidence_or_risk"
    if "substitution_or_comparator" in slots or "alternative_or_comparator" in concepts or "comparator" in evidence_slots:
        return "comparator_or_substitution"
    if family == "guideline_or_recommendation" or "practical_recommendation" in slots:
        return "guidance_or_practical_advice"
    if "mechanism" in slots or family == "mechanism_or_biomarker":
        return "mechanism_or_proxy"
    if "surrogate_or_biomarker_endpoint" in concepts:
        return "mechanism_or_proxy"
    if "hard_outcome_endpoint" in concepts or "outcome_or_endpoint" in evidence_slots:
        return "direct_outcome"
    if "high_risk_subgroup" in slots or "subgroup_diabetes_or_metabolic_risk" in concepts or "population_scope" in evidence_slots:
        return "subgroup_or_scope"
    if "implementation_constraint" in slots or "technical_or_capacity" in slots or "implementation_condition" in evidence_slots:
        return "implementation_or_feasibility"
    if "safety_or_risk" in slots or "safety_or_adverse_effect" in concepts:
        return "counterevidence_or_risk"
    if section == "method_limits" or family == "method_or_validity":
        return "method_or_validity_limit"
    return "general_evidence"


def _role_order(grouped: dict[str, list[dict[str, Any]]]) -> list[str]:
    preferred = [
        "direct_outcome",
        "counterevidence_or_risk",
        "mechanism_or_proxy",
        "subgroup_or_scope",
        "comparator_or_substitution",
        "guidance_or_practical_advice",
        "implementation_or_feasibility",
        "method_or_validity_limit",
        "general_evidence",
    ]
    return [role for role in preferred if role in grouped] + sorted(role for role in grouped if role not in preferred)


def _line_current_read(role: str, rows: list[dict[str, Any]]) -> str:
    first = rows[0]
    claim = _sentence(str(first.get("claim", "")))
    source = str(first.get("source", "")).strip()
    label = _role_label(role).lower()
    return f"{_role_opening(role, label)}: {claim}" + (f" ({source})." if source and source not in claim else ".")


def _role_opening(role: str, label: str) -> str:
    return {
        "direct_outcome": "Direct outcome evidence",
        "counterevidence_or_risk": "Counterevidence or downside risk",
        "mechanism_or_proxy": "Mechanism or proxy evidence",
        "subgroup_or_scope": "Scope or subgroup evidence",
        "comparator_or_substitution": "Comparator or substitution evidence",
        "guidance_or_practical_advice": "Guidance or practical advice",
        "implementation_or_feasibility": "Implementation or feasibility evidence",
        "method_or_validity_limit": "Method or validity limit",
    }.get(role, label.capitalize())


def _role_label(role: str) -> str:
    return role.replace("_", " ").replace(" or ", " / ").title()


def _support_direction(rows: list[dict[str, Any]]) -> str:
    sections = {str(row.get("section", "")) for row in rows}
    if "conflicting_evidence" in sections:
        return "pushes_against_or_limits_default"
    if "scope_limits" in sections or "method_limits" in sections:
        return "bounds_scope_or_confidence"
    return "supports_or_informs_default"


def _central_tensions(
    decision_model: dict[str, Any],
    evidence_lines: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    tensions: list[dict[str, str]] = []
    for item in decision_model.get("tension_resolutions", []) if isinstance(decision_model.get("tension_resolutions"), list) else []:
        if not isinstance(item, dict):
            continue
        tension = str(item.get("tension", "")).strip()
        if tension and not _artifact_language(tension) and not _artifact_language(str(item.get("resolution_hint", ""))):
            tensions.append(
                {
                    "tension": tension,
                    "why_reasonable_people_disagree": str(item.get("resolution_hint", "") or "The evidence lines point in different directions or apply under different conditions.").strip(),
                    "current_resolution": _human_resolution(item),
                    "would_change_if": "A stronger source showed one side generalizes across the relevant population, comparator, endpoint, and implementation setting.",
                }
            )
    if tensions:
        return _dedupe_dicts(tensions)[:4]
    support = _first_line(evidence_lines, ("direct_outcome", "guidance_or_practical_advice"))
    counter = _first_line(evidence_lines, ("counterevidence_or_risk", "mechanism_or_proxy", "method_or_validity_limit"))
    if support and counter:
        tensions.append(
            {
                "tension": f"{support['label']} versus {counter['label']}",
                "why_reasonable_people_disagree": "One evidence line supports the default read while another limits its scope, confidence, or practical generalization.",
                "current_resolution": "Treat the default read as conditional on the mapped population, dose or intensity, comparator, endpoint, and implementation context.",
                "would_change_if": "Direct, higher-weight evidence resolved the limiting line rather than merely coexisting with it.",
            }
        )
    elif rows:
        tensions.append(
            {
                "tension": "Whether the current source packet is complete enough for a stronger answer",
                "why_reasonable_people_disagree": "The map can show useful support while still missing decision-relevant families, slots, or source perspectives.",
                "current_resolution": "Use the packet for a scoped decision read, not as a complete literature review.",
                "would_change_if": "Missing evidence families and scope slots were filled by source-grounded claims.",
            }
        )
    return tensions[:3]


def _scope_boundaries(decision_model: dict[str, Any]) -> list[dict[str, str]]:
    slots = decision_model.get("decision_slots", {}) if isinstance(decision_model.get("decision_slots"), dict) else {}
    boundaries: list[dict[str, str]] = []
    for slot, boundary_type in (
        ("default_population", "population"),
        ("dose_or_intensity_threshold", "dose_or_intensity"),
        ("setting_or_context", "setting"),
        ("substitution_or_comparator", "comparator"),
        ("endpoint_type", "endpoint"),
        ("study_design", "study_design"),
        ("implementation_constraint", "implementation_condition"),
    ):
        for entry in slots.get(slot, [])[:2] if isinstance(slots.get(slot), list) else []:
            if not isinstance(entry, dict):
                continue
            value = _clean_slot_value(str(entry.get("value") or entry.get("claim") or ""))
            if not _usable_slot_value(value, boundary_type):
                continue
            boundaries.append(
                {
                    "boundary_type": boundary_type,
                    "current_read": value,
                    "source": str(entry.get("source", "")).strip(),
                }
            )
    return _dedupe_dicts(boundaries)[:8]


def _exceptions(decision_model: dict[str, Any], evidence_lines: list[dict[str, Any]]) -> list[dict[str, str]]:
    slots = decision_model.get("decision_slots", {}) if isinstance(decision_model.get("decision_slots"), dict) else {}
    exceptions: list[dict[str, str]] = []
    for slot, label in (("high_risk_subgroup", "high-risk subgroup"), ("safety_or_risk", "safety or downside risk")):
        for entry in slots.get(slot, [])[:3] if isinstance(slots.get(slot), list) else []:
            if not isinstance(entry, dict):
                continue
            value = _clean_slot_value(str(entry.get("value") or entry.get("claim") or ""))
            if _usable_slot_value(value, label):
                exceptions.append({"condition": label, "current_read": value, "source": str(entry.get("source", "")).strip()})
    for line in evidence_lines:
        if line.get("role") == "counterevidence_or_risk":
            exceptions.append({"condition": "counterevidence or risk", "current_read": str(line.get("current_read", "")), "source": ""})
    return _dedupe_dicts(exceptions)[:6]


def _recommendations(
    decision_model: dict[str, Any],
    scaffold: dict[str, Any],
    boundaries: list[dict[str, str]],
    exceptions: list[dict[str, str]],
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    for item in decision_model.get("practical_recommendations", []) if isinstance(decision_model.get("practical_recommendations"), list) else []:
        text = _clean_slot_value(str(item))
        if text and not _awkward_recommendation(text):
            recommendations.append({"condition": "default", "recommendation": _sentence(text), "confidence": _confidence(scaffold), "basis": "decision_model"})
    if boundaries:
        recommendations.append(
            {
                "condition": "scope-bound use",
                "recommendation": "Keep the recommendation attached to the mapped population, dose or intensity, comparator, endpoint, and implementation conditions.",
                "confidence": _confidence(scaffold),
                "basis": "scope_boundaries",
            }
        )
    if exceptions:
        recommendations.append(
            {
                "condition": "exception or caution case",
                "recommendation": "Treat named exceptions as separate decisions rather than automatically generalizing the default read.",
                "confidence": _confidence(scaffold),
                "basis": "exceptions",
            }
        )
    return _dedupe_dicts(recommendations)[:6]


def _synthesis_cruxes(
    decision_model: dict[str, Any],
    tensions: list[dict[str, str]],
    boundaries: list[dict[str, str]],
    exceptions: list[dict[str, str]],
) -> list[dict[str, str]]:
    cruxes: list[dict[str, str]] = []
    for tension in tensions[:2]:
        cruxes.append(
            {
                "crux": "Whether " + str(tension.get("tension", "")).strip().rstrip(".").lower(),
                "current_read": str(tension.get("current_resolution", "")).strip(),
                "would_change_if": str(tension.get("would_change_if", "")).strip(),
            }
        )
    for boundary in boundaries[:2]:
        label = str(boundary.get("boundary_type", "scope")).replace("_", " ")
        cruxes.append(
            {
                "crux": f"Whether the {label} boundary transfers to the target decision",
                "current_read": str(boundary.get("current_read", "")).strip(),
                "would_change_if": "Evidence showed the same read holds outside the mapped boundary or fails inside it.",
            }
        )
    for exception in exceptions[:1]:
        cruxes.append(
            {
                "crux": "Whether the named exception changes the default recommendation",
                "current_read": str(exception.get("current_read", "")).strip(),
                "would_change_if": "Better evidence showed the exception is immaterial or applies more broadly than currently mapped.",
            }
        )
    for item in decision_model.get("what_would_change_answer", []) if isinstance(decision_model.get("what_would_change_answer"), list) else []:
        text = str(item).strip()
        if text:
            cruxes.append({"crux": text, "current_read": "Not resolved by the current map.", "would_change_if": "The named uncertainty were resolved by stronger evidence."})
    return _dedupe_dicts([row for row in cruxes if row.get("crux")])[:5]


def _quantitative_anchors(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    anchors: list[dict[str, str]] = []
    for row in sorted((row for row in rows if _usable_evidence_row(row)), key=_row_rank):
        claim = str(row.get("claim", ""))
        anchor = _quantitative_anchor_sentence(claim)
        if not anchor:
            continue
        anchors.append(
            {
                "claim": anchor,
                "source": str(row.get("source", "")).strip(),
                "role": _evidence_line_role(row),
            }
        )
    return _dedupe_dicts(anchors)[:8]


def _limits(scaffold: dict[str, Any]) -> list[str]:
    items: list[str] = []
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    for slot in sufficiency.get("missing_expected_decision_slots", []) if isinstance(sufficiency.get("missing_expected_decision_slots"), list) else []:
        items.append(f"The current source packet does not establish a clean {str(slot).replace('_', ' ')}.")
    for family in sufficiency.get("missing_expected_evidence_families", []) if isinstance(sufficiency.get("missing_expected_evidence_families"), list) else []:
        items.append(f"The current source packet does not establish {str(family).replace('_', ' ')} evidence.")
    for issue in scaffold.get("quality_issues", []) if isinstance(scaffold.get("quality_issues"), list) else []:
        if str(issue).strip():
            items.append(str(issue).strip())
    return _dedupe_strings(items)[:6]


def _source_claim(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": row.get("claim_id"),
        "claim": _sentence(str(row.get("claim", ""))),
        "source": row.get("source", ""),
        "weight": row.get("weight", "medium"),
        "evidence_family": row.get("evidence_family", "general_evidence"),
    }


def _row_rank(row: dict[str, Any]) -> tuple[int, int, str]:
    quantitative = 1 if _has_quantitative_specificity(str(row.get("claim", ""))) else 0
    return (-int(row.get("score", 0)), -quantitative, str(row.get("claim_id", "")))


def _has_quantitative_specificity(text: str) -> bool:
    return bool(re.search(r"(?:\bHR\b|\bRR\b|\bCI\b|\bP\s*[<=>]|%|mg/dL|mmol/L|participants?|events?|n\s*=|≥|≤|<|>\s*)", text, flags=re.IGNORECASE))


def _usable_evidence_row(row: dict[str, Any]) -> bool:
    claim = str(row.get("claim", "")).strip()
    lowered = claim.lower()
    if len(claim) < 32:
        return False
    if any(
        marker in lowered
        for marker in (
            "[google scholar]",
            "copyright",
            "author information",
            "no. (%)",
            "pmcid:",
            "learn more:",
            " etable",
            " esupplement",
            "supplementary table",
        )
    ):
        return False
    if re.search(r"\b[A-Z]{2,}\s*=\s*[a-z]", claim):
        return False
    if re.fullmatch(r"[\w\s,./()%+-]+", claim) and len(_content_words(claim)) <= 3:
        return False
    return True


def _clean_slot_value(text: str) -> str:
    cleaned = _sentence(text)
    cleaned = re.sub(r"^\W+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else ""


def _usable_slot_value(value: str, slot: str) -> bool:
    lowered = value.lower().strip()
    if not value:
        return False
    if len(value) < 6:
        return False
    if _artifact_language(value):
        return False
    if any(marker in lowered for marker in ("no. (%)", "etable", "supplement", "pmcid:", "copyright", "google scholar")):
        return False
    if lowered in {"risk", "benefit", "effect", "outcome", "setting", "intervention", "comparator"}:
        return False
    if re.search(r"\b[A-Z]{2,}\s*=\s*[a-z]", value):
        return False
    first = re.match(r"[A-Za-z]+", value)
    if first and first.group(0).lower() in {"nerally", "respectively", "whereas", "including", "because"}:
        return False
    if lowered.endswith((" and", " or", " of", " the", " to")):
        return False
    words = _content_words(value)
    if len(words) < 2 and not re.search(r"\b\d+|\bhigh\b|\blow\b|\bpeople\b|\bpatients\b|\badults\b|\bchildren\b", lowered):
        return False
    if "subgroup" in slot or "population" in slot:
        return _looks_like_population_or_group(value) or len(words) <= 8
    return True


def _looks_like_population_or_group(value: str) -> bool:
    lowered = value.lower()
    return bool(
        re.search(
            r"\b(people|patients|participants|adults|children|workers|households|schools|sites|regions|users|firms|systems)\b",
            lowered,
        )
    )


def _awkward_recommendation(text: str) -> bool:
    lowered = text.lower()
    if "name this subgroup separately" not in lowered or ":" not in text:
        return False
    target = text.split(":", 1)[1].strip()
    if _looks_like_population_or_group(target):
        return False
    return len(_content_words(target)) > 6 or bool(re.search(r"\b(associated|increases?|decreases?|significant|showed|found)\b", target, flags=re.I))


def _quantitative_anchor_sentence(text: str) -> str:
    if not _has_quantitative_specificity(text):
        return ""
    candidates = re.split(r"(?<=[.!?])\s+", _sentence(text))
    for candidate in candidates:
        candidate = _sentence(candidate)
        if not _has_quantitative_specificity(candidate):
            continue
        lowered = candidate.lower()
        if any(marker in lowered for marker in ("etable", "supplement", "characteristics, according to", "shown in")):
            continue
        if re.search(r"\b[A-Z]{2,}\s*=\s*[a-z]", candidate):
            continue
        return candidate if len(candidate) <= 320 else candidate[:317].rstrip() + "..."
    compact = _sentence(text)
    return compact[:317].rstrip() + "..." if len(compact) > 320 else compact


def _human_resolution(item: dict[str, Any]) -> str:
    hint = str(item.get("resolution_hint", "")).strip()
    if hint and not _artifact_language(hint):
        return hint
    relation = str(item.get("relation_type", "")).replace("_", " ").strip()
    if relation:
        return f"Current evidence marks this as a {relation} rather than a settled conclusion."
    return "Read the answer as conditional rather than settled across all cases."


def _first_line(lines: list[dict[str, Any]], roles: tuple[str, ...]) -> dict[str, Any] | None:
    for role in roles:
        for line in lines:
            if line.get("role") == role:
                return line
    return None


def _confidence(scaffold: dict[str, Any]) -> str:
    return str(scaffold.get("confidence_cap", "medium"))


def _string_set(value: Any) -> set[str]:
    return {str(item) for item in value if str(item).strip()} if isinstance(value, list) else set()


def _sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().strip("- ")
    return cleaned.rstrip(".")


def _artifact_language(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "claim a",
            "claim b",
            "relation marks",
            "this challenges relation",
            "this in tension",
            "this relation",
            "default answer under stated conditions",
        )
    )


def _content_words(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-zA-Z]{4,}", text.lower()) if word not in {"with", "from", "that", "this"}]


def _dedupe_dicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = re.sub(r"\s+", " ", "|".join(str(value).lower() for value in row.values())).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.sub(r"\s+", " ", item.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
