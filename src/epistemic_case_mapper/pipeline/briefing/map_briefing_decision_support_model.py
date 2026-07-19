from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.decision_argument_artifacts import build_decision_argument_artifacts
from epistemic_case_mapper.pipeline.briefing.decision_frame import build_decision_frame, refine_crux_contract
from epistemic_case_mapper.pipeline.briefing.map_briefing_argument_model import build_argument_model
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_model import (
    build_briefing_plan,
    build_decision_model,
    build_map_sufficiency_report,
    build_proposition_clusters,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_synthesis import build_decision_synthesis_model
from epistemic_case_mapper.pipeline.briefing.map_briefing_evidence_partition import partition_map_evidence
from epistemic_case_mapper.pipeline.briefing.map_briefing_evidence_tables import (
    build_briefing_contract,
    build_concept_evidence_packets,
    build_evidence_compression_table,
    build_evidence_weighting_ledger,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_evidence_cards import (
    apply_evidence_cards_to_ledger,
    apply_evidence_cards_to_map,
    apply_evidence_cards_to_quantity_ledger,
    build_atomic_evidence_cards,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_frame_policy import adapt_decision_model_to_frame, section_policy_for_frame
from epistemic_case_mapper.pipeline.briefing.map_briefing_graph_synthesis import build_graph_synthesis_packet
from epistemic_case_mapper.pipeline.briefing.map_briefing_map_utils import _claims, confidence_cap
from epistemic_case_mapper.pipeline.briefing.map_briefing_quantities import build_quantity_ledger, top_quantity_anchors
from epistemic_case_mapper.pipeline.briefing.map_briefing_reader_contracts import (
    _profile_vocabulary_for_map,
    build_crux_contract,
    build_evidence_slot_ledger,
    build_option_comparison,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_validation import _dedupe, _dedupe_dicts


def build_decision_support_model(
    *,
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
    erosion_audit: dict[str, Any],
    question: str = "",
) -> dict[str, Any]:
    """Build the shared deterministic decision-support bundle used by briefing views."""
    partition = partition_map_evidence(candidate_map, source_lookup)
    evidence_roles = partition["evidence_roles"]
    cruxes = partition["crux_candidates"]
    audit_trail = list(partition["audit_trail"])
    vocabulary = _profile_vocabulary_for_map(candidate_map)
    contract = build_briefing_contract(partition, quality_report, vocabulary=vocabulary)
    evidence_ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup, question=question)
    atomic_cards = build_atomic_evidence_cards(candidate_map, evidence_ledger, source_lookup)
    evidence_ledger = apply_evidence_cards_to_ledger(evidence_ledger, atomic_cards)
    briefing_map = apply_evidence_cards_to_map(candidate_map, atomic_cards)
    quantity_ledger = build_quantity_ledger(briefing_map, source_lookup, question=question)
    quantity_ledger = apply_evidence_cards_to_quantity_ledger(quantity_ledger, atomic_cards)
    partition = partition_map_evidence(briefing_map, source_lookup)
    evidence_roles = partition["evidence_roles"]
    cruxes = partition["crux_candidates"]
    audit_trail = list(partition["audit_trail"])
    contract = build_briefing_contract(partition, quality_report, vocabulary=vocabulary)
    proposition_clusters = build_proposition_clusters(briefing_map, evidence_ledger, source_lookup)
    option_comparison = build_option_comparison(question, evidence_ledger, briefing_map)
    crux_contract = build_crux_contract(briefing_map, evidence_ledger, option_comparison)
    refined_cruxes = refine_crux_contract(crux_contract, briefing_map)
    decision_frame = build_decision_frame(briefing_map, evidence_ledger, quality_report, question=question)
    decision_model = adapt_decision_model_to_frame(
        build_decision_model(proposition_clusters, contract, quality_report, evidence_ledger),
        decision_frame,
    )
    sufficiency_report = build_map_sufficiency_report(
        briefing_map,
        question=question,
        evidence_ledger=evidence_ledger,
        decision_model=decision_model,
        quality_report=quality_report,
    )
    briefing_plan = build_briefing_plan(partition, contract, evidence_ledger, quality_report, decision_model)
    for item in erosion_audit.get("items", []):
        if isinstance(item, dict) and item.get("reader_anchor"):
            audit_trail.append(str(item["reader_anchor"]))
    model = {
        "schema_id": "decision_support_model_v1",
        "question": question,
        "partition": partition,
        "briefing_candidate_map": briefing_map,
        "briefing_contract": contract,
        "evidence_weighting_ledger": evidence_ledger,
        "atomic_evidence_cards": atomic_cards,
        "quantity_ledger": quantity_ledger,
        "quantitative_anchors": quantity_ledger.get("top_quantitative_anchors", top_quantity_anchors(quantity_ledger)),
        "quantitative_evidence_cards": quantity_ledger.get("evidence_cards", []) if isinstance(quantity_ledger.get("evidence_cards"), list) else [],
        "evidence_slot_ledger": build_evidence_slot_ledger(evidence_ledger),
        "proposition_clusters": proposition_clusters,
        "graph_synthesis_packet": build_graph_synthesis_packet(briefing_map, evidence_ledger, source_lookup),
        "evidence_compression_table": build_evidence_compression_table(briefing_map, evidence_ledger, source_lookup),
        "concept_evidence_packets": build_concept_evidence_packets(evidence_ledger),
        "option_comparison": option_comparison,
        "crux_contract": crux_contract,
        "refined_cruxes": refined_cruxes,
        "decision_frame": decision_frame,
        "decision_model": decision_model,
        "map_sufficiency_report": sufficiency_report,
        "briefing_plan": briefing_plan,
        "evidence_roles": {key: _dedupe(items)[:8] for key, items in evidence_roles.items()},
        "crux_candidates": _dedupe_dicts(cruxes)[:8],
        "audit_trail": _dedupe(audit_trail)[:10],
    }
    model["decision_synthesis_model"] = build_decision_synthesis_model(model)
    model["argument_model"] = build_argument_model(briefing_map, quality_report, model, question=question)
    model["decision_argument_artifacts"] = build_decision_argument_artifacts(model, briefing_map)
    return model


def decision_support_scaffold_fields(
    model: dict[str, Any],
    *,
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
    question: str,
) -> dict[str, Any]:
    return {
        "question": question,
        "seed_claims": _claims(candidate_map)[:10],
        "quality_status": quality_report.get("status"),
        "quality_score": quality_report.get("score"),
        "confidence_cap": confidence_cap(quality_report),
        "epistemic_config": candidate_map.get("epistemic_config", {}),
        "section_policy": section_policy_for_frame(model.get("decision_frame", {})),
        "source_display_names": source_lookup,
        "quality_issues": [
            f"{issue.get('severity')}: {issue.get('issue_type')} - {issue.get('message')}"
            for issue in quality_report.get("issues", [])
            if isinstance(issue, dict)
        ][:8],
        "decision_support_model": model,
        **{key: value for key, value in model.items() if key not in {"schema_id", "question", "partition", "briefing_candidate_map"}},
    }
