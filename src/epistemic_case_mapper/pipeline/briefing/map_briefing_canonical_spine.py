from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_answer_frame import is_weak_answer_frame
from epistemic_case_mapper.pipeline.briefing.map_briefing_packet_eligibility import question_content_terms, question_overlap_count
from epistemic_case_mapper.pipeline.briefing.map_briefing_text_cleanup import reader_facing_unresolved_source_category
from epistemic_case_mapper.pipeline.briefing.map_briefing_spine_validation import validate_canonical_decision_spine


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
    support_fields = _evidence_carrier_fields(by_role["support"], cards, "strongest_support", "support")
    counterevidence_fields = _evidence_carrier_fields(by_role["counterweight"], cards, "strongest_counterevidence", "counterweight")
    spine = {
        "schema_id": "canonical_decision_spine_v1",
        "decision_question": question,
        "status": _spine_status(cards, missing_fields),
        "default_answer": default_field,
        "exception_answers": _fields_from_cards(by_role["counterweight"][:2], "exception_answer", "exception"),
        "dose_or_intensity_boundaries": _quantity_fields(by_role["quantity"] + _cards_with_quantities(cards)),
        "population_boundaries": _fields_from_cards(by_role["scope"][:3], "population_boundary", "scope"),
        "strongest_support": support_fields,
        "strongest_counterevidence": counterevidence_fields,
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
            "support_field_count": len(support_fields),
            "counterevidence_field_count": len(counterevidence_fields),
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
    top_cards = _default_answer_cards(cards, question=question)
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
        _bottom_line_default_claim(bottom_line, question=question)
        or _default_from_cards(question, top_cards)
        or str(default_answer.get("plain_language_instruction", "")).strip()
    )
    if _looks_like_answer_instruction(claim) or is_weak_answer_frame(claim, question=question):
        claim = _default_from_cards(question, top_cards)
    return _field_from_cards("default_answer", claim, "default_answer", top_cards)


def _fields_from_cards(cards: list[dict[str, Any]], prefix: str, role: str) -> list[dict[str, Any]]:
    fields = []
    for index, card in enumerate(_dedupe_cards(cards), start=1):
        fields.append(_field_from_cards(f"{prefix}_{index}", str(card.get("claim", "")), role, [card]))
    return [field for field in fields if field.get("claim")]


def _evidence_carrier_fields(
    role_cards: list[dict[str, Any]],
    all_cards: list[dict[str, Any]],
    prefix: str,
    role: str,
) -> list[dict[str, Any]]:
    selected = _load_bearing_cards(role_cards)[:4] or _fallback_evidence_carrier_cards(all_cards, role)
    fields = _fields_from_cards(selected, prefix, role)
    if selected and all(card in role_cards for card in selected):
        return fields
    for field in fields:
        field["limits"] = _dedupe([*field.get("limits", []), "role_inferred_from_claim_text"])
    return fields


