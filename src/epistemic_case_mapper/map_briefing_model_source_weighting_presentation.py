from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_lightweight_guidance import evidence_quality_caveat_text
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    string_list as _string_list,
)


def render_model_source_weighting_section(
    rows: list[dict[str, Any]],
    *,
    summary: str,
    guidance: dict[str, Any] | None = None,
) -> str:
    if not any(str(row.get("memo_weight_sentence") or "").strip() for row in rows):
        return ""
    lines = ["## How to Weight the Evidence", "", summary, ""]
    for row in _ordered_source_weight_rows(rows):
        sources = _source_group_citations([row])
        sentence = _clean_source_weight_sentence(row)
        if not sources or not sentence:
            continue
        lines.append(f"- {sources}: {sentence}")
        limits = _source_local_limits(row, guidance=guidance)
        if limits:
            lines.append(f"  Use limit: {_join_readable_list(limits)}.")
    return "\n".join(lines).strip()


def _ordered_source_weight_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {
        "drives_answer": 0,
        "calibrates_magnitude": 1,
        "bounds_answer": 2,
        "defines_scope": 3,
        "identifies_crux": 4,
        "contextualizes": 5,
    }
    return sorted(rows, key=lambda row: (priority.get(str(row.get("main_use") or "contextualizes"), 9), _source_group_citations([row])))


def _clean_source_weight_sentence(row: dict[str, Any]) -> str:
    sentence = str(row.get("memo_weight_sentence") or row.get("why_weight_this_way") or "").strip()
    if not sentence:
        return ""
    return sentence[:1].upper() + sentence[1:].rstrip(".") + "."


def _source_local_limits(row: dict[str, Any], *, guidance: dict[str, Any] | None) -> list[str]:
    source_ids = _string_list(row.get("source_ids"))
    limits = _string_list(row.get("reader_facing_limit")) or _string_list(row.get("what_not_to_use_it_for"))
    sentence = _clean_source_weight_sentence(row).lower()
    return [limit for limit in _readable_limits(limits, source_ids=source_ids, guidance=guidance) if limit and limit.lower() not in sentence][:2]


def _source_group_citations(rows: list[dict[str, Any]]) -> str:
    return _cite_list(_dedupe(source_id for row in rows for source_id in _string_list(row.get("source_ids"))))


def _cite_list(source_ids: list[str]) -> str:
    return ", ".join(f"[{source_id}]" for source_id in source_ids if source_id)


def _readable_limits(limits: list[str], *, source_ids: list[str], guidance: dict[str, Any] | None) -> list[str]:
    rows: list[str] = []
    caveats = evidence_quality_caveat_text(guidance, source_ids)
    for limit in limits:
        if limit == "quality_limit" and caveats:
            rows.extend(_clean_limit_phrase(caveat) for caveat in caveats)
        else:
            rows.append(_clean_limit_phrase(_readable_warning(limit)))
    return _dedupe(rows)[:3]


def _readable_warning(warning: str) -> str:
    warning = str(warning or "").strip()
    if warning == "quality_limit":
        return "weak, indirect, or unknown evidence-quality status"
    return warning.replace("_", " ")


def _clean_limit_phrase(value: str) -> str:
    phrase = str(value or "").strip().rstrip(".;")
    if not phrase:
        return ""
    return phrase[:1].lower() + phrase[1:]


def _join_readable_list(items: list[str]) -> str:
    cleaned = [str(item or "").strip().rstrip(".") for item in items if str(item or "").strip()]
    if len(cleaned) <= 1:
        return "".join(cleaned)
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + ", and " + cleaned[-1]
