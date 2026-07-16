from __future__ import annotations

from typing import Any, Iterable

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)

SOURCE_HIERARCHY_SCHEMA_ID = "source_weight_hierarchy_v1"

SOURCE_HIERARCHY_LANES: tuple[tuple[str, str], ...] = (
    ("primary_answer_drivers", "Start with"),
    ("quantitative_calibrators", "Use to size effects"),
    ("counterweight_sources", "Use as checks"),
    ("scope_boundary_sources", "Use to bound scope"),
    ("contextual_sources", "Use for context"),
)

_LANE_ALIASES = {
    "primary_sources": "primary_answer_drivers",
    "main_sources": "primary_answer_drivers",
    "main_answer_sources": "primary_answer_drivers",
    "quantitative_or_interpretive_calibrators": "quantitative_calibrators",
    "calibrates_magnitude": "quantitative_calibrators",
    "calibrator_sources": "quantitative_calibrators",
    "counterweights": "counterweight_sources",
    "counterweights_or_tensions": "counterweight_sources",
    "limiting_sources": "counterweight_sources",
    "scope_sources": "scope_boundary_sources",
    "scope_limiters": "scope_boundary_sources",
    "bounds_answer": "scope_boundary_sources",
    "context_only": "contextual_sources",
    "context_sources": "contextual_sources",
}


def source_hierarchy_schema() -> dict[str, Any]:
    return {
        "schema_id": SOURCE_HIERARCHY_SCHEMA_ID,
        "hierarchy_thesis": "one concise paragraph explaining the comparative evidence hierarchy",
        "lanes": {
            lane: [
                {
                    "source_ids": ["source_id"],
                    "evidence_item_ids": ["item_id"],
                    "role": "what this lane does for the decision",
                    "rationale": "why these sources belong in this role",
                }
            ]
            for lane, _ in SOURCE_HIERARCHY_LANES
        },
        "source_accounting": [
            {
                "source_id": "source_id",
                "primary_lane": "one lane key above",
                "rationale": "why this is the source's primary role",
            }
        ],
    }


