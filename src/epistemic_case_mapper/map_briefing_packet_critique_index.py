from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_source_identity import source_id_alias_map


def build_packet_critique_index(packet: dict[str, Any], sufficiency_report: dict[str, Any]) -> dict[str, Any]:
    source_terms = _source_terms(_list(packet.get("source_trail")))
    bundles = [_compact_bundle(row) for row in _list(packet.get("evidence_bundles")) if isinstance(row, dict)]
    retain_items = [_compact_retain(row, source_terms=source_terms) for row in _list(packet.get("must_retain_ledger")) if isinstance(row, dict)]
    return {
        "schema_id": "packet_critique_index_v1",
        "decision_question": packet.get("decision_question", ""),
        "answer_frame": _compact_answer_frame(packet.get("answer_frame")),
        "bundle_count": len(bundles),
        "retain_item_count": len(retain_items),
        "bundles": bundles,
        "retain_items": retain_items,
        "coverage_report": packet.get("coverage_report", {}) if isinstance(packet.get("coverage_report"), dict) else {},
        "sufficiency_summary": _compact_sufficiency(sufficiency_report),
    }


def build_packet_critique_shards(index: dict[str, Any], *, max_bundles_per_shard: int = 6) -> list[dict[str, Any]]:
    bundles = [row for row in _list(index.get("bundles")) if isinstance(row, dict)]
    if not bundles:
        return []
    max_size = max(1, int(max_bundles_per_shard))
    shards = []
    for offset in range(0, len(bundles), max_size):
        rows = bundles[offset : offset + max_size]
        shard_id = f"packet_critique_shard_{len(shards) + 1:03d}"
        shards.append(
            {
                "schema_id": "packet_critique_shard_v1",
                "shard_id": shard_id,
                "decision_question": index.get("decision_question", ""),
                "answer_frame": index.get("answer_frame", {}),
                "bundles": rows,
                "retain_items": _retain_items_for_bundles(index, rows),
                "sufficiency_summary": index.get("sufficiency_summary", {}),
                "bundle_ids": [str(row.get("bundle_id", "")) for row in rows if str(row.get("bundle_id", "")).strip()],
            }
        )
    return shards


def compact_global_critique_view(index: dict[str, Any], local_reports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_id": "packet_global_critique_view_v1",
        "decision_question": index.get("decision_question", ""),
        "answer_frame": index.get("answer_frame", {}),
        "bundle_count": index.get("bundle_count", 0),
        "retain_item_count": index.get("retain_item_count", 0),
        "bundle_inventory": [
            {
                "bundle_id": row.get("bundle_id"),
                "decision_role": row.get("decision_role"),
                "weight": row.get("weight"),
                "directionality": row.get("directionality"),
                "section_targets": row.get("section_targets", []),
                "source_ids": row.get("source_ids", []),
                "claim": row.get("claim"),
            }
            for row in _list(index.get("bundles"))
            if isinstance(row, dict)
        ],
        "local_critique_summaries": local_reports,
        "coverage_report": index.get("coverage_report", {}),
        "sufficiency_summary": index.get("sufficiency_summary", {}),
    }


def targets_from_packet(packet: dict[str, Any], target_ids: list[str]) -> dict[str, Any]:
    targets = set(target_ids)
    source_terms = _source_terms(_list(packet.get("source_trail")))
    bundles = [
        _compact_bundle(row)
        for row in _list(packet.get("evidence_bundles"))
        if isinstance(row, dict) and str(row.get("bundle_id", "")) in targets
    ]
    retain = [
        _compact_retain(row, source_terms=source_terms)
        for row in _list(packet.get("must_retain_ledger"))
        if isinstance(row, dict) and str(row.get("item_id", "")) in targets
    ]
    return {"bundles": bundles, "retain_items": retain}


def _compact_bundle(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "bundle_id",
        "decision_role",
        "weight",
        "directionality",
        "section_use",
        "section_targets",
        "source_ids",
        "quantity_values",
        "relation_ids",
    )
    compact = {key: row.get(key) for key in keys if row.get(key) not in (None, "", [])}
    compact["claim"] = _short_text(str(row.get("claim") or ""), 520)
    compact["why_it_matters"] = _short_text(str(row.get("why_it_matters") or ""), 360)
    compact["limits"] = _string_list(row.get("limits"))[:6]
    compact["source_quality"] = _source_quality_summary(row)
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _source_quality_summary(row: dict[str, Any]) -> dict[str, Any]:
    appraisal = row.get("source_appraisal") if isinstance(row.get("source_appraisal"), dict) else {}
    return {
        key: value
        for key, value in {
            "quality": row.get("quality"),
            "warnings": _string_list(row.get("source_use_warnings"))[:4],
            "decision_directness": appraisal.get("decision_directness"),
            "document_types": _string_list(appraisal.get("document_types"))[:4],
            "evidence_proximity": _string_list(appraisal.get("evidence_proximity"))[:4],
            "recommended_uses": _string_list(appraisal.get("recommended_uses"))[:4],
            "interpretation_caveats": [_short_text(str(item), 180) for item in _string_list(appraisal.get("interpretation_caveats"))[:3]],
        }.items()
        if value not in (None, "", [], {})
    }


def _compact_retain(row: dict[str, Any], *, source_terms: set[str]) -> dict[str, Any]:
    return {
        "item_id": row.get("item_id"),
        "importance": row.get("importance"),
        "statement": _short_text(str(row.get("statement") or ""), 420),
        "bundle_ids": _string_list(row.get("bundle_ids"))[:12],
        "required_terms": _non_source_terms(row.get("required_terms"), source_terms)[:10],
    }


def _compact_answer_frame(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: _short_text(str(value.get(key) or ""), 360)
        for key in ("default_answer", "answer", "bottom_line", "confidence", "scope")
        if value.get(key)
    }


def _compact_sufficiency(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "warnings": _list(report.get("warnings"))[:10],
        "truly_lost_decision_critical_count": report.get("truly_lost_decision_critical_count", 0),
        "quantity_missing_count": report.get("quantity_missing_count", 0),
        "missing_required_terms": _string_list(report.get("missing_required_terms"))[:20],
    }


def _retain_items_for_bundles(index: dict[str, Any], bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bundle_ids = {str(row.get("bundle_id", "")) for row in bundles}
    retain = []
    for item in _list(index.get("retain_items")):
        if not isinstance(item, dict):
            continue
        if bundle_ids.intersection(_string_list(item.get("bundle_ids"))):
            retain.append(item)
    return retain[:12]


def _source_terms(source_trail: list[Any]) -> set[str]:
    return {
        _normalize_source_term(alias)
        for alias, source_id in source_id_alias_map(source_trail).items()
        if alias and alias != source_id
    }


def _non_source_terms(value: Any, source_terms: set[str]) -> list[str]:
    return [term for term in _string_list(value) if _normalize_source_term(term) not in source_terms]


def _normalize_source_term(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())
