from __future__ import annotations

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


def build_section_projection_packets(
    canonical_decision_spine: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    cards_by_id = _cards_by_id(scaffold)
    fields = _spine_fields(canonical_decision_spine)
    sections = [
        _projection_for_section(title, canonical_decision_spine, fields, cards_by_id)
        for title in SECTION_ORDER
    ]
    status = _overall_status(sections)
    return {
        "schema_id": "section_projection_packets_v1",
        "status": status,
        "sections": sections,
        "issues": [issue for section in sections for issue in section.get("issues", [])],
    }


def build_section_projection_readiness_report(section_projection_packets: dict[str, Any]) -> dict[str, Any]:
    sections = section_projection_packets.get("sections", []) if isinstance(section_projection_packets.get("sections"), list) else []
    rows = [
        {
            "section": section.get("section"),
            "context_status": section.get("context_status"),
            "owned_spine_field_count": len(section.get("owned_spine_field_ids", [])) if isinstance(section.get("owned_spine_field_ids"), list) else 0,
            "owned_evidence_count": len(section.get("owned_evidence", [])) if isinstance(section.get("owned_evidence"), list) else 0,
            "missing_context": section.get("missing_context", []),
            "issues": section.get("issues", []),
        }
        for section in sections
        if isinstance(section, dict)
    ]
    if any(row["context_status"] == "not_synthesis_ready" for row in rows):
        status = "not_synthesis_ready"
    elif any(row["context_status"] == "warning" for row in rows):
        status = "warning"
    else:
        status = "ready"
    return {
        "schema_id": "section_projection_readiness_report_v1",
        "status": status,
        "sections": rows,
        "issues": [issue for row in rows for issue in row.get("issues", [])],
    }


def _projection_for_section(
    title: str,
    spine: dict[str, Any],
    fields: list[dict[str, Any]],
    cards_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    owned_roles, reference_roles = _role_plan(title)
    owned_fields = _select_fields(title, fields, owned_roles)
    reference_fields = [field for field in _select_fields(title, fields, reference_roles) if field not in owned_fields]
    owned_evidence = _evidence_from_fields(owned_fields, cards_by_id, use="This section may explain this evidence fully.")
    reference_evidence = _evidence_from_fields(reference_fields, cards_by_id, use="Reference only; do not restate full detail.")
    missing_context = _missing_context(title, spine, owned_fields)
    status, issues = _context_status(title, owned_fields, owned_evidence, missing_context)
    return {
        "section": title,
        "section_thesis": _section_thesis(title, spine, owned_fields),
        "decision_move": _decision_move(title),
        "owned_spine_field_ids": [str(field.get("field_id")) for field in owned_fields if field.get("field_id")],
        "reference_spine_field_ids": [str(field.get("field_id")) for field in reference_fields if field.get("field_id")],
        "owned_evidence": owned_evidence[:7],
        "reference_only_evidence": reference_evidence[:4],
        "missing_context": missing_context,
        "context_status": status,
        "issues": issues,
    }


def _role_plan(title: str) -> tuple[set[str], set[str]]:
    key = title.lower()
    if "decision brief" in key:
        return {"default_answer"}, {"support", "counterweight", "evidence_quality_limit"}
    if "why this read" in key:
        return {"default_answer", "support", "counterweight"}, {"dose_or_intensity_boundary", "evidence_quality_limit"}
    if "evidence carrying" in key:
        return {"support", "counterweight", "mechanism_or_proxy"}, {"dose_or_intensity_boundary", "evidence_quality_limit"}
    if "practical read" in key:
        return {"default_answer", "dose_or_intensity_boundary", "population_boundary", "comparator_or_substitution"}, {"evidence_quality_limit"}
    if "scope" in key or "exception" in key:
        return {"exception", "population_boundary", "dose_or_intensity_boundary", "comparator_or_substitution"}, {"counterweight", "evidence_quality_limit"}
    if "crux" in key:
        return {"counterweight", "exception", "evidence_quality_limit", "missing_slot"}, {"support", "dose_or_intensity_boundary"}
    if "limit" in key:
        return {"evidence_quality_limit", "missing_slot", "population_boundary"}, {"counterweight", "support"}
    return {"support"}, {"counterweight"}


def _select_fields(title: str, fields: list[dict[str, Any]], roles: set[str]) -> list[dict[str, Any]]:
    selected = [field for field in fields if str(field.get("role", "")) in roles]
    if "decision brief" in title.lower():
        default = [field for field in fields if field.get("field_id") == "default_answer"]
        return (default + [field for field in selected if field not in default])[:4]
    return selected[:8]


def _spine_fields(spine: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    default = spine.get("default_answer")
    if isinstance(default, dict):
        fields.append(default)
    for key in (
        "exception_answers",
        "dose_or_intensity_boundaries",
        "population_boundaries",
        "strongest_support",
        "strongest_counterevidence",
        "mechanism_or_proxy_evidence",
        "comparator_or_substitution",
        "evidence_quality_limits",
        "missing_decision_slots",
    ):
        fields.extend(row for row in spine.get(key, []) if isinstance(row, dict))
    return fields


def _evidence_from_fields(
    fields: list[dict[str, Any]],
    cards_by_id: dict[str, dict[str, Any]],
    *,
    use: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in fields:
        card_ids = _string_list(field.get("candidate_card_ids"))
        if not card_ids:
            rows.append(_field_only_evidence(field, use=use))
            continue
        for card_id in card_ids:
            card = cards_by_id.get(card_id)
            if not card or card_id in seen:
                continue
            seen.add(card_id)
            rows.append(_card_evidence(card, field, use=use))
    return [row for row in rows if row.get("claim")]


def _card_evidence(card: dict[str, Any], field: dict[str, Any], *, use: str) -> dict[str, Any]:
    return _drop_empty(
        {
            "candidate_card_id": card.get("candidate_card_id"),
            "spine_field_id": field.get("field_id"),
            "source_card_ids": _string_list(card.get("source_card_ids"))[:4],
            "claim_ids": _string_list(card.get("claim_ids"))[:4],
            "source_ids": _string_list(card.get("source_ids"))[:4],
            "source": ", ".join(_string_list(card.get("source_titles")) or _string_list(card.get("source_ids"))),
            "claim": card.get("claim"),
            "source_excerpt": card.get("source_excerpt"),
            "intended_role": field.get("role") or card.get("role"),
            "quality": card.get("quality"),
            "quantity_values": _string_list(card.get("quantity_values"))[:4],
            "limitations": _string_list(card.get("limitations"))[:4],
            "use": use,
        }
    )


def _field_only_evidence(field: dict[str, Any], *, use: str) -> dict[str, Any]:
    return _drop_empty(
        {
            "spine_field_id": field.get("field_id"),
            "source_ids": _string_list(field.get("source_ids")),
            "claim_ids": _string_list(field.get("claim_ids")),
            "claim": field.get("claim"),
            "intended_role": field.get("role"),
            "quantity_values": _string_list(field.get("quantity_ids"))[:4],
            "limitations": _string_list(field.get("limits"))[:4],
            "use": use,
        }
    )


def _missing_context(title: str, spine: dict[str, Any], owned_fields: list[dict[str, Any]]) -> list[str]:
    missing = [str(field.get("claim")) for field in spine.get("missing_decision_slots", []) if isinstance(field, dict)]
    if "limit" in title.lower() or "crux" in title.lower():
        return missing[:5]
    if not owned_fields:
        return ["No canonical spine fields are assigned to this section."]
    return []


def _context_status(
    title: str,
    owned_fields: list[dict[str, Any]],
    owned_evidence: list[dict[str, Any]],
    missing_context: list[str],
) -> tuple[str, list[str]]:
    issues = []
    if not owned_fields:
        issues.append("no_owned_spine_fields")
        return "not_synthesis_ready", issues
    if "decision brief" not in title.lower() and not owned_evidence:
        issues.append("owned_spine_fields_have_no_projected_evidence")
        return "warning", issues
    if missing_context and "limit" not in title.lower() and "crux" not in title.lower():
        issues.append("section_has_relevant_missing_context")
        return "warning", issues
    return "ready", issues


def _section_thesis(title: str, spine: dict[str, Any], owned_fields: list[dict[str, Any]]) -> str:
    if title == "Decision Brief":
        return str(_dict(spine.get("default_answer")).get("claim") or "State the answer and confidence.")
    if owned_fields:
        lead = str(owned_fields[0].get("claim", "")).strip()
        return lead if len(lead) <= 220 else lead[:219].rstrip() + "..."
    return f"{title} should state what the canonical decision spine can and cannot support."


def _decision_move(title: str) -> str:
    moves = {
        "Decision Brief": "Give the answer, confidence, and most important caveat.",
        "Why This Read": "Explain the reasoning path from support and counterevidence to the answer.",
        "Evidence Carrying the Conclusion": "Identify which evidence actually carries the answer and what weakens it.",
        "Practical Read": "Translate the answer into practical decision implications.",
        "Practical Scope and Exceptions": "Bound where the answer applies and where it should not be used.",
        "Decision Cruxes": "Name what would change the answer.",
        "Limits of the Current Map": "State the evidence gaps and source limitations without implying they were resolved.",
    }
    return moves.get(title, "Synthesize assigned canonical spine fields.")


def _cards_by_id(scaffold: dict[str, Any]) -> dict[str, dict[str, Any]]:
    report = scaffold.get("candidate_evidence_cards", {}) if isinstance(scaffold.get("candidate_evidence_cards"), dict) else {}
    cards = report.get("cards", []) if isinstance(report.get("cards"), list) else []
    return {str(card.get("candidate_card_id")): card for card in cards if isinstance(card, dict) and card.get("candidate_card_id")}


def _overall_status(sections: list[dict[str, Any]]) -> str:
    statuses = {str(section.get("context_status")) for section in sections}
    if "not_synthesis_ready" in statuses:
        return "not_synthesis_ready"
    if "warning" in statuses:
        return "warning"
    return "ready"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}
