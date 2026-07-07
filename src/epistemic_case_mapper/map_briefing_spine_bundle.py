from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_canonical_spine import build_canonical_decision_spine
from epistemic_case_mapper.map_briefing_classical_selection import build_classical_evidence_selection_report
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
    spine_validation = validate_canonical_decision_spine(spine)
    consistency = build_decision_spine_consistency_report(spine, slot_audit)
    projections = build_section_projection_packets(spine, scaffold)
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
        "decision_spine_consistency_report": consistency,
        "section_projection_packets": projections,
        "section_projection_readiness_report": readiness,
    }
    bundle["spine_quality_report"] = build_spine_quality_report({**scaffold, **bundle})
    return bundle
