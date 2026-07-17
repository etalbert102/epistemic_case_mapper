from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


HIERARCHY_TO_CANONICAL_LANE = {
    "primary_answer_drivers": "primary_answer_drivers",
    "quantitative_calibrators": "quantitative_or_interpretive_calibrators",
    "counterweight_sources": "counterweights_or_tensions",
    "scope_boundary_sources": "scope_limiters",
    "contextual_sources": "context_only",
}


def source_hierarchy_lane_index(hierarchy: dict[str, Any]) -> list[dict[str, Any]]:
    matches = []
    lanes = _dict(hierarchy.get("lanes"))
    for hierarchy_lane, rows in lanes.items():
        canonical_lane = HIERARCHY_TO_CANONICAL_LANE.get(str(hierarchy_lane or ""))
        if not canonical_lane:
            continue
        for row in _list(rows):
            if isinstance(row, dict):
                matches.append(_hierarchy_match_row(str(hierarchy_lane), canonical_lane, row))
    for row in _list(hierarchy.get("source_accounting")):
        if not isinstance(row, dict):
            continue
        hierarchy_lane = str(row.get("primary_lane") or "")
        canonical_lane = HIERARCHY_TO_CANONICAL_LANE.get(hierarchy_lane)
        source_id = str(row.get("source_id") or "").strip()
        if canonical_lane and source_id:
            matches.append(
                _drop_empty(
                    {
                        "hierarchy_lane": hierarchy_lane,
                        "canonical_lane": canonical_lane,
                        "source_ids": [source_id],
                        "rationale": _short_text(row.get("rationale"), 360),
                    }
                )
            )
    return matches


def source_hierarchy_match_for_row(row: dict[str, Any], hierarchy_index: list[dict[str, Any]]) -> dict[str, Any]:
    row_sources = set(_string_list(row.get("source_ids")))
    row_evidence = set(
        _string_list(
            _dict(row.get("lineage")).get("evidence_item_ids")
            or _dict(row.get("lineage")).get("covered_evidence_item_ids")
        )
    )
    for match in hierarchy_index:
        if row_sources and row_sources.intersection(_string_list(match.get("source_ids"))):
            return match
        if row_evidence and row_evidence.intersection(_string_list(match.get("evidence_item_ids"))):
            return match
    return {}


def _hierarchy_match_row(hierarchy_lane: str, canonical_lane: str, row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "hierarchy_lane": hierarchy_lane,
            "canonical_lane": canonical_lane,
            "source_ids": _string_list(row.get("source_ids")),
            "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
            "role": _short_text(row.get("role"), 240),
            "rationale": _short_text(row.get("rationale"), 360),
        }
    )


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
