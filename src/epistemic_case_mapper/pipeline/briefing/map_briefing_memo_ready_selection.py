from __future__ import annotations

from collections import Counter
from typing import Any


def select_memo_ready_items(
    mandatory: list[dict[str, Any]],
    context: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    role_caps = {
        "quantitative_anchor": 3,
        "strongest_support": 5,
        "strongest_counterweight": 5,
        "scope_boundary": 4,
        "decision_crux": 3,
        "mechanism_or_explanation": 2,
    }
    selected: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for item in mandatory:
        role = str(item.get("role") or "context_only")
        cap = role_caps.get(role, 2)
        if counts[role] < cap:
            selected.append(item)
            counts[role] += 1
        else:
            overflow.append({"item_id": item.get("item_id"), "role": role, "reason": "role_cap_overflow"})
    for item in context:
        if len(selected) >= 18:
            overflow.append({"item_id": item.get("item_id"), "role": item.get("role"), "reason": "packet_item_budget_overflow"})
            continue
        selected.append(item)
    dominant = counts.most_common(1)[0] if counts else ("", 0)
    dominance = round(dominant[1] / max(len(selected), 1), 3) if selected else 0
    return selected, {
        "schema_id": "memo_ready_selection_report_v1",
        "method": "role_capped_mandatory_selection_with_context_fill",
        "selected_item_count": len(selected),
        "overflow_count": len(overflow),
        "role_counts": dict(Counter(str(item.get("role") or "context_only") for item in selected)),
        "role_caps": role_caps,
        "dominant_role": dominant[0],
        "dominant_role_share": dominance,
        "status": "warning" if dominance > 0.55 or overflow else "ready",
        "overflow_items": overflow,
    }
