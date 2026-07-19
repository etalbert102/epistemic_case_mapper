from __future__ import annotations

import os
from typing import Any


def prefilter_model_quantity_candidates(
    report: dict[str, Any],
    *,
    per_group_limit: int | None = None,
    global_limit: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = [row for row in _list(report.get("candidate_bindings")) if isinstance(row, dict)]
    candidates = [row for row in rows if row.get("model_adjudication_required")]
    per_group_limit = per_group_limit or _limit("ECM_QUANTITY_BINDING_MODEL_CANDIDATES_PER_GROUP", 4)
    global_limit = global_limit or _limit("ECM_QUANTITY_BINDING_MODEL_CANDIDATE_LIMIT", 64)
    by_group: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        by_group.setdefault(str(row.get("group_id") or ""), []).append(row)
    ranked_groups = {
        group_id: sorted(group_rows, key=_candidate_sort_key)[:per_group_limit]
        for group_id, group_rows in by_group.items()
    }
    selected: list[dict[str, Any]] = []
    for rank in range(per_group_limit):
        for group_id in sorted(ranked_groups):
            group_rows = ranked_groups[group_id]
            if rank < len(group_rows):
                selected.append(group_rows[rank])
                if len(selected) == global_limit:
                    break
        if len(selected) == global_limit:
            break
    selected_ids = {id(row) for row in selected}
    for row in candidates:
        if id(row) in selected_ids:
            continue
        row["model_adjudication_required"] = False
        row["model_prefilter_disposition"] = "context_only"
        row["model_prefilter_reason"] = "outside_bounded_diverse_quantity_review_budget"
    return report, {
        "schema_id": "quantity_model_candidate_prefilter_report_v1",
        "status": "bounded" if len(selected) < len(candidates) else "all_candidates_selected",
        "initial_candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "prefiltered_context_only_count": len(candidates) - len(selected),
        "group_count": len(by_group),
        "per_group_limit": per_group_limit,
        "global_limit": global_limit,
    }


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    role_rank = {
        "quantitative_anchor": 0,
        "load_bearing_primary_support": 1,
        "load_bearing_counterweight": 2,
        "decision_crux": 3,
        "scope_or_applicability": 4,
        "mechanism_or_context": 5,
        "background_only": 6,
    }
    return (
        role_rank.get(str(row.get("memo_role") or ""), 7),
        0 if isinstance(row.get("assertion_bundle"), dict) and row["assertion_bundle"] else 1,
        len(_list(row.get("deterministic_warnings"))),
        str(row.get("candidate_id") or ""),
    )


def _limit(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
