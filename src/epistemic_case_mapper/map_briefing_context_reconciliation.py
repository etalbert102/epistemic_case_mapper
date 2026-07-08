from __future__ import annotations

import re
from collections import Counter, defaultdict
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


def build_slot_reconciliation_report(
    canonical_decision_spine: dict[str, Any],
    slot_eligibility_audit: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    """Reconcile canonical-spine fields with slot-audit card dispositions.

    The canonical spine may preserve weak or contextual evidence even when the
    stricter slot audit marks a required reader slot as missing. This report
    makes that distinction explicit so later synthesis can use such cards as
    boundary/context, not as clean load-bearing evidence.
    """

    cards_by_id = _cards_by_id(scaffold)
    audit_by_slot = _audit_by_slot(slot_eligibility_audit)
    rows: list[dict[str, Any]] = []
    for field in _spine_fields(canonical_decision_spine):
        rows.extend(_field_reconciliation_rows(field, cards_by_id, audit_by_slot))
    rows.extend(_missing_slot_rows(canonical_decision_spine, audit_by_slot))
    rows = _dedupe_rows(rows)
    issues = _slot_reconciliation_issues(rows)
    return {
        "schema_id": "slot_reconciliation_report_v1",
        "method": "canonical_spine_fields_reconciled_with_slot_audit_dispositions",
        "status": "warning" if issues else "ready",
        "row_count": len(rows),
        "disposition_counts": dict(Counter(str(row.get("slot_status", "unknown")) for row in rows)),
        "rows": rows,
        "issues": issues,
    }


def build_section_context_decision_packets(
    section_projection_packets: dict[str, Any],
    slot_reconciliation_report: dict[str, Any],
    scaffold: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scaffold = scaffold or {}
    reconciliation = _reconciliation_index(slot_reconciliation_report)
    sections: list[dict[str, Any]] = []
    for section in section_projection_packets.get("sections", []) if isinstance(section_projection_packets.get("sections"), list) else []:
        if not isinstance(section, dict):
            continue
        title = str(section.get("section", "")).strip()
        owned = [
            _enrich_section_card(title, row, reconciliation, ownership="owned")
            for row in section.get("owned_evidence", [])
            if isinstance(row, dict)
        ]
        references = [
            _enrich_section_card(title, row, reconciliation, ownership="reference_only")
            for row in section.get("reference_only_evidence", [])
            if isinstance(row, dict)
        ]
        owned = [row for row in owned if row.get("claim")]
        references = [row for row in references if row.get("claim")]
        enriched = {
            "section": title,
            "schema_id": "section_context_decision_packet_v1",
            "section_thesis": _decision_section_thesis(title, section, owned),
            "decision_move": section.get("decision_move"),
            "context_status": section.get("context_status"),
            "telemetry_context": section.get("telemetry_context", []),
            "owned_spine_field_ids": section.get("owned_spine_field_ids", []),
            "reference_spine_field_ids": section.get("reference_spine_field_ids", []),
            "owned_evidence": owned,
            "reference_only_evidence": references,
            "do_not_use_cards": _do_not_use_cards(title, reconciliation),
            "excluded_near_miss_cards": _excluded_near_misses(title, reconciliation),
            "missing_context": section.get("missing_context", []),
            "issues": _section_packet_issues(title, owned, references, section),
        }
        enriched["context_status"] = _packet_status(enriched)
        sections.append(_drop_empty(enriched))
    status = _overall_status(sections)
    return {
        "schema_id": "section_context_decision_packets_v1",
        "method": "section_projection_enriched_with_reconciled_slot_dispositions",
        "status": status,
        "sections": sections,
        "issues": [issue for section in sections for issue in section.get("issues", [])],
    }


def build_section_context_quality_report(section_context_decision_packets: dict[str, Any]) -> dict[str, Any]:
    sections = [
        section
        for section in section_context_decision_packets.get("sections", [])
        if isinstance(section, dict)
    ]
    rows: list[dict[str, Any]] = []
    repeated_uses: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for section in sections:
        title = str(section.get("section", "")).strip()
        owned = section.get("owned_evidence", []) if isinstance(section.get("owned_evidence"), list) else []
        missing_reason = [row for row in owned if not str(row.get("reason_for_inclusion", "")).strip()]
        missing_status = [row for row in owned if not str(row.get("slot_status", "")).strip()]
        missing_use = [row for row in owned if not str(row.get("section_use", "")).strip()]
        for row in owned:
            card_id = str(row.get("candidate_card_id", "")).strip()
            use = str(row.get("section_use", "")).strip()
            if card_id and use:
                repeated_uses[(card_id, use)].append(title)
        issues = []
        if missing_reason:
            issues.append("owned_evidence_missing_reason_for_inclusion")
        if missing_status:
            issues.append("owned_evidence_missing_slot_status")
        if missing_use:
            issues.append("owned_evidence_missing_section_use")
        if section.get("context_status") == "not_synthesis_ready":
            issues.append("section_not_synthesis_ready")
        rows.append(
            {
                "section": title,
                "status": "warning" if issues else "ready",
                "owned_evidence_count": len(owned),
                "missing_reason_count": len(missing_reason),
                "missing_slot_status_count": len(missing_status),
                "missing_section_use_count": len(missing_use),
                "issues": issues,
            }
        )
    cross_section_issues = [
        {
            "issue_type": "same_card_same_section_use_repeated",
            "candidate_card_id": card_id,
            "section_use": use,
            "sections": titles,
        }
        for (card_id, use), titles in sorted(repeated_uses.items())
        if len(set(titles)) > 1
    ]
    status = "warning" if cross_section_issues or any(row["issues"] for row in rows) else "ready"
    return {
        "schema_id": "section_context_quality_report_v1",
        "method": "deterministic_context_completeness_and_cross_section_overlap_checks",
        "status": status,
        "sections": rows,
        "cross_section_issues": cross_section_issues,
        "issues": [issue for row in rows for issue in row["issues"]] + [issue["issue_type"] for issue in cross_section_issues],
    }


def _field_reconciliation_rows(
    field: dict[str, Any],
    cards_by_id: dict[str, dict[str, Any]],
    audit_by_slot: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    field_id = str(field.get("field_id", "")).strip()
    slot_id = _slot_id_for_field(field)
    audit_slot = audit_by_slot.get(slot_id, {})
    card_ids = _string_list(field.get("candidate_card_ids"))
    if not card_ids:
        return [
            _drop_empty(
                {
                    "field_id": field_id,
                    "slot_id": slot_id,
                    "slot_label": audit_slot.get("label"),
                    "slot_status": _field_only_status(field, audit_slot),
                    "claim": field.get("claim"),
                    "source_ids": _string_list(field.get("source_ids")),
                    "claim_ids": _string_list(field.get("claim_ids")),
                    "reason": _field_only_reason(field, audit_slot),
                    "evidence_weight": _field_evidence_weight(field, None),
                    "model_judgment_needed": False,
                }
            )
        ]
    rows: list[dict[str, Any]] = []
    for card_id in card_ids:
        card = cards_by_id.get(card_id, {})
        accepted = _audit_card_ids(audit_slot, "accepted_candidate_cards")
        rejected = _audit_card_ids(audit_slot, "rejected_candidate_cards")
        rejected_row = _audit_card_row(audit_slot, "rejected_candidate_cards", card_id)
        status = _card_slot_status(field, card, audit_slot, accepted=accepted, rejected=rejected)
        rows.append(
            _drop_empty(
                {
                    "field_id": field_id,
                    "slot_id": slot_id,
                    "slot_label": audit_slot.get("label"),
                    "candidate_card_id": card_id,
                    "slot_status": status,
                    "claim": card.get("claim") or field.get("claim"),
                    "source_ids": _string_list(card.get("source_ids")) or _string_list(field.get("source_ids")),
                    "source_card_ids": _string_list(card.get("source_card_ids")),
                    "claim_ids": _string_list(card.get("claim_ids")) or _string_list(field.get("claim_ids")),
                    "quality": card.get("quality"),
                    "inclusion_recommendation": card.get("inclusion_recommendation"),
                    "rejection_reasons": _string_list(rejected_row.get("rejection_reasons")) if rejected_row else [],
                    "reason": _card_slot_reason(status, field, card, audit_slot, rejected_row),
                    "evidence_weight": _field_evidence_weight(field, card),
                    "model_judgment_needed": status in {"ambiguous", "mention_only"},
                }
            )
        )
    return rows


def _missing_slot_rows(canonical_decision_spine: dict[str, Any], audit_by_slot: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for field in canonical_decision_spine.get("missing_decision_slots", []) if isinstance(canonical_decision_spine.get("missing_decision_slots"), list) else []:
        if not isinstance(field, dict):
            continue
        slot_id = str(field.get("slot_id") or _slot_id_for_field(field)).strip()
        audit_slot = audit_by_slot.get(slot_id, {})
        rows.append(
            _drop_empty(
                {
                    "field_id": field.get("field_id"),
                    "slot_id": slot_id,
                    "slot_label": audit_slot.get("label"),
                    "slot_status": "missing",
                    "claim": field.get("claim"),
                    "reason": str(audit_slot.get("missing_message") or field.get("claim") or "Required slot is not established."),
                    "evidence_weight": "gap",
                    "model_judgment_needed": False,
                }
            )
        )
    return rows


def _enrich_section_card(
    title: str,
    row: dict[str, Any],
    reconciliation: dict[tuple[str, str], dict[str, Any]],
    *,
    ownership: str,
) -> dict[str, Any]:
    field_id = str(row.get("spine_field_id", "")).strip()
    card_id = str(row.get("candidate_card_id", "")).strip()
    rec = reconciliation.get((field_id, card_id)) or reconciliation.get((field_id, "")) or {}
    slot_status = str(rec.get("slot_status") or _fallback_slot_status(row)).strip()
    slot_id = str(rec.get("slot_id") or _slot_id_from_field_id(field_id) or row.get("intended_role") or "").strip()
    section_use = _section_use(title, slot_id, slot_status, row)
    how_to_use, how_not_to_use = _use_boundaries(title, slot_id, slot_status, row)
    enriched = {
        **row,
        "slot_id": slot_id,
        "slot_status": slot_status,
        "section_use": section_use,
        "reason_for_inclusion": row.get("reason_for_inclusion") or _reason_for_inclusion(title, slot_id, slot_status, row),
        "how_to_use": how_to_use,
        "how_not_to_use": how_not_to_use,
        "evidence_weight": rec.get("evidence_weight") or _evidence_weight(row),
        "eligibility_reason": rec.get("reason"),
        "allowed_sections": _allowed_sections(slot_id, slot_status),
        "forbidden_sections": _forbidden_sections(slot_id, slot_status),
        "validation_terms": _validation_terms(row),
        "context_ownership": ownership,
        "model_judgment_needed": bool(rec.get("model_judgment_needed")),
    }
    return _drop_empty(enriched)


def _section_packet_issues(title: str, owned: list[dict[str, Any]], references: list[dict[str, Any]], section: dict[str, Any]) -> list[str]:
    issues = [str(issue) for issue in section.get("issues", []) if str(issue).strip()] if isinstance(section.get("issues"), list) else []
    telemetry = section.get("telemetry_context", []) if isinstance(section.get("telemetry_context"), list) else []
    if not owned and not telemetry and "sources" not in title.lower() and "trail" not in title.lower():
        issues.append("no_owned_evidence_after_context_reconciliation")
    if any(not row.get("reason_for_inclusion") for row in owned):
        issues.append("owned_evidence_missing_reason_for_inclusion")
    if any(row.get("slot_status") == "missing" and row.get("candidate_card_id") for row in owned):
        issues.append("card_backed_evidence_marked_missing")
    return _dedupe(issues)


def _packet_status(packet: dict[str, Any]) -> str:
    issues = _string_list(packet.get("issues"))
    if "no_owned_evidence_after_context_reconciliation" in issues:
        return "not_synthesis_ready"
    if issues or packet.get("context_status") == "warning":
        return "warning"
    return str(packet.get("context_status") or "ready")


def _decision_section_thesis(title: str, section: dict[str, Any], owned: list[dict[str, Any]]) -> str:
    roles = _dedupe([_role_label(row) for row in owned if _role_label(row)])
    move = str(section.get("decision_move") or "").strip()
    if not roles:
        return str(section.get("section_thesis") or move or f"{title} should state the section's decision-relevant contribution.").strip()
    role_text = ", ".join(roles[:4])
    if title == "Decision Brief":
        return "Give the direct answer using the default answer and the highest-priority caveat."
    if move:
        return f"{move} Use the assigned evidence as {role_text}, not as a study-by-study summary."
    return f"{title} should use the assigned evidence as {role_text}, not as a study-by-study summary."


def _section_use(title: str, slot_id: str, slot_status: str, row: dict[str, Any]) -> str:
    key = title.lower()
    if slot_status == "missing":
        return "name_gap"
    if "decision brief" in key:
        return "top_answer_or_caveat"
    if "why this read" in key:
        return "reasoning_step"
    if "evidence carrying" in key:
        return "load_bearing_or_counterweight_evidence"
    if "practical read" in key:
        return "practical_implication_or_boundary"
    if "scope" in key or "exception" in key:
        return "scope_boundary_or_exception"
    if "crux" in key:
        return "decision_changing_condition"
    if "limit" in key:
        return "evidence_gap_or_limit"
    if slot_id:
        return slot_id
    return str(row.get("use") or "section_context")


def _reason_for_inclusion(title: str, slot_id: str, slot_status: str, row: dict[str, Any]) -> str:
    role = _role_label(row) or slot_id.replace("_", " ") or "evidence"
    claim = _short_text(str(row.get("claim", "")), 120)
    if slot_status == "mention_only":
        return f"This card belongs in {title} as contextual {role}; it can bound the analysis but should not carry the main conclusion."
    if slot_status == "missing":
        return f"This row belongs in {title} to name a decision-relevant gap, not to fill it."
    if slot_status == "boundary":
        return f"This card belongs in {title} because it bounds where the answer applies."
    if slot_status == "counterweight":
        return f"This card belongs in {title} because it weakens or qualifies the default read."
    if claim:
        return f"This card belongs in {title} as {role}: {claim}"
    return f"This card belongs in {title} as {role}."


def _use_boundaries(title: str, slot_id: str, slot_status: str, row: dict[str, Any]) -> tuple[str, str]:
    role = _role_label(row) or slot_id.replace("_", " ") or "evidence"
    if slot_status == "mention_only":
        return (
            f"Use it to frame a caveat or contextual boundary for {title}.",
            "Do not present it as clean, load-bearing evidence for the default answer.",
        )
    if slot_status == "missing":
        return (
            "Use it to state what the source set does not establish.",
            "Do not infer the missing fact from adjacent evidence.",
        )
    if slot_status == "boundary":
        return (
            f"Use it to limit or scope the section's conclusion.",
            "Do not let this boundary replace the main support/counterweight balance.",
        )
    if slot_status == "counterweight":
        return (
            f"Use it to qualify the answer or describe a risk/tension.",
            "Do not overstate it beyond the source's population, comparator, or endpoint.",
        )
    return (
        f"Use it as {role} for this section's assigned analytic job.",
        "Do not repeat it as a generic source summary without explaining its section-specific implication.",
    )


def _allowed_sections(slot_id: str, slot_status: str) -> list[str]:
    if slot_status == "missing":
        return ["Decision Cruxes", "Limits of the Current Map"]
    if slot_id in {"comparator_substitution", "alternatives_or_comparators", "comparator_or_substitution"}:
        return ["Practical Read", "Practical Scope and Exceptions", "Limits of the Current Map"]
    if slot_id in {"high_risk_subgroup", "default_population_boundary", "scope_conditions"}:
        return ["Practical Scope and Exceptions", "Decision Cruxes", "Limits of the Current Map"]
    if slot_id in {"main_support", "hard_outcome_support", "strongest_support", "default_answer"}:
        return ["Decision Brief", "Why This Read", "Evidence Carrying the Conclusion"]
    if slot_id in {"counterevidence_or_tension", "hard_outcome_counter", "safety_or_risk", "strongest_counterevidence"}:
        return ["Decision Brief", "Why This Read", "Evidence Carrying the Conclusion", "Decision Cruxes"]
    return SECTION_ORDER


def _forbidden_sections(slot_id: str, slot_status: str) -> list[str]:
    allowed = set(_allowed_sections(slot_id, slot_status))
    if slot_status == "mention_only":
        return ["Decision Brief"]
    return [section for section in SECTION_ORDER if section not in allowed]


def _do_not_use_cards(title: str, reconciliation: dict[tuple[str, str], dict[str, Any]]) -> list[str]:
    blocked = []
    for (_, card_id), row in reconciliation.items():
        if not card_id or row.get("slot_status") not in {"excluded", "missing"}:
            continue
        allowed = set(_allowed_sections(str(row.get("slot_id", "")), str(row.get("slot_status", ""))))
        if title not in allowed:
            blocked.append(card_id)
    return _dedupe(blocked)[:12]


def _excluded_near_misses(title: str, reconciliation: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for (_, card_id), row in reconciliation.items():
        if not card_id or row.get("slot_status") not in {"mention_only", "excluded"}:
            continue
        if title in _allowed_sections(str(row.get("slot_id", "")), str(row.get("slot_status", ""))):
            continue
        rows.append(
            _drop_empty(
                {
                    "candidate_card_id": card_id,
                    "reason_excluded": row.get("reason") or "Not assigned to this section by slot reconciliation.",
                }
            )
        )
    return rows[:5]


def _slot_id_for_field(field: dict[str, Any]) -> str:
    if field.get("slot_id"):
        return str(field.get("slot_id"))
    return _slot_id_from_field_id(str(field.get("field_id", ""))) or _slot_id_from_role(str(field.get("role", "")))


def _slot_id_from_field_id(field_id: str) -> str:
    normalized = field_id.lower()
    for prefix, slot_id in (
        ("missing_", ""),
        ("strongest_support", "main_support"),
        ("strongest_counterevidence", "counterevidence_or_tension"),
        ("comparator_substitution", "comparator_substitution"),
        ("population_boundary", "scope_conditions"),
        ("dose_boundary", "dose_intensity_boundary"),
        ("mechanism_proxy", "mechanism_surrogate"),
        ("evidence_quality_limit", "evidence_type_limits"),
        ("exception_answer", "high_risk_subgroup"),
        ("default_answer", "default_answer"),
    ):
        if normalized.startswith(prefix):
            return normalized.removeprefix("missing_") if prefix == "missing_" else slot_id
    return ""


def _slot_id_from_role(role: str) -> str:
    role = role.lower()
    if "comparator" in role or "substitution" in role:
        return "comparator_substitution"
    if "counter" in role:
        return "counterevidence_or_tension"
    if "support" in role:
        return "main_support"
    if "dose" in role or "quantity" in role:
        return "dose_intensity_boundary"
    if "mechanism" in role or "proxy" in role:
        return "mechanism_surrogate"
    if "scope" in role or "population" in role:
        return "scope_conditions"
    if "missing" in role:
        return "missing_slot"
    return role.replace(" ", "_")


def _card_slot_status(
    field: dict[str, Any],
    card: dict[str, Any],
    audit_slot: dict[str, Any],
    *,
    accepted: set[str],
    rejected: set[str],
) -> str:
    card_id = str(card.get("candidate_card_id", "")).strip()
    role = str(field.get("role") or card.get("role") or "").lower()
    if card_id and card_id in rejected:
        return "mention_only"
    if card_id and accepted and card_id in accepted:
        return _status_for_role(role, clean=True)
    if audit_slot.get("status") == "missing" and _slot_id_for_field(field) == str(audit_slot.get("slot_id")):
        return "mention_only"
    if card.get("inclusion_recommendation") == "appendix_only" or card.get("off_question_risk"):
        return "mention_only"
    return _status_for_role(role, clean=False)


def _status_for_role(role: str, *, clean: bool) -> str:
    if "missing" in role:
        return "missing"
    if "counter" in role or "risk" in role:
        return "counterweight"
    if any(term in role for term in ("scope", "boundary", "dose", "mechanism", "proxy", "comparator", "substitution", "exception")):
        return "boundary" if clean else "mention_only" if "comparator" in role or "substitution" in role else "boundary"
    return "load_bearing"


def _field_only_status(field: dict[str, Any], audit_slot: dict[str, Any]) -> str:
    if str(field.get("role")) == "missing_slot":
        return "missing"
    if audit_slot.get("status") == "missing":
        return "missing"
    return _status_for_role(str(field.get("role", "")), clean=True)


def _field_only_reason(field: dict[str, Any], audit_slot: dict[str, Any]) -> str:
    if str(field.get("role")) == "missing_slot" or audit_slot.get("status") == "missing":
        return str(audit_slot.get("missing_message") or field.get("claim") or "Required slot is not established.")
    return "Canonical spine field has no candidate card IDs but is retained as a structured decision field."


def _card_slot_reason(
    status: str,
    field: dict[str, Any],
    card: dict[str, Any],
    audit_slot: dict[str, Any],
    rejected_row: dict[str, Any] | None,
) -> str:
    if rejected_row:
        reasons = ", ".join(_string_list(rejected_row.get("rejection_reasons")))
        return f"Slot audit rejected this card for the clean slot; retain only as contextual evidence. Reasons: {reasons}."
    if status == "mention_only":
        return "Retained as contextual or boundary evidence because it is weak, indirect, appendix-only, or not cleanly fitted to the required slot."
    if audit_slot.get("status") == "filled":
        return "Accepted by the slot audit for this required decision slot."
    if field.get("role"):
        return f"Assigned through canonical spine role {field.get('role')}."
    return "Assigned through canonical spine."


def _field_evidence_weight(field: dict[str, Any], card: dict[str, Any] | None) -> str:
    if str(field.get("role")) == "missing_slot":
        return "gap"
    quality = str((card or {}).get("quality") or field.get("confidence") or "").lower()
    if quality in {"usable", "high", "medium"}:
        return "normal"
    if quality in {"weak", "indirect", "low"}:
        return "low"
    if (card or {}).get("inclusion_recommendation") == "appendix_only":
        return "low"
    return "unknown"


def _fallback_slot_status(row: dict[str, Any]) -> str:
    role = str(row.get("intended_role") or "").lower()
    return _status_for_role(role, clean=True)


def _evidence_weight(row: dict[str, Any]) -> str:
    quality = str(row.get("quality") or "").lower()
    if quality in {"usable", "high", "medium"}:
        return "normal"
    if quality in {"weak", "indirect", "low"}:
        return "low"
    return "unknown"


def _role_label(row: dict[str, Any]) -> str:
    role = str(row.get("intended_role") or row.get("slot_id") or "").strip()
    return role.replace("_", " ")


def _validation_terms(row: dict[str, Any]) -> list[str]:
    terms = []
    terms.extend(_string_list(row.get("quantity_values"))[:3])
    claim = str(row.get("claim") or row.get("source_excerpt") or "")
    for term in re.findall(r"[A-Za-z][A-Za-z0-9%/-]{3,}", claim):
        lowered = term.lower()
        if lowered in _STOPWORDS or lowered in {item.lower() for item in terms}:
            continue
        terms.append(term)
        if len(terms) >= 6:
            break
    return terms


def _audit_by_slot(slot_eligibility_audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(slot.get("slot_id", "")).strip(): slot
        for slot in slot_eligibility_audit.get("slots", [])
        if isinstance(slot, dict) and str(slot.get("slot_id", "")).strip()
    }


def _audit_card_ids(slot: dict[str, Any], key: str) -> set[str]:
    return {
        str(row.get("candidate_card_id", "")).strip()
        for row in slot.get(key, [])
        if isinstance(row, dict) and str(row.get("candidate_card_id", "")).strip()
    }


def _audit_card_row(slot: dict[str, Any], key: str, card_id: str) -> dict[str, Any] | None:
    for row in slot.get(key, []) if isinstance(slot.get(key), list) else []:
        if isinstance(row, dict) and str(row.get("candidate_card_id", "")).strip() == card_id:
            return row
    return None


def _reconciliation_index(report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in report.get("rows", []) if isinstance(report.get("rows"), list) else []:
        if not isinstance(row, dict):
            continue
        field_id = str(row.get("field_id", "")).strip()
        card_id = str(row.get("candidate_card_id", "")).strip()
        if field_id:
            index[(field_id, card_id)] = row
    return index


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
    ):
        fields.extend(row for row in spine.get(key, []) if isinstance(row, dict))
    return fields


def _cards_by_id(scaffold: dict[str, Any]) -> dict[str, dict[str, Any]]:
    report = scaffold.get("candidate_evidence_cards", {}) if isinstance(scaffold.get("candidate_evidence_cards"), dict) else {}
    cards = report.get("cards", []) if isinstance(report.get("cards"), list) else []
    return {str(card.get("candidate_card_id")): card for card in cards if isinstance(card, dict) and card.get("candidate_card_id")}


def _slot_reconciliation_issues(rows: list[dict[str, Any]]) -> list[str]:
    issues = []
    for row in rows:
        if row.get("slot_status") == "load_bearing" and row.get("rejection_reasons"):
            issues.append(f"{row.get('candidate_card_id')}: rejected card marked load-bearing")
        if row.get("slot_status") == "missing" and row.get("candidate_card_id"):
            issues.append(f"{row.get('candidate_card_id')}: card-backed evidence marked missing")
    return _dedupe(issues)


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for row in rows:
        key = (row.get("field_id"), row.get("candidate_card_id"), row.get("slot_status"), row.get("claim"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _overall_status(sections: list[dict[str, Any]]) -> str:
    statuses = {str(section.get("context_status")) for section in sections}
    if "not_synthesis_ready" in statuses:
        return "not_synthesis_ready"
    if "warning" in statuses:
        return "warning"
    return "ready"


def _short_text(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _dedupe(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


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


_STOPWORDS = {
    "that",
    "this",
    "with",
    "from",
    "were",
    "have",
    "been",
    "into",
    "than",
    "among",
    "because",
    "current",
    "evidence",
    "source",
    "section",
}
