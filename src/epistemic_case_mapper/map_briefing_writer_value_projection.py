from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_claim_calibration import calibrate_text_for_writer
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import list_value as _list, string_list as _string_list


def drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}


def quantity_values(value: Any, *, evidence: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = []
    for row in _list(value):
        if isinstance(row, dict):
            quantity = str(row.get("value") or "").strip()
            interpretation = str(row.get("interpretation") or "").strip()
            projected = {
                "value": quantity,
                "interpretation": calibrate_text_for_writer(interpretation, evidence or {}),
                "retention_phrase": str(row.get("retention_phrase") or "").strip(),
                "quantity_role": str(row.get("quantity_role") or "").strip(),
                "quantity_id": str(row.get("quantity_id") or "").strip(),
                "source_evidence_item_id": str(row.get("source_evidence_item_id") or "").strip(),
                "source_labels": _string_list(row.get("source_labels")),
                "memo_use": str(row.get("memo_use") or "").strip(),
                "must_retain": bool(row.get("must_retain")) if "must_retain" in row else None,
                "analyst_quantity_relevance": row.get("analyst_quantity_relevance") if isinstance(row.get("analyst_quantity_relevance"), dict) else {},
            }
        else:
            quantity = str(row or "").strip()
            projected = {"value": quantity, "interpretation": ""}
        if quantity:
            rows.append(drop_empty(projected))
    return rows
