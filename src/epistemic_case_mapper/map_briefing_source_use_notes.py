from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def source_use_note_for_entry(entry: dict[str, str], packet: dict[str, Any]) -> str:
    source_id = str(entry.get("source_id") or "").strip()
    if not source_id:
        return ""
    parts = []
    judgment = _source_weight_judgments_by_source(packet).get(source_id)
    if judgment:
        use = _readable_main_use(judgment.get("main_use"))
        if use and use != "unspecified":
            parts.append(f"use: {use}")
        limits = _dedupe(
            _readable_warning(item)
            for item in (
                _string_list(judgment.get("reader_facing_limit"))
                or _string_list(judgment.get("what_not_to_use_it_for"))
            )
            if item
        )
        if limits:
            parts.append("limit: " + "; ".join(limits[:2]))
    language = _language_contracts_by_source(packet).get(source_id)
    if language and not any(part.startswith("limit:") for part in parts):
        avoid = _string_list(language.get("avoid_language"))
        if avoid:
            parts.append("wording limit: avoid " + ", ".join(avoid[:2]))
    return "; ".join(parts)


def _source_weight_judgments_by_source(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    judgments = _list(canonical.get("source_weight_judgments"))
    by_source: dict[str, dict[str, Any]] = {}
    for judgment in judgments:
        if not isinstance(judgment, dict):
            continue
        for source_id in _string_list(judgment.get("source_ids")):
            by_source[source_id] = judgment
    return by_source


def _language_contracts_by_source(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    by_source: dict[str, dict[str, Any]] = {}
    for row in _list(canonical.get("evidence_language_contracts")):
        if not isinstance(row, dict):
            continue
        for source_id in _string_list(row.get("source_ids")):
            by_source.setdefault(source_id, row)
    return by_source


def _readable_main_use(value: Any) -> str:
    return str(value or "unspecified").replace("_", " ")


def _readable_warning(warning: str) -> str:
    warning = str(warning or "").strip()
    if warning == "quality_limit":
        return "weak, indirect, or unknown evidence-quality status"
    return warning.replace("_", " ")
