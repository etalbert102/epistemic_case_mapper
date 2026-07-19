from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import short_text as _short_text

CONTRIBUTION_FIELD_LIMITS = {
    "decision_contribution": 360,
    "use_in_reasoning": 120,
    "key_qualifier": 220,
    "quantity_takeaway": 240,
    "source_weight_note": 220,
    "misuse_warning": 240,
    "if_omitted": 240,
}
SKELETON_CONTRIBUTION_FIELD_LIMITS = {"decision_contribution": 180, "key_qualifier": 140}
OBLIGATION_CONTRIBUTION_FIELD_LIMITS = {
    "decision_contribution": 220,
    "use_in_reasoning": 120,
    "key_qualifier": 180,
    "quantity_takeaway": 180,
    "misuse_warning": 180,
    "if_omitted": 180,
}


def contribution_fields(source: dict[str, Any], *, limits: dict[str, int] | None = None) -> dict[str, str]:
    active_limits = limits or CONTRIBUTION_FIELD_LIMITS
    rows: dict[str, str] = {}
    for key, limit in active_limits.items():
        value = _short_text(str(source.get(key) or ""), limit)
        if value:
            rows[key] = value
    return rows
