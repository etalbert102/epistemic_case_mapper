from __future__ import annotations

from collections import defaultdict
from typing import Any


SLOT_ORDER = (
    "effect_estimate",
    "interval",
    "sample_size",
    "follow_up",
    "dose_or_exposure",
    "estimate_count",
    "absolute_risk_or_difference",
    "other_quantity",
)


def build_quantity_slots(quantities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    slots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for quantity in quantities:
        if not isinstance(quantity, dict):
            continue
        slot = _slot_for_quantity(quantity)
        slots[slot].append(
            {
                key: value
                for key, value in quantity.items()
                if key in {"value", "interpretation", "tuple_id", "tuple_label", "binding_warning"}
                and value not in ("", None, [], {})
            }
        )
    return {slot: slots[slot] for slot in SLOT_ORDER if slots.get(slot)}


def build_quantity_slot_report(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in memo_ready_packet.get("evidence_items", []) if isinstance(item, dict)]
    quantitative = [item for item in items if item.get("role") == "quantitative_anchor"]
    missing = [item.get("item_id") for item in quantitative if item.get("quantities") and not item.get("quantity_slots")]
    slot_counts: dict[str, int] = {}
    for item in quantitative:
        slots = item.get("quantity_slots") if isinstance(item.get("quantity_slots"), dict) else {}
        for slot, values in slots.items():
            slot_counts[slot] = slot_counts.get(slot, 0) + (len(values) if isinstance(values, list) else 0)
    return {
        "schema_id": "quantity_slot_report_v1",
        "status": "warning" if missing else "ready",
        "quantitative_anchor_count": len(quantitative),
        "quantitative_anchor_missing_slots": missing,
        "slot_counts": slot_counts,
    }


def _slot_for_quantity(quantity: dict[str, Any]) -> str:
    value = str(quantity.get("value") or "").lower()
    quantity_type = str(quantity.get("quantity_type") or "").lower()
    if "interval" in quantity_type or "confidence interval" in value or value.startswith("95% ci"):
        return "interval"
    if "sample" in quantity_type or "participant" in value or "people" in value or "subjects" in value:
        return "sample_size"
    if "duration" in quantity_type or "year" in value or "month" in value or "follow" in value:
        return "follow_up"
    if "dose" in quantity_type or "per day" in value or "daily" in value or "threshold" in quantity_type:
        return "dose_or_exposure"
    if "estimate" in quantity_type and any(term in value for term in ("risk estimates", "studies", "trials")):
        return "estimate_count"
    if "absolute" in quantity_type or "ard" in value or "risk difference" in value:
        return "absolute_risk_or_difference"
    if "effect" in quantity_type or any(term in value for term in ("relative risk", "hazard ratio", "odds ratio", " rr ", " hr ")):
        return "effect_estimate"
    return "other_quantity"
