from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


ROLE_LIMITS = {
    "strongest_support": 3,
    "quantitative_anchor": 2,
    "strongest_counterweight": 3,
    "scope_boundary": 3,
    "decision_crux": 2,
}


def build_analytical_balance_contract(packet: dict[str, Any]) -> dict[str, Any]:
    packet = packet if isinstance(packet, dict) else {}
    items = _sorted_items([item for item in _list(packet.get("evidence_items")) if _contract_item_eligible(item)])
    role_cards = {
        role: [_balance_card(item, role=role) for item in _items_for_role(items, role)[:limit]]
        for role, limit in ROLE_LIMITS.items()
    }
    subgroup_cards = [_balance_card(item, role="subgroup_boundary") for item in _subgroup_boundary_items(items)[:3]]
    required_cards = _dedupe_cards([
        card
        for role, cards in role_cards.items()
        for index, card in enumerate(cards)
        if _requires_balance(card, role=role, role_index=index)
    ] + [card for index, card in enumerate(subgroup_cards) if _requires_balance(card, role="subgroup_boundary", role_index=index)])
    warnings = [
        *(["no_support_cards"] if not role_cards.get("strongest_support") and not role_cards.get("quantitative_anchor") else []),
        *(["no_counterweight_cards"] if _items_for_role(items, "strongest_counterweight") and not role_cards.get("strongest_counterweight") else []),
    ]
    return {
        "schema_id": "analytical_balance_contract_v1",
        "method": "deterministic_projection_from_existing_packet_roles_and_ranks",
        "decision_question": packet.get("decision_question"),
        "answer_to_state": _answer_to_state(packet),
        "answer_classification": _answer_classification(packet),
        "balance_tasks": _balance_tasks(),
        "support_cards": [*role_cards.get("strongest_support", []), *role_cards.get("quantitative_anchor", [])],
        "counterweight_cards": role_cards.get("strongest_counterweight", []),
        "scope_boundary_cards": role_cards.get("scope_boundary", []),
        "subgroup_boundary_cards": subgroup_cards,
        "decision_crux_cards": role_cards.get("decision_crux", []),
        "required_balance_cards": required_cards,
        "quantity_calibration": _quantity_calibration(items),
        "scope_dose_guardrails": _scope_dose_guardrails(items),
        "targeted_quantity_requirements": _targeted_quantity_requirements(items),
        "causal_language_discipline": _causal_language_discipline(items),
        "evidence_type_contrasts": _evidence_type_contrasts(items),
        "summary": {
            "support_count": len(role_cards.get("strongest_support", [])),
            "counterweight_count": len(role_cards.get("strongest_counterweight", [])),
            "scope_boundary_count": len(role_cards.get("scope_boundary", [])),
            "subgroup_boundary_count": len(subgroup_cards),
            "decision_crux_count": len(role_cards.get("decision_crux", [])),
            "required_balance_count": len(required_cards),
        },
        "status": "ready" if not warnings else "warning",
        "warnings": warnings,
    }


