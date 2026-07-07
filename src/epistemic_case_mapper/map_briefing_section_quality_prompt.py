from __future__ import annotations

from typing import Any


def section_quality_guidance(model_contract: dict[str, Any]) -> str:
    packet = model_contract.get("model_section_packet", {}) if isinstance(model_contract.get("model_section_packet"), dict) else {}
    rows = [
        row
        for key in ("owned_evidence", "reference_only_evidence")
        for row in packet.get(key, []) if isinstance(packet.get(key), list)
        if isinstance(row, dict)
    ]
    markers = _quality_markers(rows)
    if not markers:
        return "No low-weight evidence markers are present; still distinguish support, counterweight, scope, and method limits."
    return "Make these quality limits visible in prose without adding new facts: " + "; ".join(markers[:8]) + "."


def _quality_markers(rows: list[dict[str, Any]]) -> list[str]:
    markers: list[str] = []
    for row in rows:
        label = str(row.get("candidate_card_id") or row.get("spine_field_id") or row.get("source") or "evidence")
        quality = str(row.get("quality", "")).strip().lower()
        if quality in {"weak", "indirect", "unknown"}:
            markers.append(f"{label} is {quality} evidence")
        for limit in _string_list(row.get("limitations")):
            markers.append(_limit_marker(label, limit))
    return _dedupe([marker for marker in markers if marker])


def _limit_marker(label: str, limit: str) -> str:
    if limit in {"role_inferred_from_claim_text", "spine_fallback_reason"}:
        return f"{label} has inferred evidence role"
    return f"{label} is limited by {limit}" if limit else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