def normalize_source_hierarchy(
    payload: Any,
    *,
    allowed_source_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = payload if isinstance(payload, dict) else {}
    if isinstance(data.get("source_hierarchy"), dict):
        data = data["source_hierarchy"]
    allowed = {source_id for source_id in (allowed_source_ids or []) if source_id}
    warnings: list[str] = []
    invalid_removed: list[str] = []
    lanes = {lane: [] for lane, _ in SOURCE_HIERARCHY_LANES}
    raw_lanes = _dict(data.get("lanes"))
    for raw_lane, rows in raw_lanes.items():
        lane = _canonical_lane(str(raw_lane or ""))
        if not lane:
            warnings.append("unrecognized_lane_removed")
            continue
        for row in _list(rows):
            if not isinstance(row, dict):
                continue
            normalized = _normalize_lane_row(row, lane=lane, allowed_source_ids=allowed)
            invalid_removed.extend(normalized.pop("_invalid_source_ids", []))
            if normalized.get("source_ids"):
                lanes[lane].append(normalized)
    accounting = []
    for row in _list(data.get("source_accounting")):
        if not isinstance(row, dict):
            continue
        normalized = _normalize_accounting_row(row, allowed_source_ids=allowed)
        invalid_removed.extend(normalized.pop("_invalid_source_ids", []))
        if normalized.get("source_id"):
            accounting.append(normalized)
    expected_ids = sorted(allowed) if allowed else sorted(_source_ids_from_lanes(lanes))
    accounted_ids = {str(row.get("source_id") or "") for row in accounting if row.get("source_id")}
    missing_accounting = [source_id for source_id in expected_ids if source_id not in accounted_ids]
    if missing_accounting:
        warnings.append("missing_source_accounting")
    primary_count = len(_source_ids_from_lanes({"primary_answer_drivers": lanes["primary_answer_drivers"]}))
    if primary_count > 3:
        warnings.append("flat_primary_answer_driver_lane")
    if invalid_removed:
        warnings.append("invalid_source_ids_removed")
    hierarchy = {
        "schema_id": SOURCE_HIERARCHY_SCHEMA_ID,
        "hierarchy_thesis": _short_text(data.get("hierarchy_thesis") or data.get("thesis") or data.get("summary"), 600),
        "lanes": {lane: _dedupe_lane_rows(rows) for lane, rows in lanes.items()},
        "source_accounting": _dedupe_accounting(accounting),
    }
    report = {
        "schema_id": "source_weight_hierarchy_report_v1",
        "status": "warning" if warnings else ("ready" if any(hierarchy["lanes"].values()) else "empty"),
        "warnings": _dedupe(warnings),
        "invalid_source_ids_removed": _dedupe(invalid_removed),
        "missing_source_accounting": missing_accounting,
        "source_count": len(expected_ids),
        "accounted_source_count": len(accounted_ids),
        "primary_driver_source_count": primary_count,
    }
    return hierarchy, report


def normalize_source_hierarchy_for_context(payload: Any, context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return normalize_source_hierarchy(payload, allowed_source_ids=context_source_ids(context))


def attach_normalized_source_hierarchy(model: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    updated = dict(model)
    hierarchy, report = normalize_source_hierarchy_for_context(updated.get("source_hierarchy"), context)
    updated["source_hierarchy"] = hierarchy
    updated["source_hierarchy_report"] = report
    return updated


def context_source_ids(context: dict[str, Any]) -> list[str]:
    source_ids = []
    for row in _list(context.get("evidence_rows")):
        if isinstance(row, dict):
            source_ids.extend(_string_list(row.get("source_ids")))
    for source in _list(context.get("source_inventory")):
        if isinstance(source, dict):
            source_ids.append(str(source.get("source_id") or "").strip())
    return _dedupe(source_id for source_id in source_ids if source_id)


def compact_source_hierarchy_for_prompt(hierarchy: dict[str, Any] | None) -> dict[str, Any]:
    row = hierarchy if isinstance(hierarchy, dict) else {}
    if row.get("schema_id") != SOURCE_HIERARCHY_SCHEMA_ID:
        return {}
    lanes = {}
    for lane, _ in SOURCE_HIERARCHY_LANES:
        lane_rows = _list(_dict(row.get("lanes")).get(lane))[:4]
        if lane_rows:
            lanes[lane] = lane_rows
    return {
        "schema_id": SOURCE_HIERARCHY_SCHEMA_ID,
        "hierarchy_thesis": row.get("hierarchy_thesis", ""),
        "lanes": lanes,
        "source_accounting": _list(row.get("source_accounting"))[:12],
    }


def render_source_hierarchy_section(hierarchy: dict[str, Any] | None) -> str:
    row = hierarchy if isinstance(hierarchy, dict) else {}
    if row.get("schema_id") != SOURCE_HIERARCHY_SCHEMA_ID:
        return ""
    lanes = _dict(row.get("lanes"))
    if not any(_list(lanes.get(lane)) for lane, _ in SOURCE_HIERARCHY_LANES):
        return ""
    lines = ["## How to Weight the Evidence", ""]
    thesis = str(row.get("hierarchy_thesis") or "").strip()
    if thesis:
        lines.append(thesis)
    else:
        lines.append(
            "Read the evidence by decision role: start with the sources that carry the answer, then use the rest to size effects, test limits, bound scope, or translate the finding."
        )
    lane_lines = []
    for lane, label in SOURCE_HIERARCHY_LANES:
        lane_text = _render_lane(label, _list(lanes.get(lane)))
        if lane_text:
            lane_lines.append(lane_text)
    if lane_lines:
        lines.extend(["", *lane_lines])
    return "\n".join(lines).strip()


def _normalize_lane_row(row: dict[str, Any], *, lane: str, allowed_source_ids: set[str]) -> dict[str, Any]:
    source_ids, invalid = _validated_source_ids(row.get("source_ids") or row.get("sources"), allowed_source_ids)
    return {
        "source_ids": source_ids[:6],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids") or row.get("item_ids"))[:10],
        "evidence_group_ids": _string_list(row.get("evidence_group_ids") or row.get("group_ids"))[:10],
        "role": _short_text(row.get("role") or row.get("use") or lane.replace("_", " "), 260),
        "rationale": _short_text(row.get("rationale") or row.get("why") or row.get("reason"), 420),
        "_invalid_source_ids": invalid,
    }


def _normalize_accounting_row(row: dict[str, Any], *, allowed_source_ids: set[str]) -> dict[str, Any]:
    source_ids, invalid = _validated_source_ids(row.get("source_ids") or [row.get("source_id")], allowed_source_ids)
    return {
        "source_id": source_ids[0] if source_ids else "",
        "primary_lane": _canonical_lane(str(row.get("primary_lane") or row.get("lane") or "")),
        "rationale": _short_text(row.get("rationale") or row.get("why") or row.get("reason"), 360),
        "_invalid_source_ids": invalid,
    }


def _validated_source_ids(value: Any, allowed_source_ids: set[str]) -> tuple[list[str], list[str]]:
    source_ids = _string_list(value)
    valid = []
    invalid = []
    for source_id in source_ids:
        if allowed_source_ids and source_id not in allowed_source_ids:
            invalid.append(source_id)
            continue
        valid.append(source_id)
    return _dedupe(valid), _dedupe(invalid)


def _canonical_lane(value: str) -> str:
    lane = str(value or "").strip()
    if lane in {key for key, _ in SOURCE_HIERARCHY_LANES}:
        return lane
    return _LANE_ALIASES.get(lane, "")


def _source_ids_from_lanes(lanes: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {source_id for rows in lanes.values() for row in rows for source_id in _string_list(row.get("source_ids"))}


def _dedupe_lane_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    deduped = []
    for row in rows:
        key = tuple(_string_list(row.get("source_ids")))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _dedupe_accounting(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for row in rows:
        source_id = str(row.get("source_id") or "").strip()
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        deduped.append(row)
    return deduped


def _render_lane(label: str, rows: list[Any]) -> str:
    lane_rows = [row for row in rows if isinstance(row, dict) and _string_list(row.get("source_ids"))]
    if not lane_rows:
        return ""
    sources = _cite_list(_dedupe(source_id for row in lane_rows for source_id in _string_list(row.get("source_ids"))))
    rationales = _dedupe(
        str(row.get("rationale") or row.get("role") or "").strip().rstrip(".")
        for row in lane_rows
        if str(row.get("rationale") or row.get("role") or "").strip()
    )
    if rationales:
        return f"- **{label}:** {sources} — {_join_fragments(rationales[:2])}."
    return f"- **{label}:** {sources}."


def _cite_list(source_ids: list[str]) -> str:
    return ", ".join(f"[{source_id}]" for source_id in source_ids if source_id)


def _join_fragments(items: list[str]) -> str:
    cleaned = [item for item in items if item]
    if len(cleaned) <= 1:
        return "".join(cleaned)
    return "; ".join(cleaned[:-1]) + "; " + cleaned[-1]
