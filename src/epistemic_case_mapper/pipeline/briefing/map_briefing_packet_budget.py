from __future__ import annotations

from collections import Counter
from typing import Any


PROTECTED_INVARIANTS = (
    "exact_quantity_text",
    "directionality",
    "source_id",
    "source_label",
    "applicability_limit",
    "uncertainty_qualifier",
    "candidate_answer_linkage",
    "obligation_id",
    "slot_id",
    "evidence_quality_warning",
)

DEFAULT_BUCKET_ORDER = (
    "answer_frame_and_candidate_answers",
    "load_bearing_evidence",
    "counterevidence",
    "quantitative_anchors",
    "scope_and_applicability",
    "cruxes_and_named_gaps",
    "source_quality_cautions",
    "mechanism_and_context",
)


def build_packet_budget_allocation_report(
    *,
    candidate_answer_set: dict[str, Any],
    decision_slot_inventory: dict[str, Any],
    evidence_answer_matrix: dict[str, Any],
) -> dict[str, Any]:
    slots = [row for row in decision_slot_inventory.get("slots", []) if isinstance(row, dict)]
    matrix_rows = [row for row in evidence_answer_matrix.get("rows", []) if isinstance(row, dict)]
    allocations = [_allocation(bucket, slots, matrix_rows, candidate_answer_set) for bucket in DEFAULT_BUCKET_ORDER]
    return {
        "schema_id": "packet_budget_allocation_report_v1",
        "method": "obligation_aware_report_only_packet_budget",
        "allocations": allocations,
        "protected_invariants": list(PROTECTED_INVARIANTS),
        "warnings": _budget_warnings(allocations),
    }


def build_packet_compression_report(
    *,
    decision_slot_inventory: dict[str, Any],
    evidence_answer_matrix: dict[str, Any],
) -> dict[str, Any]:
    rows = [row for row in evidence_answer_matrix.get("rows", []) if isinstance(row, dict)]
    slots = [row for row in decision_slot_inventory.get("slots", []) if isinstance(row, dict)]
    missing = _missing_invariants(rows, slots)
    return {
        "schema_id": "packet_compression_report_v1",
        "method": "report_only_compression_invariant_check",
        "protected_invariants": list(PROTECTED_INVARIANTS),
        "missing_invariant_count": len(missing),
        "missing_invariants": missing[:50],
        "status": "warning" if missing else "ready",
        "warnings": ["compression_invariants_missing"] if missing else [],
    }


def _allocation(bucket: str, slots: list[dict[str, Any]], matrix_rows: list[dict[str, Any]], candidate_answer_set: dict[str, Any]) -> dict[str, Any]:
    slot_types = _bucket_slot_types(bucket)
    relevant_slots = [slot for slot in slots if slot.get("slot_type") in slot_types]
    relevant_matrix = [row for row in matrix_rows if _row_matches_bucket(row, bucket)]
    return {
        "bucket": bucket,
        "priority": _bucket_priority(bucket),
        "slot_count": len(relevant_slots),
        "matrix_row_count": len(relevant_matrix),
        "candidate_answer_count": (
            int(candidate_answer_set.get("candidate_answer_count", 0) or 0)
            if bucket == "answer_frame_and_candidate_answers"
            else 0
        ),
        "budget_policy": _budget_policy(bucket),
        "status": "represented" if relevant_slots or relevant_matrix or bucket == "answer_frame_and_candidate_answers" else "empty_report_only",
    }


def _bucket_slot_types(bucket: str) -> set[str]:
    return {
        "load_bearing_evidence": {"answer_support"},
        "counterevidence": {"counterevidence"},
        "quantitative_anchors": {"quantitative_anchor"},
        "scope_and_applicability": {"scope_boundary"},
        "cruxes_and_named_gaps": {"decision_crux", "named_gap"},
        "source_quality_cautions": {"source_quality_caution"},
        "mechanism_and_context": {"mechanism_or_context"},
    }.get(bucket, set())


def _row_matches_bucket(row: dict[str, Any], bucket: str) -> bool:
    role = str(row.get("evidence_role", ""))
    if bucket == "load_bearing_evidence":
        return role == "answer_support"
    if bucket == "counterevidence":
        return role == "counterevidence"
    if bucket == "quantitative_anchors":
        return role == "quantitative_anchor"
    if bucket == "scope_and_applicability":
        return role == "scope_boundary"
    if bucket == "source_quality_cautions":
        return str(row.get("evidence_quality", "")) in {"", "unknown", "not_assessed_in_minimal_slice"}
    return False


def _bucket_priority(bucket: str) -> int:
    return {bucket_name: index + 1 for index, bucket_name in enumerate(DEFAULT_BUCKET_ORDER)}.get(bucket, 99)


def _budget_policy(bucket: str) -> str:
    return {
        "answer_frame_and_candidate_answers": "Always preserve the decision question, candidate answers, and default answer frame.",
        "load_bearing_evidence": "Reserve space for the highest-salience support rows for each candidate answer.",
        "counterevidence": "Reserve space for strongest challenges or limiting evidence.",
        "quantitative_anchors": "Reserve space for exact top quantities with source lineage and uncertainty.",
        "scope_and_applicability": "Reserve space for subgroup, comparator, dose, endpoint, and applicability limits.",
        "cruxes_and_named_gaps": "Reserve space for answer-changing uncertainties and explicit gaps.",
        "source_quality_cautions": "Reserve space for quality warnings when they affect weighting.",
        "mechanism_and_context": "Use remaining budget for explanatory context by marginal decision value.",
    }.get(bucket, "Report-only budget bucket.")


def _missing_invariants(rows: list[dict[str, Any]], slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for row in rows:
        row_id = str(row.get("matrix_row_id", ""))
        if row.get("evidence_role") == "quantitative_anchor" and not row.get("quantity_values"):
            missing.append({"target_id": row_id, "invariant": "exact_quantity_text"})
        if not row.get("source_ids") and not row.get("source_labels"):
            missing.append({"target_id": row_id, "invariant": "source_id_or_label"})
        if not row.get("candidate_answer_id"):
            missing.append({"target_id": row_id, "invariant": "candidate_answer_linkage"})
        if not row.get("obligation_ids"):
            missing.append({"target_id": row_id, "invariant": "obligation_id"})
    for slot in slots:
        if not slot.get("obligation_ids"):
            missing.append({"target_id": slot.get("slot_id"), "invariant": "slot_obligation_id"})
    return missing


def _budget_warnings(allocations: list[dict[str, Any]]) -> list[str]:
    counts = Counter(row["status"] for row in allocations)
    return ["empty_budget_buckets"] if counts.get("empty_report_only") else []
