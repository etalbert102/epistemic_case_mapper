from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_analytical_balance_contract import required_analytical_balance_cards
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_obligations import required_memo_obligations
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_identity import project_sources_to_ids_for_model


def protected_anchor_checklist(packet: dict[str, Any]) -> list[dict[str, Any]]:
    obligations = required_memo_obligations(packet)
    anchors = [_obligation_anchor(obligation) for obligation in obligations[:18]]
    if not anchors:
        anchors = [_mandatory_item_anchor(item) for item in _mandatory_items(packet)[:18]]
    anchors.extend(_balance_anchor(card) for card in required_analytical_balance_cards(packet)[:10])
    anchors.extend(_warning_anchor(warning) for warning in _list(_dict(packet.get("memo_warning_packet")).get("warnings"))[:6])
    checklist = [_drop_empty(anchor) for anchor in anchors if _drop_empty(anchor)]
    return project_sources_to_ids_for_model(checklist, _list(packet.get("source_trail")))


def _obligation_anchor(obligation: dict[str, Any]) -> dict[str, Any]:
    return {
        "anchor_type": "memo_obligation",
        "anchor_id": obligation.get("obligation_id"),
        "role": obligation.get("role"),
        "required_meaning": obligation.get("statement"),
        "source_labels": obligation.get("source_labels", []),
        "quantities": _quantity_values(obligation.get("quantities")),
    }


def _mandatory_item_anchor(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "anchor_type": "mandatory_evidence",
        "anchor_id": item.get("item_id"),
        "role": item.get("role"),
        "required_meaning": item.get("reader_claim"),
        "source_labels": _source_labels_for_prompt(item),
        "quantities": _quantity_values(item.get("quantities")),
    }


def _balance_anchor(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "anchor_type": "balance_card",
        "role": card.get("role"),
        "required_meaning": card.get("statement"),
        "decision_relevance": card.get("decision_relevance"),
        "source_labels": card.get("source_labels", []),
    }


def _warning_anchor(warning: dict[str, Any]) -> dict[str, Any]:
    return {
        "anchor_type": "warning",
        "required_meaning": warning.get("claim") or warning.get("warning") or warning.get("statement"),
        "source_labels": warning.get("source_labels", []),
    }


def _mandatory_items(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(packet.get("evidence_items")) if isinstance(item, dict) and item.get("must_use")]


def _quantity_values(quantities: Any) -> list[dict[str, str]]:
    rows = []
    for quantity in _list(quantities):
        if isinstance(quantity, dict):
            value = str(quantity.get("value") or "").strip()
            if value:
                rows.append(_drop_empty({"value": value, "interpretation": str(quantity.get("interpretation") or "").strip()}))
            continue
        value = str(quantity or "").strip()
        if value:
            rows.append({"value": value})
    return rows


def _source_labels_for_prompt(item: dict[str, Any]) -> list[str]:
    return _dedupe([str(item.get("source_label") or ""), *_string_list(item.get("source_labels"))])


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, []) and value != {}}