def required_analytical_balance_cards(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return _list(build_analytical_balance_contract(packet).get("required_balance_cards"))


def _balance_tasks() -> list[dict[str, str]]:
    return [
        {
            "task": "state_bounded_answer",
            "writing_job": "State the answer classification or action stance the evidence supports, with its scope and confidence.",
        },
        {
            "task": "weigh_main_support",
            "writing_job": "Explain the strongest support as a reason for the answer, not as a source list.",
        },
        {
            "task": "weigh_counterweights",
            "writing_job": "For each required counterweight, explain whether it overturns, weakens, bounds, or contextualizes the answer.",
        },
        {
            "task": "bound_scope",
            "writing_job": "Name the population, setting, option, time horizon, dose, or applicability limits supplied by the packet.",
        },
        {
            "task": "calibrate_quantities",
            "writing_job": "Use decision-relevant quantities to calibrate magnitude, uncertainty, thresholds, and subgroup limits.",
        },
        {
            "task": "separate_evidence_types",
            "writing_job": "When evidence types answer different subquestions, say what each type can and cannot establish.",
        },
    ]


def _answer_to_state(packet: dict[str, Any]) -> str:
    spine = _dict(packet.get("answer_spine"))
    logic = _dict(packet.get("analyst_decision_logic"))
    for value in (spine.get("default_read"), spine.get("bounded_answer"), logic.get("bounded_bottom_line")):
        text = _short_text(str(value or "").strip(), 520)
        if text:
            return text
    return ""


def _answer_classification(packet: dict[str, Any]) -> dict[str, Any]:
    question = str(packet.get("decision_question") or "").strip()
    answer_state = _answer_to_state(packet)
    options = _question_options(question)
    return {
        "decision_question": question,
        "current_answer_state": answer_state,
        "question_options": options,
        "answer_shape": _answer_shape(answer_state),
        "writing_job": (
            "Open by answering the decision question directly. "
            "If the question offers named options, state which option the evidence supports and which options it does not support at the stated scope."
            if options
            else "Open by stating the decision stance the evidence supports, its scope, and the main uncertainty."
        ),
    }


def _question_options(question: str) -> list[str]:
    if " or " not in question.lower() and "," not in question:
        return []
    clause = question.strip().rstrip("?")
    for marker in (" whether ", " as ", " be ", " is ", " are "):
        if marker in clause.lower():
            parts = re.split(re.escape(marker), clause, flags=re.IGNORECASE)
            clause = parts[-1]
    clause = re.split(r"\b(?:for|when|among|given|under|if|in)\b", clause, maxsplit=1, flags=re.IGNORECASE)[0]
    words = re.findall(r"[A-Za-z][A-Za-z-]{2,}", clause.lower())
    stop = {
        "clearly",
        "decision",
        "especially",
        "main",
        "materially",
        "meaningfully",
        "outcome",
        "option",
        "should",
        "substantially",
        "treat",
        "treated",
        "whether",
    }
    return _dedupe(word for word in words if word not in stop)[:5]


def _answer_shape(answer_state: str) -> str:
    text = str(answer_state or "").lower()
    if re.search(r"\b(no|not|without|does not|did not)\b.{0,50}\b(harm|risk|increase|worse|failure|concern)", text):
        return "bounded_neutral_or_no_clear_harm"
    if any(phrase in text for phrase in ("neutral", "no clear", "not associated", "insufficient evidence of harm")):
        return "bounded_neutral_or_no_clear_harm"
    if any(term in text for term in ("support", "favorable", "benefit", "adopt", "recommend")):
        return "bounded_support"
    if any(term in text for term in ("harm", "risk", "increase", "unfavorable", "avoid", "do not")):
        return "bounded_concern"
    if any(term in text for term in ("uncertain", "mixed", "inconclusive")):
        return "bounded_uncertain"
    return "answer_shape_unspecified"


def _items_for_role(items: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    if role == "quantitative_anchor":
        return [item for item in items if _list(item.get("quantities")) and str(item.get("role") or "") != "strongest_support"]
    return [item for item in items if str(item.get("role") or "") == role]


def _contract_item_eligible(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    return bool(item.get("must_use")) or str(item.get("obligation_level") or "") in {"must_include", "should_include"}


def _subgroup_boundary_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        text = " ".join(
            [
                str(item.get("reader_claim") or item.get("claim") or ""),
                str(item.get("decision_relevance") or item.get("include_reason") or ""),
                str(item.get("memo_function") or ""),
                str(item.get("source_memo_role") or ""),
            ]
        )
        role = str(item.get("role") or "")
        if role in {"scope_boundary", "decision_crux", "strongest_counterweight"} and _has_boundary_indicator(text):
            rows.append(item)
    return rows


def _has_boundary_indicator(text: str) -> bool:
    return bool(
        re.search(
            r"\b(subgroup|population|participants|people|users|sites|setting|context|boundary|applies|applicability|exception|"
            r"high-risk|low-risk|prior|history|baseline|eligibility|included|excluded)\b",
            str(text),
            flags=re.IGNORECASE,
        )
    )


def _balance_card(item: dict[str, Any], *, role: str) -> dict[str, Any]:
    statement = str(item.get("reader_claim") or item.get("claim") or "").strip()
    relevance = str(item.get("decision_relevance") or item.get("include_reason") or "").strip()
    return {
        "card_id": f"balance_{str(item.get('item_id') or role)}",
        "role": role,
        "answer_relation": str(item.get("answer_relation") or "").strip(),
        "memo_function": str(item.get("memo_function") or "").strip(),
        "source_memo_role": str(item.get("source_memo_role") or "").strip(),
        "importance_rank": _importance_rank(item),
        "obligation_level": str(item.get("obligation_level") or "").strip(),
        "must_use": bool(item.get("must_use")),
        "statement": _short_text(statement, 360),
        "decision_relevance": _short_text(relevance, 300),
        "source_labels": _source_labels(item),
        "quantities": _quantity_values(item),
        "surface_numbers": _surface_numbers(" ".join([statement, relevance])),
        "evidence_item_ids": _evidence_item_ids(item),
        "validation_terms": _validation_terms(statement, relevance, role),
        "writing_job": _writing_job(role),
    }


def _requires_balance(card: dict[str, Any], *, role: str, role_index: int) -> bool:
    if card.get("must_use"):
        return False
    if str(card.get("obligation_level") or "") != "should_include":
        return False
    rank = int(card.get("importance_rank") or 100)
    if role == "strongest_counterweight":
        return role_index < 3 or rank <= 18 or bool(card.get("surface_numbers"))
    if role == "scope_boundary":
        return role_index < 2 and rank <= 45
    if role == "subgroup_boundary":
        return role_index < 2 and rank <= 45
    if role == "decision_crux":
        return role_index < 2 and rank <= 35
    return role in {"strongest_support", "quantitative_anchor"} and role_index == 0 and rank <= 10


def _writing_job(role: str) -> str:
    if role == "strongest_counterweight":
        return "Weigh this against the default answer and state whether it overturns, weakens, bounds, or contextualizes that answer."
    if role == "scope_boundary":
        return "Use this to state where the answer applies, does not apply, or needs qualification."
    if role == "subgroup_boundary":
        return "Use this to name the subgroup, population, setting, or applicability boundary that changes how the answer should be used."
    if role == "decision_crux":
        return "Use this to name a distinction or uncertainty that could change the decision read."
    if role == "quantitative_anchor":
        return "Use this quantity-bearing evidence to calibrate magnitude or uncertainty."
    return "Use this as load-bearing support for the default answer."


def _quantity_calibration(items: list[dict[str, Any]]) -> dict[str, Any]:
    support = _quantity_cards(items, roles={"strongest_support", "quantitative_anchor"})[:4]
    counter = _quantity_cards(items, roles={"strongest_counterweight"})[:4]
    boundary = _quantity_cards(items, roles={"scope_boundary", "decision_crux"})[:4]
    return {
        "support_quantities": support,
        "counterweight_quantities": counter,
        "boundary_quantities": boundary,
        "writing_job": "Use support, counterweight, and boundary quantities to calibrate the answer instead of only citing point estimates.",
    }


def _scope_dose_guardrails(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for item in items:
        text = " ".join(
            [
                str(item.get("reader_claim") or item.get("claim") or ""),
                str(item.get("decision_relevance") or item.get("include_reason") or ""),
                " ".join(_quantity_values(item)),
            ]
        )
        for value in _dose_scope_phrases(text):
            key = (value.lower(), str(item.get("item_id") or ""))
            if key in seen:
                continue
            seen.add(key)
            scope_use = "study_or_context_specific" if _is_context_specific_quantity(text, item) else "candidate_decision_scope"
            rows.append(
                {
                    "value": value,
                    "scope_use": scope_use,
                    "role": item.get("role"),
                    "evidence_item_id": item.get("item_id"),
                    "source_labels": _source_labels(item),
                    "writing_job": (
                        "Use this as context for the source, subgroup, setting, or study design; do not turn it into a broad recommendation unless the answer scope separately supports that."
                        if scope_use == "study_or_context_specific"
                        else "Use this as a candidate scope or dose boundary only if it matches the decision question and the answer frame."
                    ),
                }
            )
    return rows[:8]


def _targeted_quantity_requirements(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        role = str(item.get("role") or "")
        requirement_type = _quantity_requirement_type(item)
        if not requirement_type:
            continue
        for value in _decision_quantity_values(item):
            rows.append(
                {
                    "requirement_type": requirement_type,
                    "value": value,
                    "role": role,
                    "evidence_item_id": item.get("item_id"),
                    "source_labels": _source_labels(item),
                    "writing_job": _quantity_writing_job(requirement_type),
                }
            )
            break
    return rows[:10]


def _quantity_requirement_type(item: dict[str, Any]) -> str:
    role = str(item.get("role") or "")
    text = _item_text(item)
    if _has_uncertainty_quantity(text):
        return "uncertainty_or_interval"
    if role in {"strongest_counterweight"}:
        return "counterweight_magnitude"
    if role in {"scope_boundary", "decision_crux"}:
        return "boundary_or_scope_quantity"
    if role in {"strongest_support", "quantitative_anchor"}:
        return "support_effect_or_magnitude"
    return ""


def _quantity_writing_job(requirement_type: str) -> str:
    return {
        "support_effect_or_magnitude": "Use this quantity to state how large the main support is and why that magnitude matters.",
        "counterweight_magnitude": "Use this quantity to state how large the counterweight is and whether it changes the decision read.",
        "boundary_or_scope_quantity": "Use this quantity to define the boundary, subgroup, threshold, setting, or time horizon.",
        "uncertainty_or_interval": "Keep this uncertainty quantity attached to the estimate it qualifies.",
    }.get(requirement_type, "Use this quantity only if it changes the decision read.")


def _causal_language_discipline(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        text = _item_text(item)
        if not _has_causal_language(text):
            continue
        appraisal = _dict(item.get("source_appraisal"))
        rows.append(
            {
                "evidence_item_id": item.get("item_id"),
                "role": item.get("role"),
                "causal_language_risk": _short_text(_causal_phrase(text), 140),
                "evidence_context": _short_text(
                    " ".join([*(_string_list(appraisal.get("evidence_proximity"))), str(appraisal.get("decision_directness") or "")]),
                    220,
                ),
                "source_labels": _source_labels(item),
                "writing_job": "Use causal wording only when the source appraisal supports it; otherwise phrase this as association, explanation, mediation, consistency, or a hypothesis.",
            }
        )
    return rows[:6]


def _quantity_cards(items: list[dict[str, Any]], *, roles: set[str]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for item in items:
        if str(item.get("role") or "") not in roles:
            continue
        for quantity in _list(item.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if not value:
                continue
            key = (value.lower(), str(item.get("item_id") or ""))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "value": value,
                    "interpretation": _short_text(str(quantity.get("interpretation") or ""), 220),
                    "evidence_item_id": item.get("item_id"),
                    "role": item.get("role"),
                    "source_labels": _source_labels(quantity) or _source_labels(item),
                }
            )
    return rows


def _evidence_type_contrasts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for item in items:
        appraisal = _dict(item.get("source_appraisal"))
        proximity = _string_list(appraisal.get("evidence_proximity"))
        directness = str(appraisal.get("decision_directness") or "").strip()
        if not proximity and not directness:
            continue
        key = (tuple(proximity), directness)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "evidence_proximity": proximity[:4],
                "decision_directness": directness,
                "required_evidence_type_move": _evidence_type_move(proximity, directness),
                "writing_job": "Explain what this evidence type can establish for the decision, what it cannot establish, and how it should be weighed against other evidence types.",
                "example_item_id": item.get("item_id"),
                "source_labels": _source_labels(item),
            }
        )
    return rows[:6]


def _evidence_type_move(proximity: list[str], directness: str) -> str:
    text = " ".join([*proximity, directness]).lower()
    if any(term in text for term in ("proxy", "biomarker", "intermediate", "indirect")):
        return "separate_proxy_or_intermediate_outcomes_from_decision_endpoints"
    if any(term in text for term in ("observational", "association", "correlational")):
        return "calibrate_association_evidence_without_overstating_causality"
    if any(term in text for term in ("trial", "experiment", "random")):
        return "explain_internal_validity_and_scope_limits"
    return "state_what_the_evidence_type_can_and_cannot_establish"


def _sorted_items(items: list[Any]) -> list[dict[str, Any]]:
    return sorted(
        [item for item in items if isinstance(item, dict)],
        key=lambda item: (_importance_rank(item), str(item.get("item_id") or "")),
    )


def _importance_rank(item: dict[str, Any]) -> int:
    try:
        return int(item.get("importance_rank") or 100)
    except (TypeError, ValueError):
        return 100


def _source_labels(item: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(item.get("source_labels")), str(item.get("source_label") or "").strip()])


def _quantity_values(item: dict[str, Any]) -> list[str]:
    return _dedupe(str(quantity.get("value") or "").strip() for quantity in _list(item.get("quantities")) if isinstance(quantity, dict))[:6]


def _evidence_item_ids(item: dict[str, Any]) -> list[str]:
    ids = [str(item.get("item_id") or "").strip()]
    ids.extend(_string_list(_dict(item.get("lineage")).get("covered_evidence_item_ids")))
    return _dedupe(value for value in ids if value)[:12]


def _surface_numbers(text: str) -> list[str]:
    pattern = r"\b(?:RR|HR|OR|risk ratio|hazard ratio|relative risk|CI)?\s*\d+(?:\.\d+)?\s*(?:%|mg/dL|mmol/l|mmol/L)?\b"
    return _dedupe(match.strip() for match in re.findall(pattern, str(text), flags=re.IGNORECASE) if match.strip())[:6]


def _dose_scope_phrases(text: str) -> list[str]:
    patterns = [
        r"\b(?:up to\s+|about\s+|approximately\s+|~)?\d+(?:\.\d+)?\s*(?:[A-Za-z]+)?\s*(?:per|/)\s*(?:day|week|month|year)\b",
        r"\b(?:up to\s+|about\s+|approximately\s+|~)?\d+(?:\.\d+)?\s*(?:units|items|servings|doses|sessions|visits)\s*(?:daily|weekly|monthly|annually)\b",
        r"\b(?:up to\s+|about\s+|approximately\s+|~)?\d+(?:\.\d+)?\s*(?:daily|weekly|monthly|annually)\b",
        r"\b\d+(?:\.\d+)?\s*(?:units|items|servings|doses|sessions|visits|hours|days|weeks|months|years)\b",
    ]
    values = []
    for pattern in patterns:
        values.extend(match.strip() for match in re.findall(pattern, str(text), flags=re.IGNORECASE) if match.strip())
    return _dedupe(values)[:6]


def _decision_quantity_values(item: dict[str, Any]) -> list[str]:
    text = _item_text(item)
    values = [*_quantity_values(item), *_dose_scope_phrases(text)]
    values.extend(
        value
        for value in _surface_numbers(text)
        if re.search(r"\b(RR|HR|OR|risk ratio|hazard ratio|relative risk|CI)\b|%|mg/dL|mmol", value, flags=re.IGNORECASE)
    )
    return _dedupe(values)[:6]


def _item_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            str(item.get("reader_claim") or item.get("claim") or ""),
            str(item.get("decision_relevance") or item.get("include_reason") or ""),
            str(item.get("memo_function") or ""),
            str(item.get("source_memo_role") or ""),
        ]
    )


def _is_context_specific_quantity(text: str, item: dict[str, Any]) -> bool:
    role = str(item.get("role") or "")
    if role in {"scope_boundary", "decision_crux"}:
        return True
    return bool(
        re.search(
            r"\b(study|trial|cohort|sample|source|subgroup|population|setting|context|case|scenario|participants|over|during)\b",
            str(text),
            flags=re.IGNORECASE,
        )
    )


def _has_uncertainty_quantity(text: str) -> bool:
    return bool(re.search(r"\b(CI|confidence interval|credible interval|range|uncertainty|lower|upper)\b", str(text), flags=re.IGNORECASE))


def _has_causal_language(text: str) -> bool:
    return bool(
        re.search(
            r"\b(caus(?:e|es|ed|al|ing)|driven by|primary driver|drives|due to|leads to|results in|responsible for)\b",
            str(text),
            flags=re.IGNORECASE,
        )
    )


def _causal_phrase(text: str) -> str:
    match = re.search(
        r".{0,60}\b(caus(?:e|es|ed|al|ing)|driven by|primary driver|drives|due to|leads to|results in|responsible for)\b.{0,60}",
        str(text),
        flags=re.IGNORECASE,
    )
    return match.group(0).strip() if match else ""


def _dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for card in cards:
        key = str(card.get("card_id") or card.get("statement") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(card)
    return rows


def _validation_terms(statement: str, relevance: str, role: str) -> list[str]:
    terms = _content_terms(" ".join([statement, relevance]))
    role_terms = {
        "strongest_counterweight": ["counterweight", "risk", "concern", "limit"],
        "scope_boundary": ["scope", "boundary", "applies", "population", "context"],
        "decision_crux": ["crux", "distinction", "uncertainty", "change"],
    }.get(role, [])
    return _dedupe([*terms[:10], *role_terms])[:14]


def _content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "again",
        "against",
        "also",
        "because",
        "between",
        "could",
        "does",
        "from",
        "have",
        "into",
        "more",
        "should",
        "than",
        "that",
        "their",
        "there",
        "this",
        "with",
    }
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", str(text).lower())
    return _dedupe(word for word in words if word not in stop)
