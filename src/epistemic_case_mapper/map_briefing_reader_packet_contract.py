from __future__ import annotations

from typing import Any


def build_memo_ready_decision_synthesis_contract(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    items = _cards(memo_ready_packet, "evidence_items")
    support_cards = _memo_ready_cards(
        items,
        roles={"strongest_support", "quantitative_anchor", "mechanism_or_explanation"},
        must_use_first=True,
    )
    counter_cards = _memo_ready_cards(
        items,
        roles={"strongest_counterweight", "scope_boundary"},
        must_use_first=True,
    )
    crux_cards = _memo_ready_cards(items, roles={"decision_crux"}, must_use_first=True)
    quantity_cards = _memo_ready_cards(items, roles={"quantitative_anchor"}, must_use_first=True)
    return {
        "schema_id": "decision_synthesis_contract_v1",
        "decision_question": memo_ready_packet.get("decision_question"),
        "stance_task": "State the best-supported answer or action stance. If the answer is conditional or underdetermined, say so directly and name the default case.",
        "support_task": "Explain what evidence carries the default stance, not just which sources exist.",
        "counterweight_task": "Explain the strongest evidence that weakens, reverses, or narrows the stance.",
        "scope_task": "Separate the target case from subgroups, contexts, or assumptions where the answer changes.",
        "crux_task": "State the assumption or evidence update most likely to change the answer.",
        "decision_implication_task": "Translate the evidence state into decision support without overstating certainty.",
        "required_decision_moves": [
            "Open with a direct stance for the target decision question, including if the stance is conditional.",
            "State why the most important support does or does not outweigh the strongest counterweight.",
            "Name the conditions, subgroups, contexts, or assumptions that change the answer.",
            "Convert uncertainty into a practical implication for the decision-maker.",
            "Use source labels and load-bearing numbers while avoiding a checklist tone.",
        ],
        "answer_spine_to_use": memo_ready_packet.get("answer_spine"),
        "strongest_support_to_weigh": support_cards[:8],
        "strongest_counterweights_to_weigh": counter_cards[:8],
        "quantitative_anchors_to_interpret": quantity_cards[:8],
        "cruxes_to_resolve_or_name": crux_cards[:8],
    }


def _cards(reader_packet: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = reader_packet.get(key)
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _memo_ready_cards(
    items: list[dict[str, Any]],
    *,
    roles: set[str],
    must_use_first: bool,
) -> list[dict[str, Any]]:
    selected = [item for item in items if str(item.get("role") or "") in roles]
    if must_use_first:
        selected.sort(key=lambda item: (not bool(item.get("must_use")), -_diagnosticity_score(item)))
    return [_memo_ready_contract_card(item) for item in selected]


def _memo_ready_contract_card(item: dict[str, Any]) -> dict[str, Any]:
    quantities = item.get("quantity_tuples") or item.get("quantities") or []
    return _drop_empty(
        {
            "source": item.get("source_label"),
            "source_labels": item.get("source_labels"),
            "role": item.get("role"),
            "statement": item.get("reader_claim"),
            "quantities": quantities[:4] if isinstance(quantities, list) else [],
            "decision_relevance": item.get("decision_relevance"),
            "warrant": _nested(item, "argument", "warrant"),
            "caveat": item.get("caveat"),
            "required_in_memo": item.get("must_use"),
        }
    )


def _diagnosticity_score(item: dict[str, Any]) -> int:
    diagnosticity = item.get("diagnosticity")
    if not isinstance(diagnosticity, dict):
        return 0
    try:
        return int(diagnosticity.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def _nested(row: dict[str, Any], *keys: str) -> Any:
    current: Any = row
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}
