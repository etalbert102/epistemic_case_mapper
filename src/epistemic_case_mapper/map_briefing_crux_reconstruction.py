from __future__ import annotations

from typing import Any


def reconstruct_decision_crux_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    support = _first_role(items, {"strongest_support", "quantitative_anchor"})
    counter = _first_role(items, {"strongest_counterweight"})
    current_cruxes = [item for item in items if item.get("role") == "decision_crux"]
    if not support or not counter:
        return items, _report("skipped", "missing_support_or_counterweight", current_cruxes, [])
    if current_cruxes and not any(_weak_crux(item) for item in current_cruxes):
        return items, _report("unchanged", "existing_cruxes_are_structured", current_cruxes, [])
    reconstructed = _crux_item(support, counter)
    filtered = [item for item in items if item.get("role") != "decision_crux" or not _weak_crux(item)]
    filtered.append(reconstructed)
    return filtered, _report("changed", "replaced_weak_topical_crux", current_cruxes, [reconstructed])


def _crux_item(support: dict[str, Any], counter: dict[str, Any]) -> dict[str, Any]:
    support_claim = _short(str(support.get("reader_claim") or ""), 150)
    counter_claim = _short(str(counter.get("reader_claim") or ""), 150)
    source_labels = _dedupe(_strings(support.get("source_labels")) + _strings(counter.get("source_labels")))
    return {
        "item_id": "reconstructed_crux_001",
        "role": "decision_crux",
        "reader_claim": (
            f"Whether the counterevidence that {counter_claim} should outweigh the default-case evidence "
            f"that {support_claim} for the decision-relevant population, endpoint, and scope."
        ),
        "source_label": "; ".join(source_labels[:2]),
        "source_labels": source_labels[:4],
        "must_use": True,
        "decision_relevance": "Names the evidence update most likely to change the default answer.",
        "argument": {
            "grounds": counter_claim,
            "warrant": "The answer changes if the counterevidence is more applicable or more decision-relevant than the default-case support.",
            "backing": "; ".join(source_labels[:2]) or "source-backed claims",
            "rebuttal": support_claim,
        },
        "caveat": "Crux reconstructed from source-backed support and counterweight items.",
        "lineage": {
            "derived_from_claim_ids": _dedupe(_strings(_nested(support, "lineage", "derived_from_claim_ids")) + _strings(_nested(counter, "lineage", "derived_from_claim_ids"))),
            "derived_from_source_ids": _dedupe(_strings(_nested(support, "lineage", "derived_from_source_ids")) + _strings(_nested(counter, "lineage", "derived_from_source_ids"))),
            "assembly_activity": "decision_crux_reconstruction",
            "transformations_applied": ["support_counterweight_crux_projection"],
        },
    }


def _report(
    status: str,
    reason: str,
    original: list[dict[str, Any]],
    reconstructed: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_id": "decision_crux_reconstruction_report_v1",
        "status": status,
        "reason": reason,
        "original_crux_count": len(original),
        "reconstructed_crux_count": len(reconstructed),
        "original_crux_item_ids": [item.get("item_id") for item in original],
        "reconstructed_crux_item_ids": [item.get("item_id") for item in reconstructed],
    }


def _weak_crux(item: dict[str, Any]) -> bool:
    text = str(item.get("reader_claim") or "").lower()
    return " in tension with " in text or " versus " in text or " vs. " in text or not text


def _first_role(items: list[dict[str, Any]], roles: set[str]) -> dict[str, Any]:
    return next((item for item in items if item.get("role") in roles), {})


def _nested(row: dict[str, Any], *keys: str) -> Any:
    current: Any = row
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(row).strip() for row in value if str(row).strip()] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _short(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."
