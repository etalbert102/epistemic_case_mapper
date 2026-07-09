from __future__ import annotations

from typing import Any


def build_decision_packet_views(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "decision_packet_views_v1",
        "method": "projection_views_from_decision_packet_owner_artifacts",
        "synthesis_packet": _synthesis_packet(packet),
        "audit_packet": _audit_packet(packet),
        "source_trace_packet": _source_trace_packet(packet),
        "qa_packet": _qa_packet(packet),
    }


def _synthesis_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "synthesis_packet_v1",
        "decision_question": packet.get("decision_question"),
        "answer_frame": packet.get("answer_frame", {}),
        "candidate_answers": _candidate_answers(packet),
        "evidence_bundles": _synthesis_bundles(packet),
        "decision_slots": _slot_summaries(packet),
        "named_gaps": _named_gaps(packet),
        "budget_allocation": packet.get("packet_budget_allocation_report", {}),
    }


def _audit_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "audit_packet_v1",
        "decision_problem_report": packet.get("decision_problem_report", {}),
        "candidate_answer_set": packet.get("candidate_answer_set", {}),
        "decision_obligation_graph": packet.get("decision_obligation_graph", {}),
        "decision_slots": packet.get("decision_slots", {}),
        "coverage_report": packet.get("coverage_report", {}),
        "packet_compression_report": packet.get("packet_compression_report", {}),
        "vertical_slice_report": packet.get("decision_model_vertical_slice_report", {}),
    }


def _source_trace_packet(packet: dict[str, Any]) -> dict[str, Any]:
    source_graph = packet.get("source_evidence_graph") if isinstance(packet.get("source_evidence_graph"), dict) else {}
    return {
        "schema_id": "source_trace_packet_v1",
        "source_trail": packet.get("source_trail", []),
        "source_graph_summary": source_graph.get("summary", {}),
        "source_nodes": [node for node in source_graph.get("nodes", []) if isinstance(node, dict) and node.get("node_type") == "source"],
        "bundle_lineage": [
            {
                "bundle_id": bundle.get("bundle_id"),
                "source_ids": _string_list(bundle.get("source_ids")),
                "source_labels": _string_list(bundle.get("source_labels")),
                "claim_ids": _string_list(bundle.get("claim_ids")),
                "quantity_ids": _string_list(bundle.get("quantity_ids")),
            }
            for bundle in packet.get("evidence_bundles", [])
            if isinstance(bundle, dict)
        ],
    }


def _qa_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "qa_packet_v1",
        "coverage_report": packet.get("coverage_report", {}),
        "evidence_answer_matrix_quality_report": packet.get("evidence_answer_matrix_quality_report", {}),
        "packet_compression_report": packet.get("packet_compression_report", {}),
        "packet_budget_allocation_report": packet.get("packet_budget_allocation_report", {}),
        "vertical_slice_report": packet.get("decision_model_vertical_slice_report", {}),
    }


def _candidate_answers(packet: dict[str, Any]) -> list[dict[str, Any]]:
    answers = packet.get("candidate_answer_set", {})
    rows = answers.get("candidate_answers", []) if isinstance(answers, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _synthesis_bundles(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bundle in packet.get("evidence_bundles", []) if isinstance(packet.get("evidence_bundles"), list) else []:
        if not isinstance(bundle, dict):
            continue
        rows.append(
            {
                "bundle_id": bundle.get("bundle_id"),
                "decision_role": bundle.get("decision_role"),
                "claim": bundle.get("claim"),
                "source_ids": _string_list(bundle.get("source_ids")),
                "source_labels": _string_list(bundle.get("source_labels")),
                "quantity_values": _string_list(bundle.get("quantity_values")),
                "why_it_matters": bundle.get("why_it_matters"),
                "limits": _string_list(bundle.get("limits")),
                "section_targets": _string_list(bundle.get("section_targets")),
            }
        )
    return rows


def _slot_summaries(packet: dict[str, Any]) -> list[dict[str, Any]]:
    slots = packet.get("decision_slots", {}) if isinstance(packet.get("decision_slots"), dict) else {}
    return [
        {
            "slot_id": slot.get("slot_id"),
            "slot_type": slot.get("slot_type"),
            "obligation_ids": _string_list(slot.get("obligation_ids")),
            "candidate_answer_ids": _string_list(slot.get("candidate_answer_ids")),
            "status": slot.get("status"),
            "matrix_row_ids": _string_list(slot.get("matrix_row_ids")),
            "compression_guidance": slot.get("compression_guidance"),
        }
        for slot in slots.get("slots", [])
        if isinstance(slot, dict)
    ]


def _named_gaps(packet: dict[str, Any]) -> list[dict[str, Any]]:
    slots = packet.get("decision_slots", {}) if isinstance(packet.get("decision_slots"), dict) else {}
    return [
        {"slot_id": slot.get("slot_id"), "slot_type": slot.get("slot_type"), "expected_evidence_features": slot.get("expected_evidence_features", [])}
        for slot in slots.get("slots", [])
        if isinstance(slot, dict) and slot.get("status") != "filled"
    ]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
