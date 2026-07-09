from __future__ import annotations

from typing import Any


def reconstruct_decision_crux_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    current_cruxes = [item for item in items if item.get("role") == "decision_crux"]
    if current_cruxes and not any(_weak_crux(item) for item in current_cruxes):
        return items, _report("unchanged", "existing_cruxes_are_structured", current_cruxes)
    if current_cruxes:
        return items, _report("warning", "weak_crux_reported_without_deterministic_rewrite", current_cruxes)
    return items, _report("skipped", "no_decision_crux_items", current_cruxes)


def _report(
    status: str,
    reason: str,
    original: list[dict[str, Any]],
) -> dict[str, Any]:
    weak = [item for item in original if _weak_crux(item)]
    return {
        "schema_id": "decision_crux_reconstruction_report_v1",
        "status": status,
        "reason": reason,
        "original_crux_count": len(original),
        "reconstructed_crux_count": 0,
        "original_crux_item_ids": [item.get("item_id") for item in original],
        "reconstructed_crux_item_ids": [],
        "weak_crux_item_ids": [item.get("item_id") for item in weak],
        "semantic_boundary": "deterministic code reports weak cruxes but does not synthesize replacement cruxes",
    }


def _weak_crux(item: dict[str, Any]) -> bool:
    text = str(item.get("reader_claim") or "").lower()
    return " in tension with " in text or " versus " in text or " vs. " in text or not text
