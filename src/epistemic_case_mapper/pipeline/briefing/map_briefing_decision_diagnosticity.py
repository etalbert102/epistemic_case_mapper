from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


MEMO_USE_SCORE = {
    "load_bearing_primary_support": 60,
    "load_bearing_counterweight": 60,
    "quantitative_anchor": 58,
    "decision_crux": 54,
    "scope_or_applicability": 48,
    "mechanism_or_context": 24,
    "background_only": 8,
}

ROLE_SCORE = {
    "load_bearing_primary_support": 16,
    "load_bearing_counterweight": 18,
    "quantitative_anchor": 18,
    "decision_crux": 16,
    "scope_or_applicability": 12,
    "mechanism_or_context": 4,
    "background_only": 0,
    "needs_human_or_model_review": 0,
}


def apply_decision_diagnostic_ranking(
    groups: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rank model groups by existing decision judgments and quantity anchors.

    This is a guardrail around model ordering, not a new semantic classifier. It
    reuses upstream analyst/adjudication fields and source-bound quantities to
    prevent generic contextual support from outranking evidence that was already
    judged load-bearing for the decision.
    """
    row_by_id = {
        str(row.get("evidence_item_id") or "").strip(): row
        for row in evidence_rows
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    ranked = []
    changes = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        updated = dict(group)
        score, reasons, best_rank = _group_score(updated, row_by_id)
        ranked.append((updated, index, score, reasons, best_rank))
    ranked.sort(key=lambda pair: (-pair[2], _original_rank(pair[0]), pair[1], str(pair[0].get("group_id") or "")))
    reranked = []
    for new_rank, (group, original_index, score, reasons, best_rank) in enumerate(ranked, start=1):
        old_rank = _original_rank(group)
        updated = dict(group)
        updated["importance_rank"] = new_rank
        reranked.append(updated)
        if new_rank != old_rank:
            changes.append(
                {
                    "group_id": updated.get("group_id"),
                    "from_importance_rank": old_rank,
                    "to_importance_rank": new_rank,
                    "original_order": original_index + 1,
                    "diagnostic_priority_score": score,
                    "diagnostic_priority_reasons": reasons,
                    "best_adjudicated_importance_rank": best_rank,
                }
            )
    return reranked, {
        "schema_id": "decision_diagnostic_ranking_guard_v1",
        "method": "reuse_adjudicated_importance_and_source_bound_quantities",
        "group_count": len(reranked),
        "changed_group_count": len(changes),
        "changes": changes[:40],
    }


def apply_obligation_budget(evidence_items: list[dict[str, Any]]) -> None:
    budgets = {
        "strongest_support": 4,
        "quantitative_anchor": 2,
        "strongest_counterweight": 3,
        "scope_boundary": 2,
        "decision_crux": 2,
    }
    by_role: dict[str, list[dict[str, Any]]] = {}
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict):
            continue
        item["_original_order"] = index
        by_role.setdefault(str(item.get("role") or ""), []).append(item)
    for role, items in by_role.items():
        if role == "context_only":
            continue
        preexisting_required_ids = {
            id(item)
            for item in items
            if item.get("obligation_level") == "must_include" or item.get("must_use") is True
        }
        forced_ids = {
            id(item)
            for item in items
            if str(item.get("memo_inclusion") or "") == "memo_spine"
        }
        eligible = [
            item
            for item in items
            if str(item.get("memo_inclusion") or "") not in {"trace_only", "exclude", "supporting_context"}
        ]
        ordered = sorted(eligible, key=_obligation_budget_sort_key)
        budget = budgets.get(role, 2)
        budget_selected_ids = {id(item) for item in ordered[:budget]}
        required_ids = {*preexisting_required_ids, *budget_selected_ids}
        required_ids.update(forced_ids)
        for item in items:
            if id(item) in required_ids:
                item["obligation_level"] = "must_include"
                item["must_use"] = True
                if id(item) in preexisting_required_ids and id(item) not in budget_selected_ids and id(item) not in forced_ids:
                    item["obligation_budget_overflow"] = True
                    item["obligation_budget_role_cap"] = budget
                else:
                    item.pop("obligation_budget_overflow", None)
                    item.pop("obligation_budget_role_cap", None)
    for item in evidence_items:
        item.pop("_original_order", None)


def decision_unit_diagnosticity(
    unit: dict[str, Any],
    *,
    adjudication_by_id: dict[str, dict[str, Any]],
    quantity_plan: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evidence_ids = _string_list(_dict(unit.get("lineage")).get("covered_evidence_item_ids"))
    best_rank = 100
    score = 0
    reasons = []
    for evidence_id in evidence_ids:
        row = _dict(adjudication_by_id.get(evidence_id))
        memo_use = str(row.get("memo_use") or "").strip()
        rank = _int_value(row.get("importance_rank"), 100)
        best_rank = min(best_rank, rank)
        if memo_use in {"load_bearing_primary_support", "load_bearing_counterweight", "quantitative_anchor"}:
            score += 48
            reasons.append(f"adjudicated:{memo_use}")
        elif memo_use in {"decision_crux", "scope_or_applicability"}:
            score += 36
            reasons.append(f"adjudicated:{memo_use}")
        elif memo_use:
            score += 8
            reasons.append(f"adjudicated:{memo_use}")
        if rank < 100:
            score += max(0, 34 - min(rank, 34))
            reasons.append(f"rank:{rank}")
    if [row for row in quantity_plan.values() if bool(row.get("must_retain"))]:
        score += 28
        reasons.append("must_retain_quantity")
    elif _list(unit.get("quantities")):
        score += 10
        reasons.append("source_bound_quantity")
    role = str(unit.get("role") or "").strip()
    if role in {"strongest_counterweight", "quantitative_anchor"}:
        score += 8
    elif role == "strongest_support":
        score += 6
    elif role == "context_only":
        score = min(score, 42)
        reasons.append("contextual_role_cap")
    return {
        "schema_id": "decision_unit_diagnosticity_v1",
        "score": score,
        "best_adjudicated_importance_rank": best_rank,
        "reasons": _dedupe(reasons)[:8],
    }


def _group_score(group: dict[str, Any], row_by_id: dict[str, dict[str, Any]]) -> tuple[int, list[str], int]:
    evidence_ids = _string_list(group.get("covered_evidence_item_ids"))
    rows = [_dict(row_by_id.get(evidence_id)) for evidence_id in evidence_ids]
    best_row_score = 0
    best_rank = 100
    reasons: list[str] = []
    for row in rows:
        score = 0
        memo_use = str(row.get("adjudicated_memo_use") or row.get("memo_use") or "").strip()
        if memo_use:
            score += MEMO_USE_SCORE.get(memo_use, 0)
            reasons.append(f"adjudicated:{memo_use}")
        rank = _int_value(row.get("adjudicated_importance_rank") or row.get("importance_rank") or row.get("current_priority"), 100)
        best_rank = min(best_rank, rank)
        if rank < 100:
            score += max(0, 42 - min(rank, 42))
            reasons.append(f"rank:{rank}")
        quantities = _quantity_values(row)
        if quantities:
            score += 18
            reasons.append("source_bound_quantities")
        if any(_looks_decision_anchor_quantity(quantity) for quantity in quantities):
            score += 8
            reasons.append("decision_anchor_quantity_shape")
        best_row_score = max(best_row_score, score)
    role = str(group.get("memo_role") or "").strip()
    score = best_row_score + ROLE_SCORE.get(role, 0)
    if _string_list(group.get("quantity_values")):
        score += 8
        reasons.append("group_quantities")
    if role in {"mechanism_or_context", "background_only", "needs_human_or_model_review"}:
        score = min(score, 72)
        reasons.append("contextual_role_cap")
    return score, _dedupe(reasons)[:8], best_rank


def _obligation_budget_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int]:
    rank = _int_value(item.get("importance_rank"), 999)
    diagnosticity = _dict(item.get("decision_diagnosticity"))
    score = _int_value(diagnosticity.get("score"), 0)
    best_adjudicated_rank = _int_value(diagnosticity.get("best_adjudicated_importance_rank"), rank)
    return (-score, best_adjudicated_rank, rank, _int_value(item.get("_original_order"), 0))


def _quantity_values(row: dict[str, Any]) -> list[str]:
    values = _string_list(row.get("quantity_values"))
    for quantity in _list(row.get("claim_quantities")):
        if isinstance(quantity, dict):
            values.extend(_string_list(quantity.get("value")))
    return _dedupe(values)


def _looks_decision_anchor_quantity(value: str) -> bool:
    text = str(value or "").lower()
    return any(
        token in text
        for token in (
            "hazard ratio",
            "relative risk",
            "odds ratio",
            "confidence interval",
            "risk",
            "effect",
            "reduction",
            "increase",
            "%",
        )
    )


def _original_rank(group: dict[str, Any]) -> int:
    return _int_value(group.get("importance_rank"), 100)


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