def _fallback_evidence_carrier_cards(cards: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    scoring_terms = _support_terms() if role == "support" else _counterevidence_terms()
    blocked_terms = _counterevidence_terms() if role == "support" else _support_terms()
    scored = []
    for card in cards:
        if not _eligible_load_bearing_card(card):
            continue
        claim = str(card.get("claim", "")).lower()
        score = _stance_score(claim, scoring_terms) - 0.5 * _stance_score(claim, blocked_terms)
        if score <= 0:
            continue
        scored.append((
            score,
            _answer_relevance_score(card),
            int(card.get("decision_relevance_score", 0) or 0),
            str(card.get("candidate_card_id", "")),
            card,
        ))
    if scored:
        return [row[4] for row in sorted(scored, reverse=True)[:4]]
    if role != "support":
        return []
    return [
        card
        for card in cards
        if _eligible_load_bearing_card(card)
    ][:2]


def _default_answer_cards(cards: list[dict[str, Any]], *, question: str) -> list[dict[str, Any]]:
    role_preferred = [
        card
        for card in cards
        if (card.get("role") in {"support", "quantity"} or {"support", "quantity"} & set(_string_list(card.get("evidence_roles"))))
        and _eligible_load_bearing_card(card)
    ]
    if role_preferred:
        return [row[4] for row in sorted(
            (
                (
                    _answer_relevance_score(card),
                    _question_overlap_score(card, question),
                    int(card.get("decision_relevance_score", 0) or 0),
                    str(card.get("candidate_card_id", "")),
                    card,
                )
                for card in role_preferred
            ),
            reverse=True,
        )[:3]]
    scored = [
        (
            _answer_relevance_score(card),
            _question_overlap_score(card, question),
            int(card.get("decision_relevance_score", 0) or 0),
            str(card.get("candidate_card_id", "")),
            card,
        )
        for card in cards
        if _eligible_load_bearing_card(card)
    ]
    scored = [row for row in scored if row[0] > 0 or row[1] > 0 or row[2] > 0]
    if scored:
        return [row[4] for row in sorted(scored, reverse=True)[:3]]
    return [
        dict(card, spine_fallback_reason="no_clean_load_bearing_default_card")
        for card in cards
        if _minimally_usable_card(card)
    ][:2]

def _question_overlap_score(card: dict[str, Any], question: str) -> int:
    terms = question_content_terms(question)
    return max(
        question_overlap_count(str(card.get("claim", "")), terms),
        question_overlap_count(str(card.get("source_excerpt", "")), terms),
    )


def _load_bearing_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [card for card in cards if _eligible_load_bearing_card(card)]


def _eligible_load_bearing_card(card: dict[str, Any]) -> bool:
    if not _minimally_usable_card(card):
        return False
    claim = str(card.get("claim", "")).strip()
    if _looks_like_title_or_heading(claim):
        return False
    if _looks_like_truncated_claim(claim):
        return False
    if _looks_like_methods_only(claim):
        return False
    if _looks_like_source_metadata(claim):
        return False
    return True


def _minimally_usable_card(card: dict[str, Any]) -> bool:
    claim = str(card.get("claim", "")).strip()
    if card.get("anchor_confidence") == "missing" or card.get("fragment_risk") or card.get("boilerplate_risk"):
        return False
    if card.get("inclusion_recommendation") == "appendix_only" and not card.get("spine_fallback_reason"):
        return False
    if len(_terms(claim)) < 5:
        return False
    return True


def _answer_relevance_score(card: dict[str, Any]) -> int:
    claim = str(card.get("claim", "")).lower()
    score = 0
    for term in (
        "associated",
        "association",
        "risk",
        "outcome",
        "mortality",
        "cardiovascular",
        "adverse",
        "benefit",
        "reduction",
        "increase",
        "decrease",
        "guidance",
        "recommendation",
        "conclusion",
        "results",
    ):
        if term in claim:
            score += 1
    if card.get("quantity_values"):
        score += 2
    if card.get("role") == "support":
        score += 1
    if card.get("role") == "counterweight":
        score += 1
    return score


def _stance_score(text: str, terms: tuple[str, ...]) -> float:
    return sum(1.0 for term in terms if term in text and not _negates_counter_signal(text, term))


def _negates_counter_signal(text: str, term: str) -> bool:
    if term not in _counterevidence_terms():
        return False
    index = text.find(term)
    if index < 0:
        return False
    prefix = text[max(0, index - 36):index]
    return any(marker in prefix for marker in ("not ", "no ", "without ", "lack of ", "absence of ", "did not "))


def _support_terms() -> tuple[str, ...]:
    return (
        "not associated",
        "no association",
        "no significant",
        "did not increase",
        "did not have adverse",
        "does not increase",
        "no adverse",
        "without adverse",
        "lower risk",
        "reduced risk",
        "decreased risk",
        "improved",
        "improves",
        "benefit",
        "effective",
        "supports",
    )


def _counterevidence_terms() -> tuple[str, ...]:
    return (
        "higher risk",
        "increased risk",
        "increase in risk",
        "associated with risk",
        "positive association",
        "harmful",
        "adverse",
        "worse",
        "failure",
        "delay",
        "cost",
        "constraint",
    )


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
    selected = [
        card
        for card in cards
        if card.get("role") == "limitation" or "limitation" in _string_list(card.get("evidence_roles")) or _string_list(card.get("limitations"))
    ]
    fields = _fields_from_cards(selected[:4], "evidence_quality_limit", "evidence_quality_limit")
    sufficiency = scaffold.get("source_sufficiency_report", {}) if isinstance(scaffold.get("source_sufficiency_report"), dict) else {}
    for missing in _string_list(sufficiency.get("missing_source_categories"))[:3]:
        fields.append(
            {
                "field_id": f"evidence_quality_limit_{len(fields) + 1}",
                "claim": reader_facing_unresolved_source_category(missing),
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
                "claim": str(slot.get("missing_message") or f"The current map does not cleanly establish {slot_id}."),
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
        roles = _dedupe([str(card.get("role") or "context"), *_string_list(card.get("evidence_roles"))]) or ["context"]
        for role in roles:
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


def _bottom_line_default_claim(bottom_line: dict[str, Any], *, question: str) -> str:
    current_read = str(bottom_line.get("current_read", "")).strip()
    if current_read and not _looks_like_answer_instruction(current_read) and not is_weak_answer_frame(current_read, question=question):
        return current_read
    classification = str(bottom_line.get("classification", "")).strip()
    why = str(bottom_line.get("why_this_frame", "")).strip()
    if classification:
        label = classification.replace("_", " ")
        claim = f"The source packet supports a bounded {label} read."
        if why and not _looks_like_answer_instruction(why):
            claim += f" {why}"
        return "" if is_weak_answer_frame(claim, question=question) else claim
    return ""


def _default_from_cards(question: str, cards: list[dict[str, Any]]) -> str:
    if cards:
        claim = str(cards[0].get("claim", "")).strip()
        if _eligible_load_bearing_card(cards[0]):
            return f"The current answer is bounded by the source-backed finding that {claim[0].lower() + claim[1:] if claim else claim}"
        return f"The current source packet can only support a bounded answer to the decision question: {question}"
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


def _looks_like_title_or_heading(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return True
    terms = _terms(cleaned)
    if len(terms) < 5:
        return True
    lower = cleaned.lower()
    if lower.startswith(("title:", "source id:", "journal:", "publication year:", "doi:", "pmid:")):
        return True
    if ":" in cleaned and not any(marker in lower for marker in _evidence_markers()):
        return True
    if cleaned.endswith(".") and any(marker in lower for marker in _evidence_markers()):
        return False
    titlecase_terms = [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z'-]+", cleaned)
        if term[:1].isupper() and term.lower() not in _LOWERCASE_EVIDENCE_WORDS
    ]
    alpha_terms = re.findall(r"[A-Za-z][A-Za-z'-]+", cleaned)
    if alpha_terms and len(titlecase_terms) / max(1, len(alpha_terms)) >= 0.65 and not any(marker in lower for marker in _evidence_markers()):
        return True
    return False


def _looks_like_methods_only(text: str) -> bool:
    lower = str(text).strip().lower()
    if lower.startswith(("methods:", "method:", "background:", "objective:", "objectives:", "design:", "setting:", "participants:")):
        return not any(marker in lower for marker in ("result", "conclusion", "associated", "risk", "effect", "outcome"))
    if lower.startswith("results:"):
        return False
    return False


def _looks_like_source_metadata(text: str) -> bool:
    lower = str(text).strip().lower()
    return lower.startswith(
        (
            "limitations: automatically fetched",
            "fetch status:",
            "source id:",
            "pubmed url:",
            "doi:",
            "pmid:",
            "journal:",
            "publication year:",
        )
    )


def _looks_like_truncated_claim(text: str) -> bool:
    stripped = re.sub(r"\s+", " ", str(text)).strip()
    return stripped.endswith("...") or stripped.endswith(("although", "because", "while", "whereas", "including"))


def _evidence_markers() -> tuple[str, ...]:
    return (
        "associated",
        "association",
        "risk",
        "reduced",
        "increased",
        "decreased",
        "lower",
        "higher",
        "effect",
        "outcome",
        "mortality",
        "conclusion",
        "conclusions",
        "results",
        "suggest",
        "showed",
        "found",
        "evidence",
        "recommend",
        "guidance",
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


def _terms(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", str(text))


_LOWERCASE_EVIDENCE_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "just",
    "more",
    "not",
    "of",
    "on",
    "or",
    "than",
    "that",
    "the",
    "through",
    "to",
    "with",
    "without",
}
