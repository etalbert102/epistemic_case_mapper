from __future__ import annotations

from collections import Counter
from typing import Any


def build_decision_model_vertical_slice_report(packet: dict[str, Any]) -> dict[str, Any]:
    bundles = [row for row in packet.get("evidence_bundles", []) if isinstance(row, dict)]
    quantity_bundles = [row for row in bundles if row.get("decision_role") == "quantitative_anchor"]
    matrix = packet.get("evidence_answer_matrix") if isinstance(packet.get("evidence_answer_matrix"), dict) else {}
    source_graph = packet.get("source_evidence_graph") if isinstance(packet.get("source_evidence_graph"), dict) else {}
    slots = packet.get("decision_slots") if isinstance(packet.get("decision_slots"), dict) else {}
    compression = packet.get("packet_compression_report") if isinstance(packet.get("packet_compression_report"), dict) else {}
    budget = packet.get("packet_budget_allocation_report") if isinstance(packet.get("packet_budget_allocation_report"), dict) else {}
    signals = {
        "candidate_answer_count": _count(packet.get("candidate_answer_set"), "candidate_answer_count"),
        "source_graph_node_count": _count(source_graph.get("summary"), "node_count"),
        "source_graph_quantity_node_count": _count(source_graph.get("summary"), "quantity_node_count"),
        "obligation_count": _count(packet.get("decision_obligation_graph"), "obligation_count"),
        "evidence_answer_matrix_row_count": _count(matrix, "row_count"),
        "decision_slot_count": _count(slots, "slot_count"),
        "quantitative_anchor_bundle_count": len(quantity_bundles),
        "protected_top_quantity_bundle_count": sum(1 for row in quantity_bundles if row.get("pretrim_kind") == "quantity_ledger.top_quantitative_anchor"),
        "compression_missing_invariant_count": _count(compression, "missing_invariant_count"),
    }
    return {
        "schema_id": "decision_model_vertical_slice_report_v1",
        "method": "report_only_vertical_slice_completion_and_packet_quality_signals",
        "status": _status(signals),
        "signals": signals,
        "bundle_role_counts": dict(Counter(str(row.get("decision_role", "unknown")) for row in bundles)),
        "budget_bucket_statuses": {
            str(row.get("bucket")): row.get("status")
            for row in budget.get("allocations", [])
            if isinstance(row, dict) and row.get("bucket")
        },
        "warnings": _warnings(signals),
    }


def _status(signals: dict[str, int]) -> str:
    required = (
        "candidate_answer_count",
        "source_graph_node_count",
        "obligation_count",
        "evidence_answer_matrix_row_count",
        "decision_slot_count",
    )
    if all(signals.get(key, 0) > 0 for key in required) and signals.get("quantitative_anchor_bundle_count", 0) > 0:
        return "vertical_slice_operational"
    return "vertical_slice_incomplete"


def _warnings(signals: dict[str, int]) -> list[str]:
    warnings = []
    for key, value in signals.items():
        if key.endswith("_count") and value == 0:
            warnings.append(f"{key}_zero")
    if signals.get("compression_missing_invariant_count", 0) > 0:
        warnings.append("compression_invariants_missing")
    return warnings


def _count(value: Any, key: str) -> int:
    data = value if isinstance(value, dict) else {}
    try:
        return int(data.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0
