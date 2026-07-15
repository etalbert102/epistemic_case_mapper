from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


def build_balanced_answer_frame(
    *,
    skeleton: dict[str, Any],
    analyst_reasoning_frame: dict[str, Any],
    source_weighted_answer_frame: dict[str, Any],
    organized_evidence_inventory: dict[str, Any],
    counterweight_dispositions: list[dict[str, Any]],
    scope_boundaries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a concise controlling answer frame for memo synthesis."""

    lanes = _dict(source_weighted_answer_frame.get("lanes"))
    support = _text(skeleton.get("main_reason")) or _first_statement(_list(lanes.get("primary_answer_drivers")))
    counterweight = _first_statement(counterweight_dispositions) or _text(skeleton.get("strongest_counterweight"))
    scope = _text(skeleton.get("scope")) or _first_statement(scope_boundaries)
    practical = _text(skeleton.get("practical_implication"))
    underused = _underused_balance_evidence(organized_evidence_inventory, lanes)
    must_not_overstate = _overstatement_limits(analyst_reasoning_frame, lanes)
    return _drop_empty(
        {
            "schema_id": "balanced_answer_frame_v1",
            "best_current_read": _short_text(_text(skeleton.get("direct_answer")) or _text(analyst_reasoning_frame.get("bottom_line")), 700),
            "confidence": _text(skeleton.get("confidence")),
            "confidence_basis": _short_text(_text(skeleton.get("confidence_basis")) or _text(analyst_reasoning_frame.get("why_this_answer")), 700),
            "main_support": _short_text(support, 700),
            "main_counterweight": _short_text(counterweight, 700),
            "scope": _short_text(scope, 700),
            "practical_read": _short_text(practical, 700),
            "must_not_overstate": must_not_overstate,
            "underused_balance_evidence": underused,
            "synthesis_instruction": (
                "Use this as the controlling answer frame: state the current read crisply, then reconcile support, "
                "counterweight, scope, and underused balancing evidence without overstating causal strength."
            ),
        }
    )


def build_bluf_contract(
    *,
    skeleton: dict[str, Any],
    balanced_answer_frame: dict[str, Any],
) -> dict[str, Any]:
    """Build an answer-first contract for the memo opening."""

    recommended = _text(balanced_answer_frame.get("best_current_read")) or _text(skeleton.get("direct_answer"))
    scope = _text(balanced_answer_frame.get("scope")) or _text(skeleton.get("scope"))
    exception = _text(balanced_answer_frame.get("main_counterweight")) or _text(skeleton.get("strongest_counterweight"))
    practical = _text(balanced_answer_frame.get("practical_read")) or _text(skeleton.get("practical_implication"))
    confidence = _text(balanced_answer_frame.get("confidence")) or _text(skeleton.get("confidence"))
    return _drop_empty(
        {
            "schema_id": "bluf_contract_v1",
            "recommended_read": _short_text(recommended, 520),
            "who_it_applies_to": _short_text(scope, 360),
            "main_exception_or_boundary": _short_text(exception, 360),
            "confidence": confidence,
            "practical_read": _short_text(practical, 360),
            "one_sentence_version": _short_text(_one_sentence_bluf(recommended, scope, exception, confidence), 700),
            "writing_contract": [
                "Answer the decision question in the first sentence.",
                "Add the main scope or exception in the same sentence or the next sentence.",
                "Name confidence without turning uncertainty into a research-status lead.",
                "Do not lead with a single study, method caveat, or generic evidence inventory.",
            ],
        }
    )


def _one_sentence_bluf(recommended: str, scope: str, exception: str, confidence: str) -> str:
    first = _text(recommended)
    if not first:
        return ""
    additions = []
    if scope:
        additions.append(f"within this scope: {scope}")
    if exception:
        additions.append(f"with this main boundary: {exception}")
    if confidence:
        additions.append(f"confidence: {confidence}")
    if not additions:
        return first
    return f"{first} ({'; '.join(additions)})."


def _underused_balance_evidence(inventory: dict[str, Any], lanes: dict[str, Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected.extend(_balance_rows(_list(lanes.get("quantitative_or_interpretive_calibrators")), reason="calibrates_or_contextualizes"))
    selected.extend(_balance_rows(_list(lanes.get("context_only")), reason="contextualizes_application"))
    inventory_lanes = _dict(inventory.get("lanes"))
    selected.extend(_balance_rows(_list(inventory_lanes.get("interpretive_context")), reason="interpretive_context"))
    return _dedupe_rows(selected, "claim")[:6]


def _balance_rows(rows: list[Any], *, reason: str) -> list[dict[str, Any]]:
    balanced = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        claim = _first_text(row, "claim", "statement", "reader_claim")
        if not claim:
            continue
        balanced.append(
            _drop_empty(
                {
                    "reason": reason,
                    "claim": _short_text(claim, 520),
                    "source_ids": _row_source_ids(row),
                    "quantities": row.get("quantities"),
                }
            )
        )
    return balanced


def _source_use_limits(lanes: dict[str, Any]) -> list[str]:
    return _dedupe(
        limit
        for rows in lanes.values()
        for row in _list(rows)
        if isinstance(row, dict)
        for limit in _string_list(row.get("not_enough_for"))
        if _looks_like_use_limit(limit)
    )


def _overstatement_limits(analyst_reasoning_frame: dict[str, Any], lanes: dict[str, Any]) -> list[str]:
    explicit = [
        limit
        for limit in _string_list(analyst_reasoning_frame.get("do_not_overstate"))
        if _looks_like_overstatement_instruction(limit)
    ]
    return _dedupe(
        [
            *explicit,
            *_source_use_limits(lanes),
            "Do not state stronger causal or confidence claims than the source-specific appraisals support.",
        ]
    )[:8]


def _looks_like_overstatement_instruction(value: str) -> bool:
    lowered = _text(value).lower()
    return lowered.startswith(("do not ", "don't ", "avoid ", "do not imply", "do not claim"))


def _looks_like_use_limit(value: str) -> bool:
    text = _text(value)
    lowered = text.lower()
    return len(text) <= 120 and any(
        token in lowered
        for token in ("_", "caus", "guidance", "observational", "uncertain", "weak", "indirect", "not enough")
    )


def _row_source_ids(row: dict[str, Any]) -> list[str]:
    explicit = _string_list(row.get("source_ids")) or ([str(row.get("source_id"))] if row.get("source_id") else [])
    quantity_sources = [
        source_id
        for quantity in _list(row.get("quantities"))
        if isinstance(quantity, dict)
        for source_id in _string_list(quantity.get("source_ids"))
    ]
    return _dedupe([*explicit, *quantity_sources])


def _first_statement(rows: list[Any]) -> str:
    for row in rows:
        if isinstance(row, dict):
            text = _first_text(row, "claim", "statement", "disposition_rationale", "decision_relevance")
            if text:
                return text
    return ""


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = _text(row.get(key))
        if text:
            return text
    return ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for row in rows:
        marker = _text(row.get(key)).lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
