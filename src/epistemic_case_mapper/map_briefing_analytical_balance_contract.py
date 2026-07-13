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
    required_cards = [
        card
        for role, cards in role_cards.items()
        for index, card in enumerate(cards)
        if _requires_balance(card, role=role, role_index=index)
    ]
    warnings = [
        *(["no_support_cards"] if not role_cards.get("strongest_support") and not role_cards.get("quantitative_anchor") else []),
        *(["no_counterweight_cards"] if _items_for_role(items, "strongest_counterweight") and not role_cards.get("strongest_counterweight") else []),
    ]
    return {
        "schema_id": "analytical_balance_contract_v1",
        "method": "deterministic_projection_from_existing_packet_roles_and_ranks",
        "decision_question": packet.get("decision_question"),
        "answer_to_state": _answer_to_state(packet),
        "balance_tasks": _balance_tasks(),
        "support_cards": [*role_cards.get("strongest_support", []), *role_cards.get("quantitative_anchor", [])],
        "counterweight_cards": role_cards.get("strongest_counterweight", []),
        "scope_boundary_cards": role_cards.get("scope_boundary", []),
        "decision_crux_cards": role_cards.get("decision_crux", []),
        "required_balance_cards": required_cards,
        "quantity_calibration": _quantity_calibration(items),
        "evidence_type_contrasts": _evidence_type_contrasts(items),
        "summary": {
            "support_count": len(role_cards.get("strongest_support", [])),
            "counterweight_count": len(role_cards.get("strongest_counterweight", [])),
            "scope_boundary_count": len(role_cards.get("scope_boundary", [])),
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


def _items_for_role(items: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    if role == "quantitative_anchor":
        return [item for item in items if _list(item.get("quantities")) and str(item.get("role") or "") != "strongest_support"]
    return [item for item in items if str(item.get("role") or "") == role]


def _contract_item_eligible(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    return bool(item.get("must_use")) or str(item.get("obligation_level") or "") in {"must_include", "should_include"}


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
    if role == "decision_crux":
        return role_index < 2 and rank <= 35
    return role in {"strongest_support", "quantitative_anchor"} and role_index == 0 and rank <= 10


def _writing_job(role: str) -> str:
    if role == "strongest_counterweight":
        return "Weigh this against the default answer and state whether it overturns, weakens, bounds, or contextualizes that answer."
    if role == "scope_boundary":
        return "Use this to state where the answer applies, does not apply, or needs qualification."
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
                "writing_job": "Explain what this evidence type can establish for the decision and what it cannot establish.",
                "example_item_id": item.get("item_id"),
                "source_labels": _source_labels(item),
            }
        )
    return rows[:6]


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
    pattern = r"\b(?:RR|HR|OR|risk ratio|hazard ratio|relative risk)?\s*\d+(?:\.\d+)?\s*(?:%|mg/dL|mmol/l|mmol/L)?\b"
    return _dedupe(match.strip() for match in re.findall(pattern, str(text), flags=re.IGNORECASE) if match.strip())[:6]


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
