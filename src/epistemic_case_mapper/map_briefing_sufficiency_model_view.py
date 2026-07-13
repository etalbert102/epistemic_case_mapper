from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import string_list as _string_list
from epistemic_case_mapper.map_briefing_source_identity import (
    project_source_text_to_ids_for_model,
    project_sources_to_ids_for_model,
    source_id_alias_map,
)


def sufficiency_report_for_model(sufficiency_report: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    source_trail = packet.get("source_trail", []) if isinstance(packet.get("source_trail"), list) else []
    projected = project_sources_to_ids_for_model(sufficiency_report, source_trail)
    source_terms = {
        _normalize_source_term(alias)
        for alias, source_id in source_id_alias_map(source_trail).items()
        if alias and alias != source_id
    }
    return project_source_text_to_ids_for_model(_strip_source_terms(projected, source_terms), source_trail)


def _strip_source_terms(value: Any, source_terms: set[str]) -> Any:
    if isinstance(value, list):
        rows = []
        for item in value:
            cleaned_item = _strip_source_terms(item, source_terms)
            if cleaned_item not in ("", None, []):
                rows.append(cleaned_item)
        return rows
    if not isinstance(value, dict):
        return value
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"required_terms", "missing_required_terms", "validation_terms"}:
            terms = [term for term in _string_list(item) if _normalize_source_term(term) not in source_terms]
            if terms:
                cleaned[key] = terms
            continue
        cleaned_item = _strip_source_terms(item, source_terms)
        if cleaned_item not in ("", None, [], {}):
            cleaned[key] = cleaned_item
    return cleaned


def _normalize_source_term(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())
