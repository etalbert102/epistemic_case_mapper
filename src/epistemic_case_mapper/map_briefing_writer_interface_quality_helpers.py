from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import dict_value as _dict, list_value as _list


GENERIC_JUDGMENT_PATTERNS = (
    "use counterweights to bound",
    "connect this reasoning step",
    "write directly from",
    "answer the decision question",
    "if they do not overturn",
)


def contains_generic_judgment(value: Any) -> bool:
    text = str(value or "").lower()
    if any(pattern in text for pattern in GENERIC_JUDGMENT_PATTERNS):
        return True
    if isinstance(value, dict):
        return any(contains_generic_judgment(row) for row in value.values())
    if isinstance(value, list):
        return any(contains_generic_judgment(row) for row in value)
    return False


def reader_facing_judgment_surface(interface: dict[str, Any]) -> dict[str, Any]:
    """Return generated judgment fields, excluding internal writer instructions."""

    return {
        "bottom_line": interface.get("bottom_line"),
        "answer_frame": interface.get("answer_frame"),
        "support_that_drives_answer": _claim_surface(interface.get("support_that_drives_answer")),
        "counterweights_and_disposition": [
            {
                "claim": row.get("claim"),
                "disposition": row.get("disposition"),
                "disposition_rationale": row.get("disposition_rationale"),
            }
            for row in _list(interface.get("counterweights_and_disposition"))
            if isinstance(row, dict)
        ],
        "scope_boundaries": _claim_surface(interface.get("scope_boundaries")),
        "decision_cruxes": _claim_surface(interface.get("decision_cruxes")),
        "practical_implications": interface.get("practical_implications"),
        "practical_implication_cards": [
            {"implication_type": row.get("implication_type"), "statement": row.get("statement")}
            for row in _list(interface.get("practical_implication_cards"))
            if isinstance(row, dict)
        ],
        "critique_writer_guidance": interface.get("critique_writer_guidance"),
    }


def informative_source_appraisal(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("decision_directness") or "").strip() not in {"", "unknown"}:
        return True
    return bool(
        _list(row.get("evidence_proximity"))
        or _list(row.get("recommended_uses"))
        or _list(row.get("source_use_warnings"))
        or _list(row.get("interpretation_caveats"))
        or _dict(row.get("allowed_wording"))
    )


def _claim_surface(rows: Any) -> list[dict[str, Any]]:
    return [
        {
            "claim": row.get("claim"),
            "why_it_matters": row.get("why_it_matters"),
            "answer_relation": row.get("answer_relation"),
        }
        for row in _list(rows)
        if isinstance(row, dict)
    ]
