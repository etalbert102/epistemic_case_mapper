from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_selection import select_memo_ready_items


def test_memo_ready_selection_caps_role_dominance_and_reports_overflow() -> None:
    mandatory = [
        {"item_id": f"counter_{index}", "role": "strongest_counterweight", "must_use": True}
        for index in range(8)
    ] + [
        {"item_id": "support_1", "role": "strongest_support", "must_use": True},
        {"item_id": "quant_1", "role": "quantitative_anchor", "must_use": True},
    ]

    selected, report = select_memo_ready_items(mandatory, [])

    selected_counterweights = [item for item in selected if item["role"] == "strongest_counterweight"]
    assert len(selected_counterweights) == 5
    assert report["overflow_count"] == 3
    assert report["status"] == "warning"
    assert all(row["reason"] == "role_cap_overflow" for row in report["overflow_items"])


def test_memo_ready_selection_fills_context_with_budget() -> None:
    mandatory = [{"item_id": "support_1", "role": "strongest_support", "must_use": True}]
    context = [{"item_id": f"context_{index}", "role": "context_only", "must_use": False} for index in range(30)]

    selected, report = select_memo_ready_items(mandatory, context)

    assert len(selected) == 18
    assert selected[0]["item_id"] == "support_1"
    assert report["overflow_count"] == 13
