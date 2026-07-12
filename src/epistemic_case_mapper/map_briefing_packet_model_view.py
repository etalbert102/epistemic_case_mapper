from __future__ import annotations

from typing import Any


def packet_summary_for_model(packet: dict[str, Any], *, max_bundles: int = 18) -> dict[str, Any]:
    """Return a compact, model-facing view for critique/refinement/writing."""

    bundles = [
        _compact_bundle(row)
        for row in packet.get("evidence_bundles", [])
        if isinstance(row, dict) and not row.get("synthesis_suppressed")
    ]
    retain_rows = [
        _compact_retain(row)
        for row in packet.get("must_retain_ledger", [])
        if isinstance(row, dict) and not row.get("synthesis_suppressed")
    ]
    return {
        "schema_id": "decision_briefing_packet_model_view_v1",
        "decision_question": packet.get("decision_question"),
        "answer_frame": packet.get("answer_frame", {}),
        "must_retain_ledger": retain_rows[:18],
        "evidence_bundles": bundles[:max_bundles],
        "section_summary": _section_summary(packet.get("section_views")),
        "source_trail": packet.get("source_trail", [])[:24],
        "coverage_summary": _coverage_summary(packet.get("coverage_report")),
    }


def _compact_bundle(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "bundle_id",
        "decision_role",
        "weight",
        "directionality",
        "section_use",
        "section_targets",
        "source_ids",
        "source_labels",
        "quantity_values",
        "relation_ids",
    )
    compact = {key: row.get(key) for key in keys if row.get(key) not in (None, "", [])}
    compact["claim"] = _short_text(str(row.get("claim") or ""), 520)
    compact["why_it_matters"] = _short_text(str(row.get("why_it_matters") or ""), 360)
    compact["limits"] = _string_list(row.get("limits"))[:6]
    compact["source_quality"] = _source_quality_summary(row)
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_retain(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "item_id": row.get("item_id"),
            "decision_role": row.get("decision_role"),
            "importance": row.get("importance"),
            "statement": _short_text(str(row.get("statement") or ""), 420),
            "bundle_ids": _string_list(row.get("bundle_ids"))[:12],
            "required_terms": _string_list(row.get("required_terms"))[:10],
            "source_ids": _string_list(row.get("source_ids"))[:8],
            "quantity_ids": _string_list(row.get("quantity_ids"))[:8],
        }.items()
        if value not in (None, "", [], {})
    }


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


def _section_summary(value: Any) -> list[dict[str, Any]]:
    rows = []
    section_rows = value if isinstance(value, list) else []
    for row in section_rows:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "section": row.get("section"),
                "target_count": len(row.get("target_bundle_ids", [])) if isinstance(row.get("target_bundle_ids"), list) else 0,
                "section_use": row.get("section_use"),
            }
        )
    return rows


def _coverage_summary(value: Any) -> dict[str, Any]:
    report = value if isinstance(value, dict) else {}
    keys = (
        "status",
        "warnings",
        "truly_lost_decision_critical_count",
        "truly_lost_moderate_context_count",
        "quantity_missing_count",
        "quantity_obligation_count",
        "primary_bundles_low_question_fit_count",
        "must_retain_without_bundle_count",
    )
    summary = {key: report.get(key) for key in keys if report.get(key) not in (None, "", [])}
    for key in ("truly_lost_decision_critical", "truly_lost_moderate_context"):
        rows = report.get(key)
        if isinstance(rows, list) and rows:
            summary[f"{key}_examples"] = [_compact_coverage_item(row) for row in rows[:4] if isinstance(row, dict)]
    return summary


def _compact_coverage_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "candidate_card_id": row.get("candidate_card_id"),
            "decision_role": row.get("decision_role"),
            "priority": row.get("priority"),
            "claim": _short_text(str(row.get("claim") or ""), 220),
            "quantity_values": row.get("quantity_values", []),
            "source_ids": row.get("source_ids", []),
        }.items()
        if value not in (None, "", [])
    }


def _short_text(text: str, limit: int) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "."


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]
