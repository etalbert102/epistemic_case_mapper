from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_ready_polish_anchors import protected_anchor_checklist


def build_memo_ready_final_polish_guardrails(packet: dict[str, Any]) -> dict[str, Any]:
    anchors = protected_anchor_checklist(packet)
    spine = _dict(packet.get("answer_spine"))
    return {
        "schema_id": "memo_ready_final_polish_guardrails_v1",
        "decision_question": str(packet.get("decision_question") or "").strip(),
        "confidence": str(spine.get("confidence") or packet.get("confidence") or "").strip(),
        "source_ids_that_must_remain_traceable": _guardrail_source_ids(anchors),
        "quantities_that_must_remain_visible": _guardrail_quantities(anchors),
        "scope_or_counterweight_cues_to_preserve": _guardrail_scope_cues(anchors),
        "protected_anchor_count": len(anchors),
    }


def _guardrail_source_ids(anchors: list[dict[str, Any]]) -> list[str]:
    return _dedupe(source_id for anchor in anchors for source_id in _string_list(anchor.get("source_ids")))


def _guardrail_quantities(anchors: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    seen: set[str] = set()
    for anchor in anchors:
        for quantity in _list(anchor.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            rows.append(
                _drop_empty_guardrail(
                    {
                        "value": value,
                        "interpretation": str(quantity.get("interpretation") or "").strip(),
                    }
                )
            )
    return rows[:24]


def _guardrail_scope_cues(anchors: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for anchor in anchors:
        role = str(anchor.get("role") or anchor.get("anchor_type") or "").strip()
        meaning = str(anchor.get("required_meaning") or anchor.get("decision_relevance") or "").strip()
        if not meaning or not _is_scope_or_counterweight_role(role, meaning):
            continue
        rows.append(
            _drop_empty_guardrail(
                {
                    "role": role,
                    "cue": _compact_guardrail_text(meaning, max_chars=220),
                    "source_ids": ", ".join(_string_list(anchor.get("source_ids"))[:4]),
                }
            )
        )
    return rows[:10]


def _is_scope_or_counterweight_role(role: str, meaning: str) -> bool:
    text = f"{role} {meaning}".lower()
    return any(
        token in text
        for token in [
            "counterweight",
            "scope",
            "caveat",
            "uncertain",
            "uncertainty",
            "limit",
            "subgroup",
            "boundary",
            "warning",
            "crux",
        ]
    )


def _compact_guardrail_text(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    trimmed = cleaned[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return trimmed + "..."


def _drop_empty_guardrail(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, []) and value != {}}
