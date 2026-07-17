from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def build_decision_action_contract(reader_packet: dict[str, Any]) -> dict[str, Any]:
    balanced = _dict(reader_packet.get("balanced_answer_frame"))
    bluf = _dict(reader_packet.get("bluf_contract"))
    usefulness = _dict(reader_packet.get("decision_usefulness"))
    stance = _dict(usefulness.get("recommended_stance"))
    trigger = _first_trigger(_list(usefulness.get("monitoring_triggers")))
    tradeoff = _first_tradeoff(_list(usefulness.get("tradeoffs")))
    return _drop_empty(
        {
            "default_action": _first_text(
                stance.get("stance"),
                balanced.get("practical_read"),
                bluf.get("practical_read"),
                balanced.get("best_current_read"),
                bluf.get("recommended_read"),
            ),
            "scope": _first_text(stance.get("scope"), bluf.get("who_it_applies_to"), balanced.get("scope")),
            "exception_handling": _first_text(bluf.get("main_exception_or_boundary"), balanced.get("main_counterweight")),
            "confidence": _first_text(stance.get("confidence"), balanced.get("confidence")),
            "tradeoff": tradeoff,
            "update_trigger": trigger,
            "what_not_to_say": _string_list(balanced.get("must_not_overstate"))[:4],
        }
    )


def _first_trigger(rows: list[Any]) -> str:
    for row in rows:
        item = _dict(row)
        text = _first_text(item.get("trigger"), item.get("would_update"))
        if text:
            return text
    return ""


def _first_tradeoff(rows: list[Any]) -> str:
    for row in rows:
        item = _dict(row)
        text = _first_text(item.get("tradeoff"), item.get("choose_a_if"), item.get("choose_b_if"))
        if text:
            return text
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
