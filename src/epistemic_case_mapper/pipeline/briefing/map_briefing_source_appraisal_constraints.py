from __future__ import annotations

from typing import Any, Iterable

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


LOAD_BEARING_ROLES = {
    "strongest_support",
    "strongest_counterweight",
    "decision_crux",
    "scope_boundary",
}


def human_review_load_bearing_ids(units: Iterable[Any]) -> list[str]:
    blocked = []
    for unit in units:
        if not isinstance(unit, dict) or unit.get("role") not in LOAD_BEARING_ROLES:
            continue
        appraisal = _dict(unit.get("source_appraisal"))
        if "human_review_needed" not in _string_list(appraisal.get("recommended_uses")):
            continue
        blocked.append(str(unit.get("unit_id") or unit.get("item_id") or "unnamed_unit"))
    return _dedupe(blocked)


def constrain_source_weight_judgment(
    judgment: dict[str, Any],
    *,
    source_label: str,
    recommended_uses: Iterable[str],
    warnings: Iterable[str],
    caveats: Iterable[str] = (),
) -> dict[str, Any]:
    """Apply manifest-backed source-use ceilings to a model judgment."""

    row = dict(judgment)
    uses = set(_string_list(list(recommended_uses)))
    warning_set = set(_string_list(list(warnings)))
    caveat_rows = _dedupe(_string_list(list(caveats)))
    constraints: list[str] = []

    if "human_review_needed" in uses:
        row["main_use"] = "contextualizes"
        row["confidence_effect"] = "neutral"
        row["reader_facing_limit"] = (
            "Use only as context until the source provenance and suitability for decision use are reviewed."
        )
        row["what_not_to_use_it_for"] = _dedupe(
            [
                *_string_list(row.get("what_not_to_use_it_for")),
                "Do not use as decision-grade or load-bearing evidence before review.",
            ]
        )
        row["memo_weight_sentence"] = f"Use {source_label} only as context until its provenance is reviewed."
        constraints.append("human_review_needed_not_load_bearing")
    elif uses.intersection({"background_or_context", "decision_context_or_corroboration"}):
        if str(row.get("main_use") or "") in {"drives_answer", "calibrates_magnitude"}:
            row["main_use"] = "contextualizes"
            constraints.append("context_source_not_load_bearing")
    elif "corroborate_or_bound" in uses and str(row.get("main_use") or "") == "drives_answer":
        row["main_use"] = "bounds_answer"
        constraints.append("corroboration_source_not_primary_driver")

    independence_limited = "independence_not_established" in warning_set or any(
        "independen" in caveat.lower() or "correlat" in caveat.lower()
        for caveat in caveat_rows
    )
    if independence_limited:
        if row.get("confidence_effect") == "raises_confidence":
            row["confidence_effect"] = "neutral"
        row["reader_facing_limit"] = " ".join(
            part
            for part in (
                str(row.get("reader_facing_limit") or "").strip(),
                caveat_rows[0]
                if caveat_rows
                else "Treat this source as potentially correlated with its declared evidence cluster.",
            )
            if part
        )
        row["what_not_to_use_it_for"] = _dedupe(
            [
                *_string_list(row.get("what_not_to_use_it_for")),
                "Do not count as independent confirmation without an independence check.",
            ]
        )
        if "human_review_needed" not in uses:
            row["memo_weight_sentence"] = (
                f"Use {source_label} for its assigned role, but do not count it as independent confirmation."
            )
        constraints.append("independence_not_established")

    if constraints:
        row["source_appraisal_constraints"] = _dedupe(
            [*_string_list(row.get("source_appraisal_constraints")), *constraints]
        )
        row["constraint_method"] = "deterministic_manifest_source_use_guard"
    return _bounded_judgment_text(row)


def source_constraints_from_context_rows(rows: Iterable[Any]) -> dict[str, dict[str, list[str]]]:
    by_source: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        quality = _dict(row.get("source_quality"))
        for source_id in _string_list(row.get("source_ids")):
            constraints = by_source.setdefault(
                source_id,
                {"recommended_uses": [], "warnings": [], "caveats": [], "evidence_item_ids": []},
            )
            constraints["recommended_uses"] = _dedupe(
                [*constraints["recommended_uses"], *_string_list(quality.get("recommended_uses"))]
            )
            constraints["warnings"] = _dedupe(
                [*constraints["warnings"], *_string_list(quality.get("warnings"))]
            )
            constraints["caveats"] = _dedupe(
                [*constraints["caveats"], *_string_list(quality.get("interpretation_caveats"))]
            )
            constraints["evidence_item_ids"] = _dedupe(
                [
                    *constraints["evidence_item_ids"],
                    *_string_list(row.get("evidence_item_ids") or row.get("evidence_item_id")),
                ]
            )
    return by_source


