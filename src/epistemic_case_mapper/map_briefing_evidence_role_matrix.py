from __future__ import annotations

from collections import defaultdict
from typing import Any


ROLE_ORDER = ("load_bearing", "contrast", "boundary", "contextual")


def build_evidence_role_matrix_bundle(
    *,
    candidate_evidence_cards: dict[str, Any],
    section_context_decision_packets: dict[str, Any],
) -> dict[str, Any]:
    """Build section-specific evidence uses without making ownership exclusive."""

    cards = _candidate_cards(candidate_evidence_cards)
    sections = _section_packets(section_context_decision_packets)
    matrix = build_evidence_role_matrix(cards, sections)
    working_sets = build_section_evidence_working_sets(matrix, sections)
    coverage = build_evidence_role_coverage_report(matrix, working_sets)
    return {
        "evidence_role_matrix": matrix,
        "section_evidence_working_sets": working_sets,
        "evidence_role_coverage_report": coverage,
    }


def build_evidence_role_matrix(cards: list[dict[str, Any]], sections: list[dict[str, Any]]) -> dict[str, Any]:
    card_lookup = {_card_id(card): card for card in cards if _card_id(card)}
    section_uses: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    do_not_use: dict[str, set[str]] = defaultdict(set)
    for section in sections:
        title = str(section.get("section", "")).strip()
        if not title:
            continue
        for row in _rows(section.get("owned_evidence")):
            card_id = _card_id(row)
            if card_id:
                section_uses[card_id][title] = _section_use(title, row, default="load_bearing")
        for row in _rows(section.get("reference_only_evidence")):
            card_id = _card_id(row)
            if card_id and title not in section_uses[card_id]:
                section_uses[card_id][title] = _section_use(title, row, default="contextual")
        for card_id in _string_list(section.get("do_not_use_cards")):
            do_not_use[card_id].add(title)
    rows = []
    for card in cards:
        card_id = _card_id(card)
        if not card_id:
            continue
        uses = dict(sorted(section_uses.get(card_id, {}).items()))
        for title in sorted(do_not_use.get(card_id, set())):
            uses.setdefault(title, {"role": "do_not_use", "reason": "Section packet explicitly excluded this card."})
        rows.append(_matrix_row(card, uses))
    assigned = {row["candidate_card_id"] for row in rows if row.get("section_uses")}
    omitted = [
        _omitted_row(card_lookup[card_id])
        for card_id in sorted(set(card_lookup) - assigned)
        if card_id in card_lookup
    ]
    return {
        "schema_id": "evidence_role_matrix_v1",
        "method": "candidate_cards_crosswalked_to_section_context_packets_with_reusable_section_roles",
        "card_count": len(rows),
        "assigned_card_count": len(assigned),
        "omitted_card_count": len(omitted),
        "rows": rows,
        "omitted_cards": omitted,
        "role_counts": _role_counts(rows),
        "issues": ["candidate_cards_not_assigned_to_any_section"] if omitted else [],
    }


