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
        "section_views": packet.get("section_views", []),
        "source_trail": packet.get("source_trail", [])[:24],
        "coverage_report": packet.get("coverage_report", {}),
    }
