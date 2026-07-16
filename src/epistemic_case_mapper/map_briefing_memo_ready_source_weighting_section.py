from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def build_source_weighting_raw_section(reader_packet: dict[str, Any]) -> dict[str, Any]:
    judgments = [row for row in _list(reader_packet.get("source_weighting")) if isinstance(row, dict)]
    if not judgments:
        return {}
    evidence_by_id = _reader_packet_evidence_by_id(reader_packet)
    evidence_ids = _dedupe([
        evidence_id
        for judgment in judgments
        for evidence_id in _string_list(judgment.get("evidence_item_ids"))
    ])
    evidence_context = [evidence_by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in evidence_by_id]
    return _drop_empty(
        {
            "section": "How to Weight the Evidence",
            "writing_job": "Explain how a reader should weight the source base before reading the detailed evidence argument.",
            "required_points": [
                "Name the sources or source families that should carry the answer.",
                "Name sources that mainly calibrate, bound, or contextualize the answer.",
                "Explain the major use limits compactly so the reader does not over-read weaker evidence.",
            ],
            "evidence_context": evidence_context[:12],
            "source_weighting": judgments,
        }
    )


def _reader_packet_evidence_by_id(reader_packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    supplemental = _dict(reader_packet.get("supplemental_evidence"))
    rows.extend(row for row in _list(supplemental.get("priority_evidence")) if isinstance(row, dict))
    inventory = _dict(supplemental.get("inventory"))
    for lane_rows in _dict(inventory.get("lanes")).values():
        rows.extend(row for row in _list(lane_rows) if isinstance(row, dict))
    for raw in _list(reader_packet.get("section_writing_packets")):
        if not isinstance(raw, dict):
            continue
        rows.extend(row for row in _list(raw.get("evidence_context")) if isinstance(row, dict))
        rows.extend(row for row in _list(raw.get("retention_requirements")) if isinstance(row, dict))
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row.get("item_id") or row.get("requirement_id") or "").strip()
        if item_id and item_id not in by_id:
            by_id[item_id] = row
    return by_id


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
