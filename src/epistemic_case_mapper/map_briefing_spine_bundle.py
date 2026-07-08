from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_canonical_spine import build_canonical_decision_spine
from epistemic_case_mapper.map_briefing_classical_selection import build_classical_evidence_selection_report
from epistemic_case_mapper.map_briefing_context_reconciliation import (
    build_section_context_decision_packets,
    build_section_context_quality_report,
    build_slot_reconciliation_report,
)
from epistemic_case_mapper.map_briefing_evidence_role_matrix import build_evidence_role_matrix_bundle
from epistemic_case_mapper.map_briefing_spine_arbitration import arbitrate_canonical_decision_spine
from epistemic_case_mapper.map_briefing_spine_audit import build_spine_quality_report
from epistemic_case_mapper.map_briefing_slot_eligibility import build_slot_eligibility_audit
from epistemic_case_mapper.map_briefing_spine_projection import (
    build_section_projection_packets,
    build_section_projection_readiness_report,
)
from epistemic_case_mapper.map_briefing_spine_validation import (
    build_decision_spine_consistency_report,
    validate_canonical_decision_spine,
)


def build_decision_spine_bundle(
    prioritized_map: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    question: str,
    backend: str = "prompt",
    backend_timeout: int | None = None,
    backend_retries: int = 0,
) -> dict[str, Any]:
    classical = build_classical_evidence_selection_report(prioritized_map, scaffold, question=question)
    slot_audit = build_slot_eligibility_audit(scaffold, classical)
    spine = build_canonical_decision_spine(
        prioritized_map,
        scaffold,
        question=question,
        classical_selection_report=classical,
        slot_eligibility_audit=slot_audit,
    )
    arbitration = arbitrate_canonical_decision_spine(
        spine,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    spine = arbitration["spine"]
    spine_validation = validate_canonical_decision_spine(spine)
    consistency = build_decision_spine_consistency_report(spine, slot_audit)
    slot_reconciliation = build_slot_reconciliation_report(spine, slot_audit, scaffold)
    projections = build_section_projection_packets(spine, scaffold)
    section_context_decision_packets = build_section_context_decision_packets(
        projections,
        slot_reconciliation,
        scaffold,
    )
    section_context_quality = build_section_context_quality_report(section_context_decision_packets)
    evidence_role_bundle = build_evidence_role_matrix_bundle(
        candidate_evidence_cards=scaffold.get("candidate_evidence_cards", {})
        if isinstance(scaffold.get("candidate_evidence_cards"), dict)
        else {},
        section_context_decision_packets=section_context_decision_packets,
    )
    readiness = build_section_projection_readiness_report(projections)
    bundle = {
        "classical_evidence_selection_report": classical,
        "claim_cluster_report": classical.get("claim_cluster_report", {}),
        "evidence_centrality_report": classical.get("evidence_centrality_report", {}),
        "coverage_balance_report": classical.get("coverage_balance_report", {}),
        "quantity_outlier_report": classical.get("quantity_outlier_report", {}),
        "slot_eligibility_audit": slot_audit,
        "canonical_decision_spine": spine,
        "canonical_decision_spine_validation": spine_validation,
        "canonical_decision_spine_model_arbitration_report": arbitration["report"],
        "canonical_decision_spine_model_prompt": arbitration["prompt"],
        "canonical_decision_spine_model_raw": arbitration["raw"],
        "decision_spine_consistency_report": consistency,
        "slot_reconciliation_report": slot_reconciliation,
        "section_projection_packets": projections,
        "section_context_decision_packets": section_context_decision_packets,
        **evidence_role_bundle,
        "section_context_quality_report": section_context_quality,
        "section_projection_readiness_report": readiness,
    }
    bundle["spine_quality_report"] = build_spine_quality_report({**scaffold, **bundle})
    return bundle
