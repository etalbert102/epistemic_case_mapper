from __future__ import annotations

from typing import Any


def packet_summary_for_model(packet: dict[str, Any], *, max_bundles: int = 18) -> dict[str, Any]:
    """Return a compact, model-facing view for critique/refinement/writing."""

    bundles = [
        row
        for row in packet.get("evidence_bundles", [])
        if isinstance(row, dict) and not row.get("synthesis_suppressed")
    ]
    retain_rows = [
        row
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
