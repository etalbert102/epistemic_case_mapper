from __future__ import annotations

import re
from typing import Any


def build_slot_eligibility_audit(
    scaffold: dict[str, Any],
    classical_selection_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit why each decision memo slot is filled or missing.

    This layer is deliberately diagnostic. It records accepted and rejected
    candidates before the canonical spine decides which facts should govern
    reader-facing prose.
    """
    from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_slots import build_decision_memo_slots

    slot_report = build_decision_memo_slots(scaffold)
    cards = _candidate_cards(scaffold)
    feature_lookup = _feature_lookup(classical_selection_report or {})
    rows = [
        _slot_audit_row(slot, cards, feature_lookup)
        for slot in slot_report.get("slots", [])
        if isinstance(slot, dict)
    ]
    issues = _audit_issues(rows)
    return {
        "schema_id": "slot_eligibility_audit_v1",
        "method": "decision_slot_rows_plus_candidate_rejection_reasons",
        "status": "warning" if issues else "ready",
        "checked_candidate_pools": [
            "decision_memo_slots",
            "candidate_evidence_cards",
            "curated_evidence_packets",
            "evidence_weighting_ledger",
            "quantity_ledger",
            "classical_evidence_selection_report",
        ],
        "slots": rows,
        "coverage": slot_report.get("coverage", {}),
        "issues": issues,
    }


def _slot_audit_row(
    slot: dict[str, Any],
    cards: list[dict[str, Any]],
    feature_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    accepted_rows = [row for row in slot.get("rows", []) if isinstance(row, dict)]
    accepted_cards = _matched_cards(accepted_rows, cards)
    rejected_cards = [
        _rejected_card(card, slot, feature_lookup)
        for card in cards
        if _card_id(card) not in {_card_id(accepted) for accepted in accepted_cards}
        and _card_relevant_to_slot(card, str(slot.get("slot_id", "")))
    ]
    rejected_cards = [row for row in rejected_cards if row]
    status = "filled" if accepted_rows or accepted_cards else "missing"
    return {
        "slot_id": slot.get("slot_id"),
        "label": slot.get("label"),
        "required": bool(slot.get("required")),
        "status": status,
        "missing_message": slot.get("missing_message") if status == "missing" else "",
        "accepted_rows": [_compact_row(row) for row in accepted_rows],
        "accepted_candidate_cards": [_compact_card(card, feature_lookup) for card in accepted_cards],
        "rejected_candidate_cards": rejected_cards[:12],
        "checked_candidate_pools": [
            "slot_rows",
            "candidate_cards",
            "classical_selection_features",
        ],
    }


def _matched_cards(rows: list[dict[str, Any]], cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        row_terms = _terms(f"{row.get('claim', '')} {row.get('source', '')}")
        for card in cards:
            card_id = _card_id(card)
            if not card_id or card_id in seen:
                continue
            card_terms = _terms(f"{card.get('claim', '')} {' '.join(_string_list(card.get('source_titles')))}")
            if row_terms and card_terms and len(row_terms & card_terms) >= min(3, len(row_terms)):
                matched.append(card)
                seen.add(card_id)
    return matched


def _rejected_card(
    card: dict[str, Any],
    slot: dict[str, Any],
    feature_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    reasons: list[str] = []
    if card.get("inclusion_recommendation") == "appendix_only":
        reasons.append(str(card.get("map_eligibility_reason") or "appendix_only_candidate"))
    if card.get("off_question_risk"):
        reasons.append("off_question_risk")
    if not _card_relevant_to_slot(card, str(slot.get("slot_id", ""))):
        reasons.append("role_or_section_not_slot_relevant")
    if not reasons:
        reasons.append("lower_ranked_than_accepted_slot_rows")
    compact = _compact_card(card, feature_lookup)
    compact["rejection_reasons"] = reasons
    return compact


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "source": row.get("source"),
            "claim": _shorten(str(row.get("claim", "")), 280),
            "section": row.get("section"),
            "weight": row.get("weight"),
            "score": row.get("score"),
            "reader_score": row.get("reader_score"),
            "decision_concepts": _string_list(row.get("decision_concepts"))[:6],
            "evidence_slots": _string_list(row.get("evidence_slots"))[:6],
        }
    )


def _compact_card(card: dict[str, Any], feature_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    card_id = _card_id(card)
    feature = feature_lookup.get(card_id, {})
    return _drop_empty(
        {
            "candidate_card_id": card_id,
            "source_card_ids": _string_list(card.get("source_card_ids"))[:4],
            "source_ids": _string_list(card.get("source_ids"))[:4],
            "claim_ids": _string_list(card.get("claim_ids"))[:4],
            "role": card.get("role"),
            "claim": _shorten(str(card.get("claim", "")), 280),
            "quality": card.get("quality"),
            "decision_relevance_score": card.get("decision_relevance_score"),
            "inclusion_recommendation": card.get("inclusion_recommendation"),
            "quantity_values": _string_list(card.get("quantity_values"))[:4],
            "classical_rank_score": feature.get("advisory_rank_score"),
            "question_relevance_score": feature.get("question_relevance_score"),
            "graph_centrality_score": feature.get("graph_centrality_score"),
        }
    )


def _candidate_cards(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    report = scaffold.get("candidate_evidence_cards", {}) if isinstance(scaffold.get("candidate_evidence_cards"), dict) else {}
    return [card for card in report.get("cards", []) if isinstance(card, dict)] if isinstance(report.get("cards"), list) else []


def _feature_lookup(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    features = report.get("selection_features", []) if isinstance(report.get("selection_features"), list) else []
    return {
        str(row.get("candidate_card_id")): row
        for row in features
        if isinstance(row, dict) and str(row.get("candidate_card_id", "")).strip()
    }


def _card_relevant_to_slot(card: dict[str, Any], slot_id: str) -> bool:
    role = str(card.get("role", "")).lower()
    sections = " ".join(_string_list(card.get("section_candidates"))).lower()
    claim = str(card.get("claim", "")).lower()
    if slot_id in {"main_support", "hard_outcome_support"}:
        return role in {"support", "quantity"} or "support" in sections
    if slot_id in {"counterevidence_or_tension", "hard_outcome_counter", "safety_or_risk"}:
        return role in {"counterweight", "limitation"} or "challenge" in claim or "risk" in claim
    if slot_id in {"scope_conditions", "default_population_boundary", "high_risk_subgroup"}:
        return role in {"scope", "limitation"} or "scope" in sections
    if slot_id in {"dose_intensity_boundary", "mechanism_proxy", "mechanism_or_surrogate"}:
        return bool(card.get("quantity_values")) or role in {"quantity", "context"}
    if slot_id in {"alternatives_or_comparators", "comparator_substitution"}:
        return any(term in claim for term in ("compare", "versus", "rather than", "instead", "substitution", "alternative"))
    if slot_id in {"evidence_type_limits", "study_design_limits", "implementation_constraints"}:
        return role in {"limitation", "scope", "context"}
    return True


def _audit_issues(rows: list[dict[str, Any]]) -> list[str]:
    issues = []
    for row in rows:
        if row.get("status") == "missing" and row.get("accepted_candidate_cards"):
            issues.append(f"{row.get('slot_id')}: missing slot has accepted candidate cards")
        if row.get("status") == "missing" and not row.get("checked_candidate_pools"):
            issues.append(f"{row.get('slot_id')}: missing slot lacks checked candidate pools")
    return issues


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", text.lower()) if len(term) >= 4}


def _card_id(card: dict[str, Any]) -> str:
    return str(card.get("candidate_card_id", "")).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _shorten(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "..."


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}
