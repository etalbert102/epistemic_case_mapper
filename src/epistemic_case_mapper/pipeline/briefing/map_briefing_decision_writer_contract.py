from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def build_decision_memo_contract(
    *,
    packet: dict[str, Any],
    memo_obligations: dict[str, Any],
    decision_obligation_plan: dict[str, Any],
    writeability: dict[str, Any],
) -> dict[str, Any]:
    required = [row for row in _list(memo_obligations.get("obligations")) if isinstance(row, dict) and row.get("required")]
    return {
        "schema_id": "decision_memo_contract_v1",
        "method": "reuse_first_obligation_contract",
        "decision_question": packet.get("decision_question"),
        "bounded_answer": _dict(packet.get("answer")).get("bounded_answer"),
        "confidence": _dict(packet.get("answer")).get("confidence"),
        "confidence_reasons": _string_list(_dict(packet.get("answer")).get("confidence_reasons")),
        "must_include_obligations": required,
        "must_include_count": len(required),
        "strongest_counterweights": _role_units(packet, "strongest_counterweight"),
        "scope_boundaries": _role_units(packet, "scope_boundary"),
        "decision_cruxes": _role_units(packet, "decision_crux"),
        "missing_evidence": _string_list(packet.get("missing_evidence")),
        "source_trail": _list(packet.get("source_trail")),
        "writeability_status": writeability.get("status"),
        "recommended_synthesis_strategy": writeability.get("recommended_synthesis_strategy"),
        "judgment_lineage": {
            "obligations": decision_obligation_plan.get("source_artifacts_used", []),
            "quantities": ["analyst_quantity_binding_report"],
            "answer": ["global_decision_model"],
        },
    }


def _role_units(packet: dict[str, Any], role: str) -> list[dict[str, Any]]:
    return [
        {
            "unit_id": unit.get("unit_id"),
            "claim": unit.get("claim"),
            "decision_relevance": unit.get("decision_relevance"),
            "source_labels": unit.get("source_labels", []),
        }
        for unit in _list(packet.get("evidence_units"))
        if isinstance(unit, dict) and str(unit.get("role") or "") == role
    ]