def build_section_evidence_working_sets(
    evidence_role_matrix: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = [row for row in evidence_role_matrix.get("rows", []) if isinstance(row, dict)]
    section_order = [str(section.get("section", "")).strip() for section in sections if str(section.get("section", "")).strip()]
    by_section: dict[str, dict[str, list[dict[str, Any]]]] = {
        title: {role: [] for role in (*ROLE_ORDER, "do_not_use")} for title in section_order
    }
    for row in rows:
        card_id = str(row.get("candidate_card_id", "")).strip()
        for title, use in _dict(row.get("section_uses")).items():
            role = str(_dict(use).get("role", "contextual")).strip() or "contextual"
            if title not in by_section:
                by_section[title] = {item: [] for item in (*ROLE_ORDER, "do_not_use")}
            if role not in by_section[title]:
                by_section[title][role] = []
            by_section[title][role].append(_working_card(row, title, _dict(use), card_id=card_id))
    sections_out = []
    for title, role_rows in by_section.items():
        primary = _rank_cards(role_rows.get("load_bearing", []))[:8]
        contrast = _rank_cards(role_rows.get("contrast", []))[:5]
        boundary = _rank_cards(role_rows.get("boundary", []))[:5]
        contextual = _rank_cards(role_rows.get("contextual", []))[:5]
        do_not_use = _rank_cards(role_rows.get("do_not_use", []))[:8]
        section_out = _drop_empty(
            {
                "section": title,
                "schema_id": "section_evidence_working_set_v1",
                "primary_evidence": primary,
                "contrast_evidence": contrast,
                "boundary_evidence": boundary,
                "contextual_evidence": contextual,
                "do_not_use_evidence": do_not_use,
                "budget_report": _budget_report(role_rows, primary, contrast, boundary, contextual),
            }
        )
        sections_out.append(section_out)
    return {
        "schema_id": "section_evidence_working_sets_v1",
        "method": "role_matrix_grouped_into_section_local_model_working_sets",
        "sections": sections_out,
        "issues": _working_set_issues(sections_out),
    }


def build_evidence_role_coverage_report(
    evidence_role_matrix: dict[str, Any],
    section_evidence_working_sets: dict[str, Any],
) -> dict[str, Any]:
    matrix_rows = [row for row in evidence_role_matrix.get("rows", []) if isinstance(row, dict)]
    working_sections = [section for section in section_evidence_working_sets.get("sections", []) if isinstance(section, dict)]
    shown_ids = _shown_card_ids(working_sections)
    omitted_lookup = {
        str(item.get("candidate_card_id")): item
        for item in evidence_role_matrix.get("omitted_cards", [])
        if isinstance(item, dict) and item.get("candidate_card_id")
    }
    high_priority_omitted = [
        _coverage_omitted_card(row, omitted_lookup)
        for row in matrix_rows
        if int(row.get("global_priority", 0) or 0) >= 7
        and row.get("inclusion_recommendation") != "appendix_only"
        and str(row.get("candidate_card_id", "")) not in shown_ids
    ]
    budget_pressure = [
        {
            "section": section.get("section"),
            "budget_report": section.get("budget_report"),
        }
        for section in working_sections
        if _budget_pressure(section.get("budget_report", {}))
    ]
    repeated_same_role = _repeated_same_role_rows(matrix_rows)
    issues = []
    if high_priority_omitted:
        issues.append("high_priority_cards_not_shown_to_any_section")
    if budget_pressure:
        issues.append("section_working_set_budget_pressure")
    if repeated_same_role:
        issues.append("same_card_same_role_reused_across_sections")
    return {
        "schema_id": "evidence_role_coverage_report_v1",
        "status": "warning" if issues else "ready",
        "mode": "report_only",
        "shown_card_count": len(shown_ids),
        "assigned_card_count": int(evidence_role_matrix.get("assigned_card_count", 0) or 0),
        "omitted_card_count": int(evidence_role_matrix.get("omitted_card_count", 0) or 0),
        "high_priority_omitted_cards": high_priority_omitted[:30],
        "budget_pressure_sections": budget_pressure,
        "repeated_same_role_reuse": repeated_same_role[:30],
        "issues": issues,
    }


def _section_use(title: str, row: dict[str, Any], *, default: str) -> dict[str, Any]:
    role = _role_for_row(title, row, default=default)
    return _drop_empty(
        {
            "role": role,
            "section_use": row.get("section_use") or row.get("use") or _default_section_use(role),
            "reason": row.get("reason_for_inclusion") or row.get("reason") or row.get("eligibility_reason"),
            "source": row.get("source"),
            "slot_status": row.get("slot_status"),
            "evidence_weight": row.get("evidence_weight"),
            "model_judgment_needed": row.get("model_judgment_needed"),
        }
    )


def _role_for_row(title: str, row: dict[str, Any], *, default: str) -> str:
    text = " ".join(
        str(value)
        for value in [
            title,
            row.get("intended_role"),
            row.get("role"),
            row.get("slot_id"),
            row.get("slot_status"),
            row.get("section_use"),
            row.get("reason_for_inclusion"),
            " ".join(_string_list(row.get("limitations"))),
        ]
        if str(value).strip()
    ).lower()
    if any(marker in text for marker in ("do_not_use", "appendix only", "rejected")):
        return "do_not_use"
    if any(marker in text for marker in ("crux", "tension", "counter", "challenge", "contrast")):
        return "contrast"
    if any(marker in text for marker in ("scope", "boundary", "exception", "limit", "population", "comparator")):
        return "boundary"
    return default if default in ROLE_ORDER else "contextual"


def _matrix_row(card: dict[str, Any], section_uses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _drop_empty(
        {
            "candidate_card_id": _card_id(card),
            "source_card_ids": _string_list(card.get("source_card_ids"))[:6],
            "claim_ids": _string_list(card.get("claim_ids"))[:6],
            "source_ids": _string_list(card.get("source_ids"))[:6],
            "source_titles": _string_list(card.get("source_titles"))[:3],
            "claim": _short_text(str(card.get("claim", "")), 360),
            "source_excerpt": _short_text(str(card.get("source_excerpt", "")), 520),
            "global_priority": int(card.get("decision_relevance_score", 0) or 0),
            "quality": card.get("quality"),
            "inclusion_recommendation": card.get("inclusion_recommendation"),
            "quantity_values": _string_list(card.get("quantity_values"))[:6],
            "limitations": _string_list(card.get("limitations"))[:6],
            "section_uses": section_uses,
            "assignment_status": "assigned" if section_uses else "omitted",
        }
    )


def _working_card(row: dict[str, Any], title: str, use: dict[str, Any], *, card_id: str) -> dict[str, Any]:
    return _drop_empty(
        {
            "candidate_card_id": card_id,
            "source_card_ids": _string_list(row.get("source_card_ids"))[:4],
            "claim_ids": _string_list(row.get("claim_ids"))[:4],
            "source_ids": _string_list(row.get("source_ids"))[:4],
            "source": ", ".join(_string_list(row.get("source_titles")) or _string_list(row.get("source_ids"))),
            "claim": _short_text(str(row.get("claim", "")), 320),
            "source_excerpt": _short_text(str(row.get("source_excerpt", "")), 420),
            "section_use": use.get("section_use"),
            "reason_for_inclusion": use.get("reason"),
            "evidence_role": use.get("role"),
            "quality": row.get("quality"),
            "evidence_weight": use.get("evidence_weight"),
            "slot_status": use.get("slot_status"),
            "quantity_values": _string_list(row.get("quantity_values"))[:4],
            "limitations": _string_list(row.get("limitations"))[:4],
            "use": _model_use_instruction(str(use.get("role", "")), title),
        }
    )


def _omitted_row(card: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    if card.get("inclusion_recommendation") == "appendix_only":
        reasons.append("appendix_only")
    if int(card.get("decision_relevance_score", 0) or 0) < 7:
        reasons.append("below_main_text_relevance")
    if card.get("anchor_confidence") == "missing":
        reasons.append("missing_source_anchor")
    if card.get("fragment_risk"):
        reasons.append("fragment_risk")
    if not reasons:
        reasons.append("not_selected_by_section_context")
    return {
        "candidate_card_id": _card_id(card),
        "global_priority": int(card.get("decision_relevance_score", 0) or 0),
        "inclusion_recommendation": card.get("inclusion_recommendation"),
        "reasons": reasons,
        "claim": _short_text(str(card.get("claim", "")), 220),
    }


def _budget_report(
    role_rows: dict[str, list[dict[str, Any]]],
    primary: list[dict[str, Any]],
    contrast: list[dict[str, Any]],
    boundary: list[dict[str, Any]],
    contextual: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "primary_available": len(role_rows.get("load_bearing", [])),
        "primary_included": len(primary),
        "contrast_available": len(role_rows.get("contrast", [])),
        "contrast_included": len(contrast),
        "boundary_available": len(role_rows.get("boundary", [])),
        "boundary_included": len(boundary),
        "contextual_available": len(role_rows.get("contextual", [])),
        "contextual_included": len(contextual),
    }


def _working_set_issues(sections: list[dict[str, Any]]) -> list[str]:
    issues = []
    if any(not section.get("primary_evidence") for section in sections if section.get("section") != "Decision Brief"):
        issues.append("section_without_primary_evidence")
    if any(_budget_pressure(section.get("budget_report", {})) for section in sections):
        issues.append("section_working_set_budget_pressure")
    return issues


def _budget_pressure(report: Any) -> bool:
    row = _dict(report)
    return any(int(row.get(f"{name}_available", 0) or 0) > int(row.get(f"{name}_included", 0) or 0) for name in ("primary", "contrast", "boundary", "contextual"))


def _shown_card_ids(sections: list[dict[str, Any]]) -> set[str]:
    shown: set[str] = set()
    for section in sections:
        for key in ("primary_evidence", "contrast_evidence", "boundary_evidence", "contextual_evidence"):
            for row in section.get(key, []) if isinstance(section.get(key), list) else []:
                if isinstance(row, dict) and row.get("candidate_card_id"):
                    shown.add(str(row["candidate_card_id"]))
    return shown


def _coverage_omitted_card(row: dict[str, Any], omitted_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    card_id = str(row.get("candidate_card_id", ""))
    return _drop_empty(
        {
            "candidate_card_id": card_id,
            "global_priority": row.get("global_priority"),
            "inclusion_recommendation": row.get("inclusion_recommendation"),
            "claim": _short_text(str(row.get("claim", "")), 220),
            "section_uses": row.get("section_uses"),
            "omission_reasons": omitted_lookup.get(card_id, {}).get("reasons"),
        }
    )


def _repeated_same_role_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repeated: list[dict[str, Any]] = []
    for row in rows:
        by_role: dict[str, list[str]] = defaultdict(list)
        for section, use in _dict(row.get("section_uses")).items():
            role = str(_dict(use).get("role", "")).strip()
            if role and role != "do_not_use":
                by_role[role].append(str(section))
        for role, sections in sorted(by_role.items()):
            if len(sections) > 1:
                repeated.append(
                    {
                        "candidate_card_id": row.get("candidate_card_id"),
                        "role": role,
                        "sections": sections,
                        "diagnostic": "Reuse is allowed, but repeated same-role use should add section-specific value.",
                    }
                )
    return repeated


def _role_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for use in _dict(row.get("section_uses")).values():
            role = str(_dict(use).get("role", "unknown"))
            counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def _rank_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -int(row.get("global_priority", row.get("decision_relevance_score", 0)) or 0),
            str(row.get("candidate_card_id", "")),
        ),
    )


def _candidate_cards(report: dict[str, Any]) -> list[dict[str, Any]]:
    cards = report.get("cards", []) if isinstance(report.get("cards"), list) else []
    return [card for card in cards if isinstance(card, dict)]


def _section_packets(report: dict[str, Any]) -> list[dict[str, Any]]:
    sections = report.get("sections", []) if isinstance(report.get("sections"), list) else []
    return [section for section in sections if isinstance(section, dict)]


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _card_id(row: dict[str, Any]) -> str:
    return str(row.get("candidate_card_id", "")).strip()


def _short_text(text: str, max_chars: int) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ({}, [], "", None)}


def _default_section_use(role: str) -> str:
    if role == "contrast":
        return "Use this as a counterweight or decision-changing tension."
    if role == "boundary":
        return "Use this to bound scope, applicability, or implementation."
    if role == "contextual":
        return "Mention only if it clarifies the section-specific implication."
    if role == "do_not_use":
        return "Do not use this card in this section."
    return "Use this as load-bearing evidence for this section's analytic move."


def _model_use_instruction(role: str, title: str) -> str:
    if role == "contrast":
        return "Use to explain the section-specific counterweight or crux; do not bury it as generic context."
    if role == "boundary":
        return "Use to define where the answer does and does not travel."
    if role == "contextual":
        return "Use briefly only if it improves the reader's understanding of this section."
    if role == "do_not_use":
        return "Do not use in this section."
    return f"Use as primary evidence for {title}; synthesize rather than list."