def constrain_source_hierarchy(
    hierarchy: dict[str, Any],
    report: dict[str, Any],
    constraints_by_source: dict[str, dict[str, list[str]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Remove manifest-limited sources from lanes they cannot safely occupy."""

    updated = dict(hierarchy)
    lanes = {key: [dict(row) for row in _list(value) if isinstance(row, dict)] for key, value in _dict(updated.get("lanes")).items()}
    moved: dict[str, list[str]] = {}
    for lane, lane_rows in list(lanes.items()):
        retained_rows = []
        for lane_row in lane_rows:
            retained_ids = []
            for source_id in _string_list(lane_row.get("source_ids")):
                if _lane_allowed(lane, constraints_by_source.get(source_id, {})):
                    retained_ids.append(source_id)
                else:
                    moved.setdefault(source_id, []).extend(
                        _string_list(constraints_by_source.get(source_id, {}).get("evidence_item_ids"))
                    )
            if retained_ids:
                retained_rows.append({**lane_row, "source_ids": retained_ids})
        lanes[lane] = retained_rows
    contextual = lanes.setdefault("contextual_sources", [])
    contextual_ids = {
        source_id
        for row in contextual
        for source_id in _string_list(row.get("source_ids"))
    }
    for source_id, evidence_ids in moved.items():
        if source_id in contextual_ids:
            continue
        contextual.append(
            {
                "source_ids": [source_id],
                "evidence_item_ids": _dedupe(evidence_ids),
                "role": "context subject to manifest source-use constraints",
                "rationale": "Manifest provenance or source-use metadata prevents load-bearing use.",
            }
        )
    accounting = []
    for row in _list(updated.get("source_accounting")):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "")
        accounting.append(
            {
                **row,
                **(
                    {
                        "primary_lane": "contextual_sources",
                        "rationale": "Manifest provenance or source-use metadata prevents load-bearing use.",
                    }
                    if source_id in moved
                    else {}
                ),
            }
        )
    updated["lanes"] = lanes
    updated["source_accounting"] = accounting
    updated_report = dict(report)
    if moved:
        thesis = str(updated.get("hierarchy_thesis") or "").strip()
        guard = "Manifest source-use constraints override any conflicting proposed source lane."
        updated["hierarchy_thesis"] = _short_text(f"{thesis} {guard}".strip(), 600)
        updated_report["status"] = "warning"
        updated_report["warnings"] = _dedupe(
            [*_string_list(updated_report.get("warnings")), "manifest_source_use_constraints_applied"]
        )
        updated_report["manifest_constrained_source_ids"] = sorted(moved)
        updated_report["primary_driver_source_count"] = len(
            {
                source_id
                for row in _list(lanes.get("primary_answer_drivers"))
                if isinstance(row, dict)
                for source_id in _string_list(row.get("source_ids"))
            }
        )
    return updated, updated_report


def _lane_allowed(lane: str, constraints: dict[str, list[str]]) -> bool:
    uses = set(_string_list(constraints.get("recommended_uses")))
    if "human_review_needed" in uses or "background_or_context" in uses:
        return lane == "contextual_sources"
    if "decision_context_or_corroboration" in uses:
        return lane in {"counterweight_sources", "scope_boundary_sources", "contextual_sources"}
    if "corroborate_or_bound" in uses:
        return lane != "primary_answer_drivers"
    return True


def _bounded_judgment_text(row: dict[str, Any]) -> dict[str, Any]:
    bounded = dict(row)
    for key, limit in (
        ("why_weight_this_way", 700),
        ("reader_facing_limit", 360),
        ("memo_weight_sentence", 520),
    ):
        if key in bounded:
            bounded[key] = _short_text(bounded.get(key), limit)
    return {key: value for key, value in bounded.items() if value not in (None, "", [], {})}
