from __future__ import annotations

import json
from typing import Any


def build_decision_synthesis_contract(reader_packet: dict[str, Any]) -> dict[str, Any]:
    support_cards = _cards(reader_packet, "evidence_cards")
    counter_cards = _cards(reader_packet, "counterweight_cards")
    crux_cards = _cards(reader_packet, "decision_cruxes")
    quantity_cards = _cards(reader_packet, "quantitative_anchors")
    return {
        "schema_id": "decision_synthesis_contract_v1",
        "decision_question": reader_packet.get("decision_question"),
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
        "source_bottom_lines_to_integrate": [_contract_card(card) for card in _source_bottom_line_cards(support_cards + counter_cards)[:12]],
        "strongest_support_to_weigh": [_contract_card(card) for card in support_cards[:6]],
        "strongest_counterweights_to_weigh": [_contract_card(card) for card in counter_cards[:6]],
        "quantitative_anchors_to_interpret": [_contract_card(card) for card in quantity_cards[:6]],
        "cruxes_to_resolve_or_name": [_contract_card(card) for card in crux_cards[:6]],
    }


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


def build_reader_facing_packet_synthesis_prompt(reader_packet: dict[str, Any]) -> str:
    return (
        "You are a senior decision analyst writing for a thoughtful human decision-maker.\n"
        "Write a polished, decision-ready briefing memo from the reader-facing evidence packet below.\n"
        "The packet includes a decision_synthesis_contract. Use that contract as the writing plan.\n\n"
        "Core objective:\n"
        "- Do not merely summarize or list evidence. Produce a decision read: default stance, why it is supported, strongest counterweight, scope/conditions, and practical implication.\n\n"
        "Rules:\n"
        "- Answer the decision question directly in the first paragraph.\n"
        "- Preserve load-bearing numbers, uncertainty, exceptions, and source labels.\n"
        "- Treat `must_retain_obligations` and evidence cards marked `required_in_memo` as mandatory content unless a packet warning says the evidence is unsafe to use.\n"
        "- Use `synthesis_warnings` to bound confidence and avoid overclaiming; do not name the warning machinery.\n"
        "- Every evidence paragraph or bullet must include bracketed source labels copied from the packet's `source` fields.\n"
        "- Include the exact decision question near the top of the memo.\n"
        "- Do not add facts, sources, populations, causal interpretations, or recommendations beyond the packet.\n"
        "- Do not mention packet schema, IDs, validation, repair reports, or internal pipeline status.\n"
        "- Write like an analyst making a decision legible, not like a checklist renderer.\n\n"
        "Memo shape:\n"
        "## Decision Brief\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change the Answer\n"
        "## Decision-Relevant Evidence\n"
        "## Sources\n\n"
        "Reader-facing evidence packet:\n"
        f"{json.dumps(reader_packet, indent=2, ensure_ascii=False)}\n"
    )


def _cards(reader_packet: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = reader_packet.get(key)
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _source_bottom_line_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [card for card in cards if "source-level bottom line" in str(card.get("interpretation") or "").lower()]


def _contract_card(card: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "source": card.get("source"),
            "role": card.get("role"),
            "statement": card.get("statement"),
            "quantities": card.get("quantities", [])[:4] if isinstance(card.get("quantities"), list) else [],
            "interpretation": card.get("interpretation"),
            "required_in_memo": card.get("required_in_memo"),
        }
    )


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
