from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_spine_validation import validate_canonical_decision_spine


def build_canonical_decision_spine(
    candidate_map: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    question: str,
    classical_selection_report: dict[str, Any],
    slot_eligibility_audit: dict[str, Any],
) -> dict[str, Any]:
    cards = _rank_cards(_candidate_cards(scaffold), classical_selection_report)
    by_role = _cards_by_role(cards)
    source_anchors = _source_anchors(cards, scaffold)
    default_field = _default_answer_field(scaffold, question, cards)
    missing_fields = _missing_slot_fields(slot_eligibility_audit)
    spine = {
        "schema_id": "canonical_decision_spine_v1",
        "decision_question": question,
        "status": _spine_status(cards, missing_fields),
        "default_answer": default_field,
        "exception_answers": _fields_from_cards(by_role["counterweight"][:2], "exception_answer", "exception"),
        "dose_or_intensity_boundaries": _quantity_fields(by_role["quantity"] + _cards_with_quantities(cards)),
        "population_boundaries": _fields_from_cards(by_role["scope"][:3], "population_boundary", "scope"),
        "strongest_support": _fields_from_cards(by_role["support"][:4], "strongest_support", "support"),
        "strongest_counterevidence": _fields_from_cards(by_role["counterweight"][:4], "strongest_counterevidence", "counterweight"),
        "mechanism_or_proxy_evidence": _mechanism_fields(cards),
        "comparator_or_substitution": _comparator_fields(cards, slot_eligibility_audit),
        "evidence_quality_limits": _limit_fields(cards, scaffold),
        "missing_decision_slots": missing_fields,
        "confidence": _confidence(scaffold, missing_fields),
        "source_anchors": source_anchors,
        "construction_report": {
            "schema_id": "canonical_decision_spine_construction_report_v1",
            "method": "deterministic_source_backed_candidate_selection_with_classical_rank_features",
            "candidate_card_count": len(cards),
            "source_anchor_count": len(source_anchors),
            "classical_signal_count": len(classical_selection_report.get("selection_features", []))
            if isinstance(classical_selection_report.get("selection_features"), list)
            else 0,
        },
    }
    spine["canonical_decision_spine_validation"] = validate_canonical_decision_spine(spine)
    return spine


