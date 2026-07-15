from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
from typing import Any

from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet_quality_report
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_source_weight_judgments import build_source_weight_judgment_report


PROJECTION_SCHEMA_ID = "memo_ready_source_id_projection_v1"
SOURCE_KEY_PREFIX = "SRC_"


def project_memo_ready_packet_source_ids(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    """Use opaque source IDs as memo-facing citation keys while preserving source metadata."""
    packet = deepcopy(memo_ready_packet) if isinstance(memo_ready_packet, dict) else {}
    if _dict(packet.get("source_identity_projection")).get("schema_id") == PROJECTION_SCHEMA_ID:
        return packet
    source_trail = [row for row in _list(packet.get("source_trail")) if isinstance(row, dict)]
    mapping = _source_id_projection_map(source_trail)
    if not mapping:
        packet["source_identity_projection"] = _projection_report({}, status="skipped", reason="no_source_trail")
        return packet
    projected = _project_source_references(packet, mapping)
    projected["source_trail"] = [_project_source_trail_row(row, mapping) for row in source_trail]
    projected["source_identity_projection"] = _projection_report(mapping, status="ready", reason="")
    _refresh_canonical_reports(projected)
    return projected


def _source_id_projection_map(source_trail: list[dict[str, Any]]) -> dict[str, str]:
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for source in source_trail:
        original = _source_original_id(source)
        if not original:
            continue
        key = _opaque_source_key(original, used=used)
        used.add(key)
        aliases = _source_alias_values(source, original=original)
        for alias in aliases:
            mapping[alias] = key
    return mapping


def _project_source_trail_row(source: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    original = _source_original_id(source)
    projected_id = mapping.get(original, original)
    row = dict(source)
    row["source_id"] = projected_id
    row["citation_key"] = projected_id
    if original and original != projected_id:
        row.setdefault("source_slug", original)
        row.setdefault("original_source_id", original)
    aliases = _dedupe([*_string_list(row.get("source_aliases")), *_source_alias_values(source, original=original)])
    if aliases:
        row["source_aliases"] = aliases
    return row


def _project_source_references(value: Any, mapping: dict[str, str], *, key: str = "") -> Any:
    if isinstance(value, list):
        return [_project_source_references(item, mapping, key=key) for item in value]
    if not isinstance(value, dict):
        if key in {"source_id", "primary_source_id"}:
            return mapping.get(str(value or "").strip(), value)
        return value
    projected: dict[str, Any] = {}
    for child_key, child_value in value.items():
        if child_key == "source_trail":
            continue
        if child_key == "source_id":
            source_id = str(child_value or "").strip()
            projected[child_key] = mapping.get(source_id, child_value)
            if source_id and source_id != projected[child_key]:
                projected.setdefault("source_slug", source_id)
                projected.setdefault("original_source_id", source_id)
            continue
        if child_key == "source_ids":
            projected[child_key] = _dedupe(mapping.get(source_id, source_id) for source_id in _string_list(child_value))
            continue
        if child_key in {"allowed_citations", "expected_source_ids"}:
            projected[child_key] = _dedupe(mapping.get(source_id, source_id) for source_id in _string_list(child_value))
            continue
        projected[child_key] = _project_source_references(child_value, mapping, key=child_key)
    return projected


def _refresh_canonical_reports(packet: dict[str, Any]) -> None:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    if not canonical:
        return
    judgments = _list(canonical.get("source_weight_judgments"))
    if judgments:
        canonical["source_weight_judgment_report"] = build_source_weight_judgment_report(
            judgments,
            _list(packet.get("source_trail")),
        )
    canonical["quality_report"] = build_canonical_decision_writer_packet_quality_report(canonical)
    packet["canonical_decision_writer_packet"] = canonical
    packet["canonical_decision_writer_packet_quality_report"] = canonical["quality_report"]
    if "source_weight_judgment_report" in canonical:
        packet["source_weight_judgment_report"] = canonical["source_weight_judgment_report"]


def _projection_report(mapping: dict[str, str], *, status: str, reason: str) -> dict[str, Any]:
    canonical_sources = sorted({value for value in mapping.values()})
    report = {
        "schema_id": PROJECTION_SCHEMA_ID,
        "status": status,
        "method": "deterministic_hash_opaque_source_ids",
        "source_count": len(canonical_sources),
        "source_ids": canonical_sources,
        "warnings": [],
    }
    if reason:
        report["reason"] = reason
    return report


def _source_original_id(source: dict[str, Any]) -> str:
    for key in ("original_source_id", "source_slug", "source_id", "source_label"):
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def _source_alias_values(source: dict[str, Any], *, original: str) -> list[str]:
    return _dedupe(
        [
            original,
            str(source.get("source_id") or "").strip(),
            str(source.get("source_slug") or "").strip(),
            str(source.get("original_source_id") or "").strip(),
            str(source.get("source_label") or "").strip(),
            str(source.get("display_label") or "").strip(),
            str(source.get("citation_label") or "").strip(),
            *_string_list(source.get("source_aliases")),
        ]
    )


def _opaque_source_key(original: str, *, used: set[str]) -> str:
    digest = base64.b32encode(hashlib.sha1(str(original).encode("utf-8")).digest()).decode("ascii").rstrip("=")
    for length in (8, 10, 12, 16):
        candidate = f"{SOURCE_KEY_PREFIX}{digest[:length]}"
        if candidate not in used:
            return candidate
    suffix = 2
    while True:
        candidate = f"{SOURCE_KEY_PREFIX}{digest[:12]}_{suffix}"
        if candidate not in used:
            return candidate
        suffix += 1
