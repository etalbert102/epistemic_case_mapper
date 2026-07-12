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


_NATURAL_LANGUAGE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        r"\bUse counterweights to bound the answer if they do not overturn the primary support\.?",
        "Counterweights limit confidence or scope when the support remains stronger.",
    ),
    (r"\bConnect this reasoning step to the weighted answer\.?", ""),
    (r"\bcrux\s+for\b", "relevant to"),
    (r"\bthe\s+primary\s+driver\b", "a plausible important driver"),
    (r"\bprimary\s+driver\b", "plausible important driver"),
    (r"\bconsistently\s+neutralized\b", "less decisive after adjustment"),
    (r"\bneutralized\b", "weakened"),
    (r"\bbyproduct\s+of\b", "partly explained by"),
    (r"\binherent\s+property\s+of\b", "effect specific to"),
    (r"\bfundamentally\s+changing\b", "shifting"),
)

_SCAFFOLDED_DECISION_LOGIC_PATTERNS = (
    "use counterweights to bound",
    "connect this reasoning step",
    "explain whether the strongest counterweight changes",
)


def analyst_decision_logic(
    refinement: dict[str, Any],
    answer_frame: dict[str, Any],
    groups: list[dict[str, Any]],
    warning_obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    refined = _dict(refinement.get("decision_logic"))
    if any(
        str(refined.get(key) or "").strip()
        for key in ("bounded_bottom_line", "support_summary", "counterweight_weighting")
    ):
        return _normalize_decision_logic(refined, answer_frame)
    return _deterministic_decision_logic(answer_frame, groups, warning_obligations)


def naturalize_decision_logic_payload(logic: dict[str, Any]) -> dict[str, Any]:
    result = dict(logic or {})
    for key in ("bounded_bottom_line", "support_summary", "strongest_counterweight", "counterweight_weighting"):
        if key in result:
            result[key] = naturalize_decision_logic_text(str(result.get(key) or ""))
    for key in ("reconciled_cruxes", "scope_boundaries", "practical_implications", "do_not_overstate"):
        if key in result:
            result[key] = [naturalize_decision_logic_text(value) for value in _string_list(result.get(key))]
    return result


def naturalize_decision_logic_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    for pattern, replacement in _NATURAL_LANGUAGE_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\ba plausible important driver\b", "a plausible important driver", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip()


def is_scaffolded_decision_logic_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return any(pattern in text for pattern in _SCAFFOLDED_DECISION_LOGIC_PATTERNS)


def content_based_counterweight_weighting(
    *,
    support: Any = "",
    counterweight: Any = "",
    fallback: Any = "",
) -> str:
    fallback_text = naturalize_decision_logic_text(str(fallback or ""))
    if fallback_text and not is_scaffolded_decision_logic_text(fallback_text):
        return _short_text(fallback_text, 520)
    support_text = naturalize_decision_logic_text(str(support or ""))
    counter_text = naturalize_decision_logic_text(str(counterweight or ""))
    if counter_text and support_text:
        return _short_text(
            f"The counterweight limits the support: {counter_text} The support remains: {support_text}",
            520,
        )
    if counter_text:
        return _short_text(f"The counterweight narrows confidence or scope: {counter_text}", 520)
    return ""


def argument_plan_transition(step_id: str) -> str:
    if step_id == "counterweight":
        return "Contrast this point with the support and state whether it changes the answer or narrows scope."
    if step_id == "scope":
        return "Use this to state where the answer applies."
    if step_id == "crux":
        return "Use this to name what would most change the answer."
    return ""


def _normalize_decision_logic(logic: dict[str, Any], answer_frame: dict[str, Any]) -> dict[str, Any]:
    logic = naturalize_decision_logic_payload(logic)
    return {
        "schema_id": "analyst_decision_logic_v1",
        "bounded_bottom_line": _natural_short(logic.get("bounded_bottom_line") or answer_frame.get("direct_answer"), 520),
        "support_summary": _natural_short(logic.get("support_summary") or answer_frame.get("why_this_read"), 520),
        "strongest_counterweight": _natural_short(logic.get("strongest_counterweight") or answer_frame.get("strongest_counterargument"), 420),
        "counterweight_weighting": _natural_short(
            logic.get("counterweight_weighting") or answer_frame.get("why_counterargument_does_or_does_not_change_answer"),
            520,
        ),
        "reconciled_cruxes": [_short_text(value, 280) for value in _string_list(logic.get("reconciled_cruxes"))[:6]],
        "scope_boundaries": [_short_text(value, 260) for value in _string_list(logic.get("scope_boundaries"))[:6]],
        "practical_implications": [_short_text(value, 260) for value in _string_list(logic.get("practical_implications"))[:6]],
        "do_not_overstate": _dedupe(
            [
                *[_short_text(value, 240) for value in _string_list(logic.get("do_not_overstate"))[:8]],
                *[naturalize_decision_logic_text(value) for value in _string_list(answer_frame.get("must_not_overstate"))],
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
        "bounded_bottom_line": _natural_short(answer_frame.get("direct_answer"), 520),
        "support_summary": naturalize_decision_logic_text(support) or _natural_short(answer_frame.get("why_this_read"), 520),
        "strongest_counterweight": naturalize_decision_logic_text(counter)
        or _natural_short(answer_frame.get("strongest_counterargument"), 420),
        "counterweight_weighting": content_based_counterweight_weighting(
            support=support or answer_frame.get("why_this_read"),
            counterweight=counter or answer_frame.get("strongest_counterargument"),
            fallback=answer_frame.get("why_counterargument_does_or_does_not_change_answer"),
        ),
        "reconciled_cruxes": [naturalize_decision_logic_text(value) for value in cruxes],
        "scope_boundaries": [naturalize_decision_logic_text(value) for value in scope],
        "practical_implications": _dedupe([naturalize_decision_logic_text(value) for value in implications])[:6],
        "do_not_overstate": _dedupe(
            [
                *[naturalize_decision_logic_text(value) for value in _string_list(answer_frame.get("must_not_overstate"))],
                "Keep the answer within the stated population, dose, comparator, and evidence base.",
                "Treat a counterweight as decisive only when the packet says it changes the bottom line.",
            ]
        )[:8],
    }


def _natural_short(value: Any, limit: int) -> str:
    return _short_text(naturalize_decision_logic_text(str(value or "")), limit)


def _first_group_text(groups: list[dict[str, Any]], memo_use: str) -> str:
    for group in groups:
        if group.get("memo_role") == memo_use and group.get("proposition"):
            return _short_text(str(group.get("proposition") or ""), 260)
    return ""
