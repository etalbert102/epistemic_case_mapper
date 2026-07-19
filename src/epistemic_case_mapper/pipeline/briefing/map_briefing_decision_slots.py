from __future__ import annotations

from collections import Counter
from typing import Any


SLOT_TYPE_BY_OBLIGATION = {
    "answer_support": "answer_support",
    "counterevidence": "counterevidence",
    "quantitative_anchor": "quantitative_anchor",
    "scope_boundary": "scope_boundary",
    "source_quality_caution": "source_quality_caution",
    "named_gap": "named_gap",
}


def build_decision_slot_inventory(
    *,
    decision_obligation_graph: dict[str, Any],
    evidence_answer_matrix: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    matrix_rows = _matrix_rows_by_obligation(evidence_answer_matrix)
    for obligation in _obligations(decision_obligation_graph):
        obligation_id = str(obligation.get("obligation_id", "")).strip()
        if not obligation_id:
            continue
        linked_rows = matrix_rows.get(obligation_id, [])
        rows.append(
            {
                "slot_id": f"slot_{len(rows)+1:03d}",
                "slot_type": SLOT_TYPE_BY_OBLIGATION.get(str(obligation.get("obligation_type")), "named_gap"),
                "obligation_ids": [obligation_id],
                "candidate_answer_ids": _string_list(obligation.get("candidate_answer_ids")),
                "requiredness": obligation.get("requiredness", "required"),
                "expected_evidence_features": _string_list(obligation.get("expected_evidence_features")),
                "matrix_row_ids": [str(row.get("matrix_row_id")) for row in linked_rows if row.get("matrix_row_id")][:12],
                "evidence_node_ids": _dedupe(
                    [
                        *_string_list(obligation.get("evidence_node_ids")),
                        *[str(row.get("evidence_node_id")) for row in linked_rows if row.get("evidence_node_id")],
                    ]
                )[:12],
                "compression_guidance": _compression_guidance(str(obligation.get("obligation_type"))),
                "status": "filled" if linked_rows or _string_list(obligation.get("evidence_node_ids")) else "unfilled_report_only",
            }
        )
    counts = Counter(row["slot_type"] for row in rows)
    return {
        "schema_id": "decision_slot_inventory_v1",
        "method": "derived_from_decision_obligations_and_evidence_answer_matrix",
        "slots": rows,
        "slot_count": len(rows),
        "slot_type_counts": dict(sorted(counts.items())),
        "unfilled_slot_ids": [row["slot_id"] for row in rows if row["status"] != "filled"],
        "warnings": ["unfilled_required_slots"] if any(row["status"] != "filled" and row["requiredness"] == "required" for row in rows) else [],
    }


def _matrix_rows_by_obligation(matrix: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in matrix.get("rows", []) if isinstance(matrix.get("rows"), list) else []:
        if not isinstance(row, dict):
            continue
        for obligation_id in _string_list(row.get("obligation_ids")):
            grouped.setdefault(obligation_id, []).append(row)
    return grouped


def _obligations(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in graph.get("obligations", []) if isinstance(row, dict)] if isinstance(graph.get("obligations"), list) else []


def _compression_guidance(obligation_type: str) -> str:
    return {
        "answer_support": "Preserve source, direction, and why this evidence bears on the candidate answer.",
        "counterevidence": "Preserve the challenged answer and the limiting or contrary condition.",
        "quantitative_anchor": "Preserve exact quantity text, source lineage, uncertainty, and claim context.",
        "scope_boundary": "Preserve population, dose, comparator, endpoint, or applicability limit.",
        "source_quality_caution": "Preserve quality warning and source lineage.",
    }.get(obligation_type, "Name the gap or uncertainty explicitly.")


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