def _default_answer_field(scaffold: dict[str, Any], question: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    bottom_line = synthesis.get("bottom_line", {}) if isinstance(synthesis.get("bottom_line"), dict) else {}
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    default_answer = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    top_cards = [card for card in cards if card.get("role") in {"support", "quantity"}][:3] or cards[:2]
    if not top_cards:
        return {
            "field_id": "default_answer",
            "claim": f"The current source packet is too sparse to answer the decision question without caveats: {question}",
            "role": "missing_slot",
            "source_ids": [],
            "candidate_card_ids": [],
            "claim_ids": [],
            "quantity_ids": [],
            "confidence": "low",
            "limits": ["no_usable_candidate_cards"],
        }
    claim = (
        str(bottom_line.get("current_read", "")).strip()
        or str(default_answer.get("plain_language_instruction", "")).strip()
        or _default_from_cards(question, top_cards)
    )
    if _looks_like_answer_instruction(claim):
        claim = _default_from_cards(question, top_cards)
    return _field_from_cards("default_answer", claim, "default_answer", top_cards)


def _fields_from_cards(cards: list[dict[str, Any]], prefix: str, role: str) -> list[dict[str, Any]]:
    fields = []
    for index, card in enumerate(_dedupe_cards(cards), start=1):
        fields.append(_field_from_cards(f"{prefix}_{index}", str(card.get("claim", "")), role, [card]))
    return [field for field in fields if field.get("claim")]


def _quantity_fields(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = []
    seen_values: set[str] = set()
    for card in _dedupe_cards(cards):
        values = _string_list(card.get("quantity_values"))
        if not values:
            continue
        new_values = [value for value in values if value not in seen_values]
        if not new_values:
            continue
        seen_values.update(new_values)
        fields.append(_field_from_cards(f"dose_boundary_{len(fields) + 1}", str(card.get("claim", "")), "dose_or_intensity_boundary", [card], quantity_ids=new_values))
    return fields[:4]


def _mechanism_fields(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    marker_terms = ("mechanism", "surrogate", "proxy", "pathway", "mediator", "biomarker", "model")
    selected = [card for card in cards if any(term in str(card.get("claim", "")).lower() for term in marker_terms)]
    return _fields_from_cards(selected[:3], "mechanism_proxy", "mechanism_or_proxy")


def _comparator_fields(cards: list[dict[str, Any]], audit: dict[str, Any]) -> list[dict[str, Any]]:
    marker_terms = ("compare", "versus", "rather than", "instead", "alternative", "substitution", "comparator")
    selected = [card for card in cards if any(term in str(card.get("claim", "")).lower() for term in marker_terms)]
    fields = _fields_from_cards(selected[:3], "comparator_substitution", "comparator_or_substitution")
    if fields:
        return fields
    for slot in audit.get("slots", []) if isinstance(audit.get("slots"), list) else []:
        if not isinstance(slot, dict) or "comparator" not in str(slot.get("slot_id", "")):
            continue
        rows = slot.get("accepted_rows", []) if isinstance(slot.get("accepted_rows"), list) else []
        for row in rows[:2]:
            if isinstance(row, dict) and str(row.get("claim", "")).strip():
                fields.append(
                    {
                        "field_id": f"comparator_substitution_{len(fields) + 1}",
                        "claim": str(row.get("claim", "")),
                        "role": "comparator_or_substitution",
                        "source_ids": _string_list(row.get("source")),
                        "candidate_card_ids": [],
                        "claim_ids": [],
                        "quantity_ids": [],
                        "confidence": "medium",
                        "limits": [],
                    }
                )
    return fields[:3]


def _limit_fields(cards: list[dict[str, Any]], scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    selected = [card for card in cards if card.get("role") == "limitation" or _string_list(card.get("limitations"))]
    fields = _fields_from_cards(selected[:4], "evidence_quality_limit", "evidence_quality_limit")
    sufficiency = scaffold.get("source_sufficiency_report", {}) if isinstance(scaffold.get("source_sufficiency_report"), dict) else {}
    for missing in _string_list(sufficiency.get("missing_source_categories"))[:3]:
        fields.append(
            {
                "field_id": f"evidence_quality_limit_{len(fields) + 1}",
                "claim": f"The source set is missing {missing.replace('_', ' ')}.",
                "role": "evidence_quality_limit",
                "source_ids": [],
                "candidate_card_ids": [],
                "claim_ids": [],
                "quantity_ids": [],
                "confidence": "high",
                "limits": [missing],
            }
        )
    return fields[:5]


def _missing_slot_fields(audit: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    for slot in audit.get("slots", []) if isinstance(audit.get("slots"), list) else []:
        if not isinstance(slot, dict) or slot.get("status") != "missing" or not slot.get("required"):
            continue
        slot_id = str(slot.get("slot_id", ""))
        fields.append(
            {
                "field_id": f"missing_{slot_id}",
                "slot_id": slot_id,
                "claim": str(slot.get("missing_message") or f"The current source packet does not establish {slot_id}."),
                "role": "missing_slot",
                "source_ids": [],
                "candidate_card_ids": [],
                "claim_ids": [],
                "quantity_ids": [],
                "confidence": "high",
                "limits": [slot_id],
            }
        )
    return fields


def _field_from_cards(
    field_id: str,
    claim: str,
    role: str,
    cards: list[dict[str, Any]],
    *,
    quantity_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "claim": _shorten(claim, 420),
        "role": role,
        "source_ids": _dedupe([source_id for card in cards for source_id in _string_list(card.get("source_ids"))]),
        "candidate_card_ids": _dedupe([str(card.get("candidate_card_id")) for card in cards if card.get("candidate_card_id")]),
        "claim_ids": _dedupe([claim_id for card in cards for claim_id in _string_list(card.get("claim_ids"))]),
        "quantity_ids": quantity_ids or _dedupe([value for card in cards for value in _string_list(card.get("quantity_values"))]),
        "confidence": _field_confidence(cards),
        "limits": _dedupe([limit for card in cards for limit in _string_list(card.get("limitations"))])[:4],
    }


def _rank_cards(cards: list[dict[str, Any]], classical: dict[str, Any]) -> list[dict[str, Any]]:
    features = {
        str(row.get("candidate_card_id")): row
        for row in classical.get("selection_features", [])
        if isinstance(row, dict) and str(row.get("candidate_card_id", "")).strip()
    } if isinstance(classical.get("selection_features"), list) else {}

    def score(card: dict[str, Any]) -> tuple[float, int, str]:
        feature = features.get(str(card.get("candidate_card_id")), {})
        rank = float(feature.get("advisory_rank_score", 0.0) or 0.0)
        return (
            rank,
            int(card.get("decision_relevance_score", 0) or 0),
            str(card.get("candidate_card_id", "")),
        )

    usable = [card for card in cards if card.get("inclusion_recommendation") != "appendix_only"]
    if usable:
        return sorted(usable, key=score, reverse=True)
    fallback = [
        dict(card, spine_fallback_reason="all_candidates_were_appendix_only")
        for card in cards
        if card.get("anchor_confidence") != "missing" and not card.get("fragment_risk")
    ]
    return sorted(fallback, key=score, reverse=True)


def _candidate_cards(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    report = scaffold.get("candidate_evidence_cards", {}) if isinstance(scaffold.get("candidate_evidence_cards"), dict) else {}
    return [card for card in report.get("cards", []) if isinstance(card, dict)] if isinstance(report.get("cards"), list) else []


def _cards_by_role(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups = {role: [] for role in ("support", "counterweight", "scope", "quantity", "limitation", "context")}
    for card in cards:
        role = str(card.get("role") or "context")
        groups.setdefault(role, []).append(card)
        if card.get("quantity_values") and card not in groups["quantity"]:
            groups["quantity"].append(card)
    return groups


def _cards_with_quantities(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [card for card in cards if _string_list(card.get("quantity_values"))]


def _source_anchors(cards: list[dict[str, Any]], scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    source_names = scaffold.get("source_display_names", {}) if isinstance(scaffold.get("source_display_names"), dict) else {}
    anchors: dict[str, dict[str, Any]] = {}
    for card in cards:
        for source_id in _string_list(card.get("source_ids")):
            anchors.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "source": source_names.get(source_id) or ", ".join(_string_list(card.get("source_titles"))) or source_id,
                    "candidate_card_ids": [],
                },
            )
            anchors[source_id]["candidate_card_ids"].extend(_string_list(card.get("candidate_card_id")))
    for anchor in anchors.values():
        anchor["candidate_card_ids"] = _dedupe(anchor["candidate_card_ids"])
    return list(anchors.values())[:20]


def _default_from_cards(question: str, cards: list[dict[str, Any]]) -> str:
    if cards:
        return f"For the decision question, the current source packet is most directly carried by: {cards[0].get('claim', '')}"
    return f"The current source packet is too sparse to answer the decision question without caveats: {question}"


def _looks_like_answer_instruction(text: str) -> bool:
    return str(text).strip().lower().startswith(
        (
            "state ",
            "do not ",
            "phrase ",
            "preserve ",
            "avoid ",
            "say ",
            "write ",
        )
    )


def _spine_status(cards: list[dict[str, Any]], missing_fields: list[dict[str, Any]]) -> str:
    if not cards:
        return "insufficient"
    if missing_fields or any(card.get("spine_fallback_reason") for card in cards):
        return "bounded"
    return "ready"


def _confidence(scaffold: dict[str, Any], missing_fields: list[dict[str, Any]]) -> str:
    default = _dict(_dict(scaffold.get("decision_model")).get("default_answer"))
    confidence = str(default.get("confidence_cap") or scaffold.get("confidence_cap") or "medium")
    return "low" if missing_fields and confidence == "high" else confidence


def _field_confidence(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "low"
    qualities = {str(card.get("quality", "")) for card in cards}
    if "usable" in qualities and len({source for card in cards for source in _string_list(card.get("source_ids"))}) >= 2:
        return "high"
    if "usable" in qualities:
        return "medium"
    return "low"


def _dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for card in cards:
        card_id = str(card.get("candidate_card_id", ""))
        if not card_id or card_id in seen:
            continue
        seen.add(card_id)
        out.append(card)
    return out


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


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _shorten(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "..."
