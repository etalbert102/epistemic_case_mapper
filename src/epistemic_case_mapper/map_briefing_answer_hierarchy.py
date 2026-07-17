from __future__ import annotations

from epistemic_case_mapper.map_briefing_balanced_answer_frame import split_bluf_answer_hierarchy
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import short_text as _short_text


def answer_hierarchy_from_fields(
    *,
    direct_answer: str,
    primary_answer: str = "",
    secondary_detail: str = "",
    secondary_detail_type: str = "",
    full_direct_answer: str = "",
) -> dict[str, str]:
    direct = str(full_direct_answer or direct_answer or "").strip()
    split = split_bluf_answer_hierarchy(direct)
    secondary_type = str(secondary_detail_type or split["secondary_detail_type"]).strip()
    if secondary_type == "none":
        secondary_type = ""
    secondary = str(secondary_detail or split["secondary_detail"]).strip()
    return {
        "direct_answer": _short_text(direct, 700),
        "primary_answer": _short_text(primary_answer or split["primary_answer"], 520),
        "secondary_detail": _short_text(secondary, 420),
        "secondary_detail_type": secondary_type,
        "full_direct_answer": _short_text(full_direct_answer or direct, 700) if secondary else "",
    }
