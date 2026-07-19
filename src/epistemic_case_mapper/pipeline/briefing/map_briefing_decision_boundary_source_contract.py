from __future__ import annotations

from collections import Counter
import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_claim_calibration import calibrate_claim_for_writer, calibrate_text_for_writer
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


BOUNDARY_ROLES = {"scope_boundary", "strongest_counterweight", "decision_crux"}
PRIMARY_QUANTITY_ROLES = {"decision_anchor", "supporting_detail"}


def build_decision_boundary_source_contract(
    packet: dict[str, Any],
    visible_items: list[dict[str, Any]],
    *,
    selected_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    packet = packet if isinstance(packet, dict) else {}
    visible = [item for item in visible_items if isinstance(item, dict)]
    context = [item for item in (selected_context or []) if isinstance(item, dict)]
    boundary_obligations = _boundary_obligations(packet, visible, context)
    source_use_cards = _source_use_cards(visible, context)
    quantity_priority_cards = _quantity_priority_cards(visible, context)
    language_discipline = _language_discipline(visible, context)
    warnings = [
        *(["no_boundary_obligations"] if not boundary_obligations else []),
        *(["no_source_use_cards"] if not source_use_cards else []),
        *(["no_quantity_priority_cards"] if _has_quantities(visible) and not quantity_priority_cards else []),
    ]
    return {
        "schema_id": "decision_boundary_source_contract_v1",
        "method": "compiled_from_existing_writer_packet_judgments",
        "decision_question": packet.get("decision_question"),
        "status": "ready" if not warnings else "warning",
        "boundary_obligations": boundary_obligations,
        "source_use_cards": source_use_cards,
        "quantity_priority_cards": quantity_priority_cards,
        "language_discipline": language_discipline,
        "summary": {
            "boundary_count": len(boundary_obligations),
            "source_card_count": len(source_use_cards),
            "quantity_priority_count": len(quantity_priority_cards),
            "language_discipline_count": len(language_discipline),
        },
        "warnings": warnings,
    }


def _boundary_obligations(
    packet: dict[str, Any],
    visible_items: list[dict[str, Any]],
    selected_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _sorted_items([*visible_items, *selected_context]):
        if not _is_boundary_item(item):
            continue
        rows.append(
            {
                "boundary_id": f"boundary_{len(rows) + 1:03d}",
                "boundary_type": _boundary_type(item),
                "writing_job": _boundary_writing_job(item),
                "statement": _short_text(_calibrated_claim(item), 420),
                "source_labels": _source_labels(item),
                "quantities": _quantity_values(item),
                "evidence_item_ids": _evidence_item_ids(item),
                "obligation_level": item.get("obligation_level"),
                "answer_relation": str(item.get("answer_relation") or "").strip(),
            }
        )
    for statement in _model_boundary_statements(packet):
        rows.append(
            {
                "boundary_id": f"boundary_{len(rows) + 1:03d}",
                "boundary_type": "model_supplied_boundary",
                "writing_job": "Use this to bound the answer if it is not already covered by source-linked boundary evidence.",
                "statement": _short_text(calibrate_text_for_writer(statement), 420),
                "source_labels": [],
                "quantities": [],
                "evidence_item_ids": [],
                "obligation_level": "guidance",
                "answer_relation": "bounds_scope",
            }
        )
    for statement in _missing_evidence_statements(packet):
        rows.append(
            {
                "boundary_id": f"boundary_{len(rows) + 1:03d}",
                "boundary_type": "missing_evidence_boundary",
                "writing_job": "Use this only to explain uncertainty or what evidence would change the answer.",
                "statement": _short_text(calibrate_text_for_writer(statement), 420),
                "source_labels": [],
                "quantities": [],
                "evidence_item_ids": [],
                "obligation_level": "guidance",
                "answer_relation": "uncertain_relation",
            }
        )
    return _dedupe_boundaries(rows)[:12]


def _source_use_cards(visible_items: list[dict[str, Any]], selected_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_label: dict[str, list[dict[str, Any]]] = {}
    for item in _sorted_items([*visible_items, *selected_context]):
        labels = _source_labels(item)
        for label in labels:
            by_label.setdefault(label, []).append(item)
    cards = []
    for label, items in sorted(by_label.items()):
        cards.append(
            {
                "source_label": label,
                "use_for": _source_use_roles(items),
                "key_claims": [_short_text(_calibrated_claim(item), 260) for item in items[:3]],
                "key_quantities": _source_quantities(items),
                "wording_cautions": _source_wording_cautions(items),
                "evidence_item_ids": _dedupe([evidence_id for item in items for evidence_id in _evidence_item_ids(item)])[:12],
            }
        )
    return cards[:16]


def _quantity_priority_cards(visible_items: list[dict[str, Any]], selected_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for item in _sorted_items([*visible_items, *selected_context]):
        for quantity in _list(item.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if not value:
                continue
            key = (value.lower(), tuple(_source_labels(quantity) or _source_labels(item)))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "quantity": value,
                    "quantity_kind": _quantity_kind(value, str(quantity.get("interpretation") or "")),
                    "priority": _quantity_priority(item, quantity),
                    "interpretation": _short_text(calibrate_text_for_writer(str(quantity.get("interpretation") or ""), item), 300),
                    "source_labels": _source_labels(quantity) or _source_labels(item),
                    "evidence_item_id": item.get("item_id"),
                    "quantity_role": str(quantity.get("quantity_role") or "").strip(),
                    "item_role": str(item.get("role") or "").strip(),
                }
            )
    return sorted(rows, key=_quantity_sort_key)[:16]


def _language_discipline(visible_items: list[dict[str, Any]], selected_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in _sorted_items([*visible_items, *selected_context]):
        cautions = _source_wording_cautions([item])
        if not cautions:
            continue
        rows.append(
            {
                "target": item.get("item_id"),
                "source_labels": _source_labels(item),
                "claim": _short_text(_calibrated_claim(item), 240),
                "wording_cautions": cautions,
            }
        )
    return rows[:10]


def _is_boundary_item(item: dict[str, Any]) -> bool:
    role = str(item.get("role") or "").strip()
    memo_function = str(item.get("memo_function") or "").strip()
    relation = str(item.get("answer_relation") or "").strip()
    return role in BOUNDARY_ROLES or memo_function in {"counterweight", "scope_boundary", "crux"} or relation in {
        "challenges_answer",
        "bounds_scope",
        "identifies_crux",
    }


def _boundary_type(item: dict[str, Any]) -> str:
    role = str(item.get("role") or "").strip()
    relation = str(item.get("answer_relation") or "").strip()
    if role == "strongest_counterweight" or relation == "challenges_answer":
        return "counterweight_boundary"
    if role == "decision_crux" or relation == "identifies_crux":
        return "decision_crux_boundary"
    return "scope_or_applicability_boundary"


def _boundary_writing_job(item: dict[str, Any]) -> str:
    boundary_type = _boundary_type(item)
    if boundary_type == "counterweight_boundary":
        return "Explain whether this weakens, bounds, or could change the default answer."
    if boundary_type == "decision_crux_boundary":
        return "Name why this distinction or uncertainty could change the decision read."
    return "State where the answer applies, does not apply, or needs qualification."


def _model_boundary_statements(packet: dict[str, Any]) -> list[str]:
    logic = _dict(packet.get("analyst_decision_logic"))
    return _dedupe(
        [
            *_string_list(logic.get("scope_boundaries")),
            *_string_list(logic.get("reconciled_cruxes")),
        ]
    )[:8]


def _missing_evidence_statements(packet: dict[str, Any]) -> list[str]:
    writer_packet = _dict(packet.get("writer_packet"))
    return _string_list(writer_packet.get("missing_evidence"))[:4]


def _dedupe_boundaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for row in rows:
        key = " ".join(str(row.get("statement") or "").lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _calibrated_claim(item: dict[str, Any]) -> str:
    return str(
        calibrate_claim_for_writer(str(item.get("reader_claim") or item.get("claim") or ""), item).get("claim")
        or ""
    ).strip()


def _source_use_roles(items: list[dict[str, Any]]) -> list[str]:
    roles = []
    for item in items:
        roles.append(str(item.get("memo_function") or item.get("role") or "").strip())
    return _dedupe([role for role in roles if role])


def _source_quantities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for item in items:
        for quantity in _list(item.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if not value or value.lower() in seen:
                continue
            seen.add(value.lower())
            rows.append(
                {
                    "value": value,
                    "interpretation": _short_text(calibrate_text_for_writer(str(quantity.get("interpretation") or ""), item), 240),
                    "quantity_role": str(quantity.get("quantity_role") or "").strip(),
                }
            )
    return rows[:6]


def _source_wording_cautions(items: list[dict[str, Any]]) -> list[str]:
    cautions = []
    for item in items:
        appraisal = _dict(item.get("source_appraisal"))
        wording = _dict(item.get("allowed_wording") or appraisal.get("allowed_wording"))
        if wording.get("causal_language_allowed") is False:
            cautions.append("Use association or observed-effect wording unless another source in the packet supports causal language.")
        cautions.extend(_string_list(wording.get("must_qualify_with"))[:3])
        cautions.extend(_string_list(item.get("source_use_warnings") or appraisal.get("source_use_warnings"))[:3])
        cautions.extend(_string_list(appraisal.get("interpretation_caveats"))[:2])
    return _dedupe([_short_text(caution, 220) for caution in cautions if caution])[:6]


def _quantity_priority(item: dict[str, Any], quantity: dict[str, Any]) -> str:
    role = str(item.get("role") or "").strip()
    quantity_role = str(quantity.get("quantity_role") or "").strip()
    if role in {"strongest_support", "strongest_counterweight", "quantitative_anchor"} and (
        not quantity_role or quantity_role in PRIMARY_QUANTITY_ROLES
    ):
        return "primary_decision_anchor"
    if role in BOUNDARY_ROLES:
        return "boundary_or_counterweight_anchor"
    if quantity_role in PRIMARY_QUANTITY_ROLES:
        return "supporting_anchor"
    return "context_quantity"


def _quantity_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    priority = {
        "primary_decision_anchor": 0,
        "boundary_or_counterweight_anchor": 1,
        "supporting_anchor": 2,
        "context_quantity": 3,
    }
    return (
        priority.get(str(row.get("priority") or ""), 4),
        _quantity_kind_rank(str(row.get("quantity_kind") or "")),
        str(row.get("source_labels") or ""),
        str(row.get("quantity") or ""),
    )


def _quantity_kind(value: str, interpretation: str) -> str:
    text = f"{value} {interpretation}".lower()
    if "confidence interval" in text or re.search(r"\bci\b", text):
        return "uncertainty_interval"
    if re.search(r"\b(hr|rr|or)\b", text) or any(
        phrase in text
        for phrase in (
            "relative risk",
            "hazard ratio",
            "odds ratio",
            "risk ratio",
            "risk difference",
            "mean difference",
        )
    ):
        return "effect_estimate"
    if any(marker in text for marker in ("/day", "per day", "/week", "per week", "threshold", "baseline", "dose")):
        return "dose_or_context_boundary"
    return "context_quantity"


def _quantity_kind_rank(kind: str) -> int:
    return {
        "effect_estimate": 0,
        "uncertainty_interval": 1,
        "dose_or_context_boundary": 2,
        "context_quantity": 3,
    }.get(kind, 4)


def _sorted_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [item for item in items if isinstance(item, dict)],
        key=lambda item: (_importance_rank(item), str(item.get("item_id") or "")),
    )


def _importance_rank(item: dict[str, Any]) -> int:
    try:
        return int(item.get("importance_rank") or 100)
    except (TypeError, ValueError):
        return 100


def _quantity_values(values: Any) -> list[str]:
    rows = []
    for quantity in _list(values):
        if isinstance(quantity, dict):
            value = str(quantity.get("value") or "").strip()
            if value:
                rows.append(value)
        elif str(quantity or "").strip():
            rows.append(str(quantity).strip())
    return _dedupe(rows)


def _source_labels(item: dict[str, Any]) -> list[str]:
    return _string_list(item.get("source_labels")) or _string_list(item.get("source_label"))


def _evidence_item_ids(item: dict[str, Any]) -> list[str]:
    return _string_list(_dict(item.get("lineage")).get("covered_evidence_item_ids")) or _string_list(item.get("item_id"))


def _has_quantities(items: list[dict[str, Any]]) -> bool:
    return any(_list(item.get("quantities")) for item in items if isinstance(item, dict))


def contract_quality_summary(contract: dict[str, Any]) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
    source_roles = Counter(
        role
        for card in _list(contract.get("source_use_cards"))
        if isinstance(card, dict)
        for role in _string_list(card.get("use_for"))
    )
    return {
        "schema_id": "decision_boundary_source_contract_quality_v1",
        "status": contract.get("status", "missing"),
        "boundary_count": len(_list(contract.get("boundary_obligations"))),
        "source_card_count": len(_list(contract.get("source_use_cards"))),
        "quantity_priority_count": len(_list(contract.get("quantity_priority_cards"))),
        "source_role_counts": dict(source_roles),
        "warnings": _string_list(contract.get("warnings")),
    }
