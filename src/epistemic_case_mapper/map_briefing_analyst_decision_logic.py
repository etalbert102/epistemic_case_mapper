from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


def analyst_decision_logic(
    refinement: dict[str, Any],
    answer_frame: dict[str, Any],
    groups: list[dict[str, Any]],
    warning_obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    refined = _dict(refinement.get("decision_logic"))
    if any(str(refined.get(key) or "").strip() for key in ("bounded_bottom_line", "support_summary", "counterweight_weighting")):
        return _normalize_decision_logic(refined, answer_frame)
    return _deterministic_decision_logic(answer_frame, groups, warning_obligations)


def _normalize_decision_logic(logic: dict[str, Any], answer_frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "analyst_decision_logic_v1",
        "bounded_bottom_line": _short_text(str(logic.get("bounded_bottom_line") or answer_frame.get("direct_answer") or ""), 520),
        "support_summary": _short_text(str(logic.get("support_summary") or answer_frame.get("why_this_read") or ""), 520),
        "strongest_counterweight": _short_text(str(logic.get("strongest_counterweight") or answer_frame.get("strongest_counterargument") or ""), 420),
        "counterweight_weighting": _short_text(str(logic.get("counterweight_weighting") or answer_frame.get("why_counterargument_does_or_does_not_change_answer") or ""), 520),
        "reconciled_cruxes": [_short_text(value, 280) for value in _string_list(logic.get("reconciled_cruxes"))[:6]],
        "scope_boundaries": [_short_text(value, 260) for value in _string_list(logic.get("scope_boundaries"))[:6]],
        "practical_implications": [_short_text(value, 260) for value in _string_list(logic.get("practical_implications"))[:6]],
        "do_not_overstate": _dedupe(
            [
                *[_short_text(value, 240) for value in _string_list(logic.get("do_not_overstate"))[:8]],
                *_string_list(answer_frame.get("must_not_overstate")),
            ]
        )[:8],
    }


def _deterministic_decision_logic(
    answer_frame: dict[str, Any],
    groups: list[dict[str, Any]],
    warning_obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    support = _first_group_text(groups, "load_bearing_primary_support")
    counter = _first_group_text(groups, "load_bearing_counterweight")
    scope = [
        _short_text(str(group.get("proposition") or ""), 260)
        for group in groups
        if group.get("memo_role") == "scope_or_applicability" and group.get("proposition")
    ][:4]
    cruxes = [
        _short_text(str(group.get("proposition") or ""), 280)
        for group in groups
        if group.get("memo_role") == "decision_crux" and group.get("proposition")
    ][:4]
    implications = [
        "State the practical implication that follows from the bounded bottom line.",
        "Treat counterweights and warning obligations as limits on scope, confidence, or implementation rather than orphan facts.",
    ]
    implications.extend(
        _short_text(str(row.get("obligation") or ""), 220)
        for row in warning_obligations
        if str(row.get("memo_action") or "") in {"incorporate_as_counterweight", "bound_scope_or_confidence"}
    )
    return {
        "schema_id": "analyst_decision_logic_v1",
        "bounded_bottom_line": _short_text(str(answer_frame.get("direct_answer") or ""), 520),
        "support_summary": support or _short_text(str(answer_frame.get("why_this_read") or ""), 520),
        "strongest_counterweight": counter or _short_text(str(answer_frame.get("strongest_counterargument") or ""), 420),
        "counterweight_weighting": _short_text(
            str(answer_frame.get("why_counterargument_does_or_does_not_change_answer") or "Explain whether the strongest counterweight changes the bottom line or only bounds it."),
            520,
        ),
        "reconciled_cruxes": cruxes,
        "scope_boundaries": scope,
        "practical_implications": _dedupe(implications)[:6],
        "do_not_overstate": _dedupe(
            [
                *_string_list(answer_frame.get("must_not_overstate")),
                "Do not imply the answer travels outside the stated population, dose, comparator, or evidence base.",
                "Do not treat a counterweight as decisive unless the packet explicitly says it changes the bottom line.",
            ]
        )[:8],
    }


def _first_group_text(groups: list[dict[str, Any]], memo_use: str) -> str:
    for group in groups:
        if group.get("memo_role") == memo_use and group.get("proposition"):
            return _short_text(str(group.get("proposition") or ""), 260)
    return ""
