from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import dedupe as _dedupe
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import list_value as _list


def render_source_weighting_caveat_note(caveat_rows: list[dict[str, Any]]) -> str:
    limits_by_source = [
        {"sources": str(row.get("sources") or "").strip(), "limits": _source_limit_phrases(row)}
        for row in caveat_rows
        if str(row.get("sources") or "").strip() and _source_limit_phrases(row)
    ]
    if not limits_by_source:
        return ""
    unique_limits = _dedupe(limit for row in limits_by_source for limit in row["limits"])
    if len(unique_limits) == 1:
        return "\n".join(
            [
                "Use limits:",
                f"- Across cited sources: {unique_limits[0]}.",
                "- The citation trace keeps source-by-source detail.",
            ]
        )
    clauses = [f"- {row['sources']}: {row['limits'][0]}." for row in limits_by_source[:3]]
    return "\n".join(["Use limits:", *clauses, "- The citation trace keeps source-by-source detail."])


def _source_limit_phrases(row: dict[str, Any]) -> list[str]:
    return _dedupe(
        _clean_source_limit_phrase(limit)
        for limit in _list(row.get("limits"))
        if _clean_source_limit_phrase(limit)
    )


def _clean_source_limit_phrase(value: Any) -> str:
    phrase = str(value or "").strip().rstrip(".;")
    phrase = phrase[:1].lower() + phrase[1:] if phrase else ""
    if phrase.startswith("use "):
        phrase = phrase.removeprefix("use ")
    return phrase
