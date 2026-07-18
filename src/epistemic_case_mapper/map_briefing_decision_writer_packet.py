from __future__ import annotations

from collections import Counter
from typing import Any

from epistemic_case_mapper.map_briefing_balanced_answer_frame import split_bluf_answer_hierarchy
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_decision_writer_contract import build_decision_memo_contract
from epistemic_case_mapper.map_briefing_decision_diagnosticity import apply_obligation_budget, decision_unit_diagnosticity
from epistemic_case_mapper.map_briefing_decision_writer_helpers import (
    answer_relation_by_evidence_id,
    answer_relation_for_unit,
    effective_writer_role,
    memo_use_by_evidence_id,
    merged_source_appraisal,
)
from epistemic_case_mapper.map_briefing_decision_relevance import (
    analyst_quantity_relevance_plan,
    analyst_relevance_plan,
    combined_relevance_decision,
    serializable_quantity_relevance_plan,
    unit_relevance_decisions,
)
from epistemic_case_mapper.map_briefing_decision_quantity_plan import (
    build_quantity_obligation_plan,
    quantity_fallback_requests,
    quantity_must_retain,
    quantity_plan_by_evidence_value,
    quantity_plan_for_unit,
    quantity_plan_match,
)
from epistemic_case_mapper.map_briefing_memo_obligations import build_memo_obligation_packet
from epistemic_case_mapper.map_briefing_writer_decision_interface import (
    build_writer_decision_interface,
    build_writer_decision_interface_quality_report,
)
from epistemic_case_mapper.map_briefing_production_readiness import (
    build_memo_ready_production_readiness_report,
)
from epistemic_case_mapper.map_briefing_source_claim_context import source_context_fields as _source_context_fields
from epistemic_case_mapper.map_briefing_writer_guidance import compact_writer_guidance_for_model


ROLE_BY_GLOBAL_SECTION = {
    "strongest_support": "strongest_support",
    "strongest_counterargument": "strongest_counterweight",
    "scope_boundaries": "scope_boundary",
    "decision_cruxes": "decision_crux",
    "contextual_evidence": "context_only",
}

SECTION_BY_ROLE = {
    "strongest_support": "support",
    "strongest_counterweight": "counterweight",
    "decision_crux": "crux",
    "scope_boundary": "scope",
    "context_only": "context",
}

def build_decision_writer_packet_bundle(
    *,
    global_decision_model: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    packet = build_decision_writer_packet(global_decision_model=global_decision_model, ledger=ledger)
    quality = build_decision_writer_packet_quality_report(packet, global_decision_model=global_decision_model, ledger=ledger)
    traceability = build_evidence_unit_traceability_matrix(packet, ledger=ledger)
    packet["decision_writer_packet_quality_report"] = quality
    return {
        "decision_writer_packet": packet,
        "decision_writer_packet_quality_report": quality,
        "evidence_unit_traceability_matrix": traceability,
    }


def decision_writer_packet_to_memo_ready_packet(
    decision_writer_packet: dict[str, Any],
    *,
    quality_report: dict[str, Any] | None = None,
    analyst_adjudication: dict[str, Any] | None = None,
    analyst_decision_model: dict[str, Any] | None = None,
    analyst_quantity_binding_report: dict[str, Any] | None = None,
    global_decision_model: dict[str, Any] | None = None,
    writer_guidance_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = decision_writer_packet if isinstance(decision_writer_packet, dict) else {}
    semantic_context = _semantic_context(
        analyst_adjudication=analyst_adjudication,
        analyst_decision_model=analyst_decision_model,
        analyst_quantity_binding_report=analyst_quantity_binding_report,
        global_decision_model=global_decision_model,
    )
    evidence_items = [
        _memo_ready_item_from_unit(index, unit, semantic_context=semantic_context)
        for index, unit in enumerate(_list(packet.get("evidence_units")), start=1)
        if isinstance(unit, dict)
    ]
    apply_obligation_budget(evidence_items)
    decision_obligation_plan = build_decision_obligation_plan(evidence_items, packet=packet, semantic_context=semantic_context)
    writer_guidance = writer_guidance_packet if isinstance(writer_guidance_packet, dict) else {}
    memo_obligations = build_memo_obligation_packet(evidence_items, {"warnings": []}, writer_guidance)
    writeability = build_writer_packet_writeability_report(
        memo_obligations=memo_obligations,
        evidence_items=evidence_items,
        decision_obligation_plan=decision_obligation_plan,
        packet=packet,
        semantic_context=semantic_context,
    )
    decision_contract = build_decision_memo_contract(
        packet=packet,
        memo_obligations=memo_obligations,
        decision_obligation_plan=decision_obligation_plan,
        writeability=writeability,
    )
    answer_hierarchy = _semantic_answer_hierarchy(packet, semantic_context)
    memo_ready = {
        "schema_id": "memo_ready_packet_v1",
        "method": "global_decision_writer_packet_adapter",
        "decision_question": packet.get("decision_question"),
        "answer_spine": {
            "default_read": _dict(packet.get("answer")).get("bounded_answer"),
            "primary_answer": answer_hierarchy["primary_answer"],
            "secondary_detail": answer_hierarchy["secondary_detail"],
            "secondary_detail_type": answer_hierarchy["secondary_detail_type"],
            "full_direct_answer": answer_hierarchy["full_direct_answer"],
            "confidence": _dict(packet.get("answer")).get("confidence", "not_specified"),
            "why_this_read": "; ".join(_string_list(_dict(packet.get("answer")).get("confidence_reasons"))[:3]),
            "synthesis_strategy": "Write directly from the global decision writer packet.",
        },
        "source_trail": _list(packet.get("source_trail")),
        "memo_warning_packet": {},
        "analyst_decision_logic": _dict(packet.get("decision_logic")),
        "analyst_argument_plan": _list(packet.get("argument_plan")),
        "writer_guidance_packet": writer_guidance,
        "compact_writer_guidance": compact_writer_guidance_for_model(writer_guidance),
        "memo_obligations": memo_obligations,
        "decision_obligation_plan": decision_obligation_plan,
        "decision_memo_contract": decision_contract,
        "decision_contract_source_judgment_lineage": decision_contract.get("judgment_lineage", {}),
        "analyst_relevance_plan": semantic_context.get("analyst_relevance_plan", {}),
        "analyst_quantity_relevance_plan": serializable_quantity_relevance_plan(semantic_context.get("analyst_quantity_relevance_plan")),
        "analyst_source_hierarchy": _dict(_dict(semantic_context.get("analyst_decision_model")).get("source_hierarchy")) or _dict(_dict(global_decision_model).get("source_hierarchy")),
        "analyst_source_hierarchy_report": _dict(_dict(semantic_context.get("analyst_decision_model")).get("source_hierarchy_report")) or _dict(_dict(global_decision_model).get("source_hierarchy_report")),
        "analyst_source_weight_judgments": _list(_dict(semantic_context.get("analyst_decision_model")).get("source_weight_judgments")) or _list(_dict(global_decision_model).get("source_weight_judgments")),
        "analyst_source_weight_judgment_report": _dict(_dict(semantic_context.get("analyst_decision_model")).get("source_weight_judgment_report")) or _dict(_dict(global_decision_model).get("source_weight_judgment_report")),
        "writer_packet_writeability_report": writeability,
        "writer_packet_fallback_requests": writeability.get("fallback_requests", []),
        "quantity_obligation_plan": semantic_context.get("quantity_obligation_plan", {}),
        "decision_writer_packet_quality_report": quality_report or packet.get("decision_writer_packet_quality_report", {}),
        "evidence_items": evidence_items,
        "writer_packet": packet,
        "writer_packet_quality_report": quality_report or packet.get("decision_writer_packet_quality_report", {}),
        "decision_synthesis_contract": {
            "schema_id": "decision_synthesis_contract_v1",
            "method": "global_decision_writer_packet_adapter",
            "bounded_answer": _dict(packet.get("answer")).get("bounded_answer"),
            "must_preserve": _contract_must_preserve(evidence_items),
            "required_memo_obligations": [
                obligation for obligation in memo_obligations.get("obligations", []) if obligation.get("required")
            ],
            "decision_memo_contract": decision_contract,
            "writeability_status": writeability.get("status"),
            "warnings": _string_list(_dict(packet.get("global_reconciliation")).get("issues")),
        },
    }
    writer_interface = build_writer_decision_interface(memo_ready)
    memo_ready["writer_decision_interface"] = writer_interface
    memo_ready["writer_decision_interface_quality_report"] = build_writer_decision_interface_quality_report(writer_interface)
    from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet
    memo_ready["canonical_decision_writer_packet"] = canonical = build_canonical_decision_writer_packet(memo_ready, writer_interface=writer_interface)
    memo_ready["canonical_decision_writer_packet_quality_report"] = canonical.get("quality_report", {})
    memo_ready["source_weighting_contract"] = _dict(canonical.get("source_weighting_contract"))
    memo_ready["source_weighting_flow_audit"] = _dict(canonical.get("source_weighting_flow_audit"))
    memo_ready["production_readiness_report"] = build_memo_ready_production_readiness_report(memo_ready)
    return memo_ready


def build_decision_writer_packet(*, global_decision_model: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    ledger_by_id = _ledger_by_id(ledger)
    evidence_units = _evidence_units(global_decision_model, ledger_by_id)
    return {
        "schema_id": "decision_writer_packet_v1",
        "method": "global_decision_model_projection",
        "decision_question": str(global_decision_model.get("decision_question") or ledger.get("decision_question") or "").strip(),
        "answer": {
            "bounded_answer": str(global_decision_model.get("bounded_answer") or "").strip(),
            "confidence": str(global_decision_model.get("confidence") or "not_specified").strip(),
            "confidence_reasons": _string_list(global_decision_model.get("confidence_reasons")),
        },
        "decision_logic": _dict(global_decision_model.get("decision_logic")),
        "argument_plan": _compact_argument_plan(global_decision_model),
        "evidence_units": evidence_units,
        "sections": _sections(evidence_units),
        "source_trail": _source_trail(evidence_units, ledger_by_id),
        "source_aliases": _source_aliases(evidence_units, ledger_by_id),
        "do_not_overstate": _string_list(_dict(global_decision_model.get("decision_logic")).get("do_not_overstate")),
        "missing_evidence": _string_list(global_decision_model.get("missing_evidence")),
        "global_reconciliation": _dict(global_decision_model.get("reconciliation")),
        "writer_guidance": [
            "Use the bounded answer as the stance.",
            "Weigh support, counterweights, scope boundaries, and cruxes as an argument.",
            "Use attached source labels and source-bound quantities when citing load-bearing claims.",
            "Treat missing evidence and reconciliation warnings as uncertainty to explain, not as prose metadata.",
        ],
    }


def _memo_ready_item_from_unit(index: int, unit: dict[str, Any], *, semantic_context: dict[str, Any] | None = None) -> dict[str, Any]:
    semantic_context = semantic_context if isinstance(semantic_context, dict) else {}
    source_labels = _string_list(unit.get("source_labels"))
    relation = answer_relation_for_unit(unit, semantic_context=semantic_context)
    source_role = str(unit.get("role") or "context_only").strip()
    effective_role = effective_writer_role(source_role, relation)
    obligation_unit = {**unit, "role": effective_role}
    obligation = _obligation_for_unit(obligation_unit, semantic_context=semantic_context)
    quantity_plan = quantity_plan_for_unit(unit, semantic_context=semantic_context)
    quantities = _memo_ready_quantities(unit, quantity_plan=quantity_plan)
    diagnosticity = decision_unit_diagnosticity(
        obligation_unit,
        adjudication_by_id=_dict(semantic_context.get("adjudication_by_evidence_id")),
        quantity_plan=quantity_plan,
    )
    relevance = unit_relevance_decisions(unit, semantic_context=semantic_context)
    return {
        "item_id": f"decision_writer_item_{index:03d}",
        "role": effective_role,
        "source_role": source_role,
        "answer_relation": relation["answer_relation"],
        "answer_relation_basis": relation["basis"],
        "reader_claim": str(unit.get("claim") or "").strip(),
        "source_label": source_labels[0] if source_labels else "",
        "source_labels": source_labels,
        "source_ids": [],
        "quantities": quantities,
        "excluded_quantity_values": _excluded_quantity_values(unit, quantity_plan=quantity_plan),
        "lineage": _dict(unit.get("lineage")),
        "decision_relevance": str(unit.get("decision_relevance") or "").strip(),
        "caveat": str(unit.get("caveat") or "").strip(),
        "source_appraisal": _dict(unit.get("source_appraisal")),
        "source_use_warnings": _string_list(unit.get("source_use_warnings")),
        "allowed_wording": _dict(unit.get("allowed_wording")),
        "population": str(unit.get("population") or "").strip(),
        "exposure_or_intervention": str(unit.get("exposure_or_intervention") or "").strip(),
        "outcome_or_endpoint": str(unit.get("outcome_or_endpoint") or "").strip(),
        "evidence_type": str(unit.get("evidence_type") or "").strip(),
        "natural_bottom_line": str(unit.get("natural_bottom_line") or "").strip(),
        "must_preserve_terms": _string_list(unit.get("must_preserve_terms")),
        "claim_context": _dict(unit.get("claim_context")),
        "importance_rank": unit.get("importance_rank"),
        "decision_diagnosticity": diagnosticity,
        "source_memo_role": str(unit.get("source_memo_role") or "").strip(),
        "obligation_level": obligation.get("obligation_level", "optional_context"),
        "memo_function": obligation.get("memo_function", "background"),
        "include_reason": obligation.get("include_reason", ""),
        "demotion_reason": obligation.get("demotion_reason", ""),
        "judgment_lineage": obligation.get("judgment_lineage", []),
        "memo_inclusion": obligation.get("memo_inclusion", ""),
        "memo_inclusion_rationale": obligation.get("memo_inclusion_rationale", ""),
        "analyst_relevance_decisions": relevance,
        "must_use": obligation.get("obligation_level") == "must_include",
    }


def _memo_ready_quantities(unit: dict[str, Any], *, quantity_plan: dict[str, dict[str, Any]] | None = None) -> list[dict[str, str]]:
    quantity_plan = quantity_plan if isinstance(quantity_plan, dict) else {}
    rows = []
    for quantity in _list(unit.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        plan = quantity_plan_match(quantity, quantity_plan)
        if plan and not quantity_must_retain(plan):
            continue
        if quantity_plan and not plan:
            continue
        rows.append(
            {
                "value": value,
                "interpretation": str((plan or {}).get("retention_phrase") or (plan or {}).get("interpretation") or quantity.get("interpretation") or "").strip(),
                "source_evidence_item_id": str(quantity.get("source_evidence_item_id") or "").strip(),
                "source_labels": _string_list(quantity.get("source_label")) or _string_list(quantity.get("source_labels")),
                "quantity_role": str((plan or {}).get("quantity_role") or "").strip(),
                "quantity_id": str((plan or {}).get("quantity_id") or (plan or {}).get("candidate_id") or "").strip(),
                "must_retain": bool(plan and quantity_must_retain(plan)),
                "memo_use": str((plan or {}).get("memo_use") or "").strip(),
                "analyst_quantity_relevance": _dict((plan or {}).get("analyst_quantity_relevance")),
            }
        )
    return rows


def _excluded_quantity_values(unit: dict[str, Any], *, quantity_plan: dict[str, dict[str, Any]] | None = None) -> list[str]:
    quantity_plan = quantity_plan if isinstance(quantity_plan, dict) else {}
    excluded = []
    for quantity in _list(unit.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        plan = quantity_plan_match(quantity, quantity_plan)
        if quantity_plan and (not plan or not quantity_must_retain(plan)):
            excluded.append(value)
    return _dedupe(excluded)


def build_decision_obligation_plan(
    evidence_items: list[dict[str, Any]],
    *,
    packet: dict[str, Any],
    semantic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_context = semantic_context if isinstance(semantic_context, dict) else {}
    obligations = []
    conflicts = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        lineage = _dict(item.get("lineage"))
        evidence_ids = _string_list(lineage.get("covered_evidence_item_ids"))
        memo_use_rows = [_memo_use_for_evidence_id(evidence_id, semantic_context=semantic_context) for evidence_id in evidence_ids]
        memo_uses = _dedupe([row for row in memo_use_rows if row])
        if len(memo_uses) > 1:
            conflicts.append(
                {
                    "item_id": item.get("item_id"),
                    "evidence_item_ids": evidence_ids,
                    "memo_uses": memo_uses,
                    "issue": "conflicting_upstream_memo_use",
                }
            )
        obligations.append(
            {
                "evidence_unit_id": item.get("item_id"),
                "writer_role": item.get("role"),
                "obligation_level": item.get("obligation_level"),
                "memo_function": item.get("memo_function"),
                "include_reason": item.get("include_reason"),
                "demotion_reason": item.get("demotion_reason"),
                "required_quantity_ids": [
                    str(row.get("quantity_id") or row.get("value") or "")
                    for row in _list(item.get("quantities"))
                    if isinstance(row, dict)
                ],
                "source_labels": _string_list(item.get("source_labels")),
                "covered_evidence_item_ids": evidence_ids,
                "judgment_lineage": _list(item.get("judgment_lineage")),
            }
        )
    level_counts = Counter(str(row.get("obligation_level") or "unknown") for row in obligations)
    function_counts = Counter(str(row.get("memo_function") or "unknown") for row in obligations)
    fallback_requests = _obligation_fallback_requests(obligations, conflicts)
    return {
        "schema_id": "decision_obligation_plan_v1",
        "method": "reuse_first_global_and_analyst_judgment_adapter",
        "decision_question": packet.get("decision_question"),
        "obligation_count": len(obligations),
        "level_counts": dict(level_counts),
        "memo_function_counts": dict(function_counts),
        "obligations": obligations,
        "conflicts": conflicts,
        "fallback_requests": fallback_requests,
        "model_call_policy": "no_new_call_unless_fallback_requests_are_executed",
        "source_artifacts_used": _dedupe(
            [
                source
                for row in obligations
                for source in _string_list(row.get("judgment_lineage"))
            ]
        ),
    }


def build_writer_packet_writeability_report(
    *,
    memo_obligations: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    decision_obligation_plan: dict[str, Any],
    packet: dict[str, Any],
    semantic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_context = semantic_context if isinstance(semantic_context, dict) else {}
    obligations = [row for row in _list(memo_obligations.get("obligations")) if isinstance(row, dict)]
    required = [row for row in obligations if row.get("required")]
    mandatory_quantity_count = sum(len(_list(row.get("quantities"))) for row in required)
    max_quantities = max([len(_list(row.get("quantities"))) for row in required] or [0])
    role_counts = Counter(str(item.get("role") or "unknown") for item in evidence_items if isinstance(item, dict))
    fallback_requests = [
        *_list(decision_obligation_plan.get("fallback_requests")),
        *quantity_fallback_requests(semantic_context.get("quantity_obligation_plan", {})),
    ]
    issues = [
        *(["too_many_mandatory_obligations"] if len(required) > 12 else []),
        *(["too_many_mandatory_quantities"] if mandatory_quantity_count > 24 else []),
        *(["obligation_with_excessive_quantities"] if max_quantities > 4 else []),
        *(["missing_counterweight_or_scope"] if role_counts.get("strongest_counterweight", 0) == 0 and role_counts.get("scope_boundary", 0) == 0 else []),
        *(["fallback_adjudication_recommended"] if fallback_requests else []),
    ]
    strategy = "single_pass"
    if len(required) > 12 or mandatory_quantity_count > 24:
        strategy = "table_assisted"
    if fallback_requests:
        strategy = "needs_packet_repair"
    return {
        "schema_id": "writer_packet_writeability_report_v1",
        "method": "deterministic_reuse_first_contract_telemetry",
        "status": "ready" if not issues else "warning",
        "decision_question": packet.get("decision_question"),
        "mandatory_obligation_count": len(required),
        "optional_obligation_count": len(obligations) - len(required),
        "mandatory_quantity_count": mandatory_quantity_count,
        "maximum_quantities_per_obligation": max_quantities,
        "evidence_item_count": len(evidence_items),
        "role_counts": dict(role_counts),
        "relation_support_available": bool(_list(packet.get("argument_plan"))),
        "expected_memo_length_band": _expected_length_band(len(required), mandatory_quantity_count),
        "recommended_synthesis_strategy": strategy,
        "fallback_needed": bool(fallback_requests),
        "fallback_requests": fallback_requests,
        "model_call_accounting": {
            "new_default_model_call_added": False,
            "existing_judgment_artifacts_reused": _reused_artifacts(semantic_context),
            "fallback_model_call_recommended": bool(fallback_requests),
        },
        "issues": issues,
    }


def _semantic_context(
    *,
    analyst_adjudication: dict[str, Any] | None,
    analyst_decision_model: dict[str, Any] | None,
    analyst_quantity_binding_report: dict[str, Any] | None,
    global_decision_model: dict[str, Any] | None,
) -> dict[str, Any]:
    analyst_model = analyst_decision_model if isinstance(analyst_decision_model, dict) else {}
    analyst_quantity_relevance = analyst_quantity_relevance_plan(analyst_model)
    quantity_plan = build_quantity_obligation_plan(
        analyst_quantity_binding_report or {},
        analyst_quantity_relevance=analyst_quantity_relevance,
    )
    return {
        "analyst_adjudication": analyst_adjudication if isinstance(analyst_adjudication, dict) else {},
        "analyst_decision_model": analyst_model,
        "global_decision_model": global_decision_model if isinstance(global_decision_model, dict) else {},
        "analyst_quantity_binding_report": analyst_quantity_binding_report if isinstance(analyst_quantity_binding_report, dict) else {},
        "quantity_obligation_plan": quantity_plan,
        "quantity_plan_by_evidence_value": quantity_plan_by_evidence_value(quantity_plan),
        "analyst_relevance_plan": analyst_relevance_plan(analyst_model),
        "analyst_quantity_relevance_plan": analyst_quantity_relevance,
        "answer_hierarchy": _compact_answer_hierarchy(analyst_model, global_decision_model if isinstance(global_decision_model, dict) else {}),
        "memo_use_by_evidence_id": memo_use_by_evidence_id(analyst_adjudication if isinstance(analyst_adjudication, dict) else {}),
        "answer_relation_by_evidence_id": answer_relation_by_evidence_id(analyst_adjudication if isinstance(analyst_adjudication, dict) else {}),
        "adjudication_by_evidence_id": _adjudication_by_evidence_id(analyst_adjudication if isinstance(analyst_adjudication, dict) else {}),
    }


def _semantic_answer_hierarchy(packet: dict[str, Any], semantic_context: dict[str, Any]) -> dict[str, str]:
    hierarchy = _dict(semantic_context.get("answer_hierarchy"))
    direct = str(hierarchy.get("full_direct_answer") or hierarchy.get("direct_answer") or _dict(packet.get("answer")).get("bounded_answer") or "").strip()
    split = split_bluf_answer_hierarchy(direct)
    primary = str(hierarchy.get("primary_answer") or split["primary_answer"]).strip()
    secondary = str(hierarchy.get("secondary_detail") or split["secondary_detail"]).strip()
    secondary_type = str(hierarchy.get("secondary_detail_type") or split["secondary_detail_type"]).strip()
    if secondary_type == "none":
        secondary_type = ""
    return {
        "direct_answer": _short_text(direct, 700),
        "primary_answer": _short_text(primary, 520),
        "secondary_detail": _short_text(secondary, 420),
        "secondary_detail_type": secondary_type,
        "full_direct_answer": _short_text(hierarchy.get("full_direct_answer") or direct, 700) if secondary else "",
    }


def _compact_answer_hierarchy(analyst_model: dict[str, Any], global_model: dict[str, Any]) -> dict[str, str]:
    source = analyst_model if analyst_model else global_model
    direct = str(source.get("full_direct_answer") or source.get("direct_answer") or _dict(global_model.get("answer")).get("bounded_answer") or "").strip()
    split = split_bluf_answer_hierarchy(direct)
    primary = str(source.get("primary_answer") or split["primary_answer"]).strip()
    secondary = str(source.get("secondary_detail") or split["secondary_detail"]).strip()
    secondary_type = str(source.get("secondary_detail_type") or split["secondary_detail_type"]).strip()
    if secondary_type == "none":
        secondary_type = ""
    return {
        "direct_answer": _short_text(direct, 700),
        "primary_answer": _short_text(primary, 520),
        "secondary_detail": _short_text(secondary, 420),
        "secondary_detail_type": secondary_type,
        "full_direct_answer": _short_text(direct, 700) if secondary else "",
    }


def _obligation_for_unit(unit: dict[str, Any], *, semantic_context: dict[str, Any]) -> dict[str, Any]:
    role = str(unit.get("role") or "context_only").strip()
    evidence_ids = _string_list(_dict(unit.get("lineage")).get("covered_evidence_item_ids"))
    memo_uses = _dedupe([_memo_use_for_evidence_id(evidence_id, semantic_context=semantic_context) for evidence_id in evidence_ids])
    memo_uses = [value for value in memo_uses if value]
    relevance_decision = combined_relevance_decision(evidence_ids, semantic_context=semantic_context)
    level = _base_obligation_level(role)
    function = _memo_function(role)
    lineage = ["global_decision_model"]
    include_reason = str(unit.get("decision_relevance") or "").strip()
    demotion_reason = ""
    memo_inclusion = str(relevance_decision.get("memo_inclusion") or "").strip()
    memo_inclusion_rationale = str(relevance_decision.get("rationale") or "").strip()
    if memo_inclusion:
        lineage.append("analyst_decision_model_relevance")
        if memo_inclusion == "memo_spine":
            level = "must_include" if role != "context_only" else "should_include"
            include_reason = memo_inclusion_rationale or include_reason
        elif memo_inclusion == "supporting_context":
            level = "should_include"
            function = function if function != "background" else "interpretive_context"
            include_reason = memo_inclusion_rationale or include_reason
        elif memo_inclusion == "trace_only":
            level = "optional_context"
            demotion_reason = memo_inclusion_rationale or "Analyst decision model marked this evidence as trace-only."
        elif memo_inclusion == "exclude":
            level = "optional_context"
            demotion_reason = memo_inclusion_rationale or "Analyst decision model marked this evidence as outside the memo answer."
    if role == "context_only":
        if any(value in {"decision_crux", "load_bearing_primary_support", "load_bearing_counterweight", "quantitative_anchor"} for value in memo_uses):
            level = "should_include"
            function = "background"
            include_reason = include_reason or "Analyst adjudication marked covered evidence as potentially memo-relevant."
            lineage.append("analyst_adjudication")
        else:
            level = "optional_context"
            demotion_reason = "Global decision model placed this unit in contextual evidence."
    elif any(value == "not_decision_relevant" for value in memo_uses) and len(memo_uses) == 1:
        level = "should_include"
        demotion_reason = "Analyst adjudication questioned direct relevance; preserved for review because global model selected it."
        lineage.append("analyst_adjudication")
    elif memo_uses:
        lineage.append("analyst_adjudication")
    return {
        "obligation_level": level,
        "memo_function": function,
        "include_reason": include_reason or f"Global decision model selected this unit as {role}.",
        "demotion_reason": demotion_reason,
        "judgment_lineage": _dedupe(lineage),
        "memo_inclusion": memo_inclusion,
        "memo_inclusion_rationale": memo_inclusion_rationale,
    }


def _base_obligation_level(role: str) -> str:
    if role in {"strongest_support", "strongest_counterweight", "scope_boundary", "decision_crux", "quantitative_anchor"}:
        return "must_include"
    if role == "context_only":
        return "optional_context"
    return "should_include"


def _memo_function(role: str) -> str:
    return {
        "strongest_support": "answer_anchor",
        "quantitative_anchor": "answer_anchor",
        "strongest_counterweight": "counterweight",
        "scope_boundary": "scope_boundary",
        "decision_crux": "crux",
        "context_only": "background",
    }.get(role, "background")


def _adjudication_by_evidence_id(analyst_adjudication: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _list(analyst_adjudication.get("rows")):
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or row.get("claim_id") or "").strip()
        if evidence_id:
            rows[evidence_id] = row
    return rows


def _memo_use_for_evidence_id(evidence_id: str, *, semantic_context: dict[str, Any]) -> str:
    return str(_dict(semantic_context.get("memo_use_by_evidence_id")).get(str(evidence_id or "").strip()) or "").strip()


def _obligation_fallback_requests(obligations: list[dict[str, Any]], conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests = [
        {
            "request_type": "resolve_conflicting_evidence_disposition",
            "target_id": conflict.get("item_id"),
            "reason": conflict.get("issue"),
            "evidence_item_ids": conflict.get("evidence_item_ids", []),
        }
        for conflict in conflicts
    ]
    for obligation in obligations:
        if not obligation.get("source_labels") and obligation.get("obligation_level") == "must_include":
            requests.append(
                {
                    "request_type": "source_grounding_needed",
                    "target_id": obligation.get("evidence_unit_id"),
                    "reason": "must_include_without_source_label",
                }
            )
    return requests

def _expected_length_band(required_count: int, quantity_count: int) -> str:
    if required_count > 12 or quantity_count > 24:
        return "long"
    if required_count > 6 or quantity_count > 10:
        return "medium"
    return "short"


def _reused_artifacts(semantic_context: dict[str, Any]) -> list[str]:
    rows = ["global_decision_model"]
    if _list(_dict(semantic_context.get("analyst_adjudication")).get("rows")):
        rows.append("analyst_adjudication")
    if semantic_context.get("analyst_decision_model"):
        rows.append("analyst_decision_model")
    if _list(_dict(semantic_context.get("quantity_obligation_plan")).get("rows")):
        rows.append("analyst_quantity_binding_report")
    return _dedupe(rows)


def _contract_must_preserve(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "item_id": item.get("item_id"),
            "role": item.get("role"),
            "claim": item.get("reader_claim"),
            "source_labels": item.get("source_labels", []),
            "quantities": item.get("quantities", []),
        }
        for item in evidence_items
        if item.get("must_use")
    ]


def build_decision_writer_packet_quality_report(
    packet: dict[str, Any],
    *,
    global_decision_model: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    units = [unit for unit in _list(packet.get("evidence_units")) if isinstance(unit, dict)]
    role_counts = Counter(str(unit.get("role") or "unknown") for unit in units)
    missing_source_units = [
        str(unit.get("unit_id") or "")
        for unit in units
        if not _string_list(unit.get("source_labels"))
    ]
    missing_critical = _missing_critical_evidence(global_decision_model)
    issues = [
        *(["empty_writer_packet"] if not units else []),
        *(["missing_support_unit"] if role_counts.get("strongest_support", 0) == 0 else []),
        *(["missing_counterweight_or_scope_unit"] if role_counts.get("strongest_counterweight", 0) == 0 and role_counts.get("scope_boundary", 0) == 0 else []),
        *(["source_trail_missing_for_units"] if missing_source_units else []),
        *(["critical_evidence_not_accounted"] if missing_critical else []),
        *(["global_model_has_reconciliation_warnings"] if _string_list(_dict(global_decision_model.get("reconciliation")).get("issues")) else []),
    ]
    return {
        "schema_id": "decision_writer_packet_quality_report_v1",
        "status": "ready" if not issues else "warning",
        "evidence_unit_count": len(units),
        "ledger_row_count": len(_list(ledger.get("rows"))),
        "role_counts": dict(role_counts),
        "source_trail_count": len(_list(packet.get("source_trail"))),
        "source_missing_unit_ids": missing_source_units,
        "missing_critical_evidence_item_ids": missing_critical,
        "global_reconciliation_issues": _string_list(_dict(global_decision_model.get("reconciliation")).get("issues")),
        "packet_is_smaller_than_full_ledger": len(str(packet)) < len(str(ledger)),
        "issues": issues,
    }


def build_evidence_unit_traceability_matrix(packet: dict[str, Any], *, ledger: dict[str, Any]) -> dict[str, Any]:
    units = [unit for unit in _list(packet.get("evidence_units")) if isinstance(unit, dict)]
    unit_by_evidence_id = {
        evidence_id: unit
        for unit in units
        for evidence_id in _string_list(_dict(unit.get("lineage")).get("covered_evidence_item_ids"))
    }
    rows = []
    for ledger_row in _list(ledger.get("rows")):
        if not isinstance(ledger_row, dict):
            continue
        evidence_id = str(ledger_row.get("evidence_item_id") or "").strip()
        unit = unit_by_evidence_id.get(evidence_id, {})
        rows.append(
            {
                "evidence_item_id": evidence_id,
                "claim_id": ledger_row.get("claim_id"),
                "in_writer_packet": bool(unit),
                "unit_id": unit.get("unit_id", ""),
                "role": unit.get("role", ""),
                "source_labels": _string_list(ledger_row.get("source_labels")),
            }
        )
    return {
        "schema_id": "evidence_unit_traceability_matrix_v1",
        "method": "ledger_row_to_decision_writer_packet_unit",
        "row_count": len(rows),
        "covered_row_count": sum(1 for row in rows if row.get("in_writer_packet")),
        "rows": rows,
    }


def _evidence_units(global_model: dict[str, Any], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    units = []
    for section, role in ROLE_BY_GLOBAL_SECTION.items():
        for group in _list(global_model.get(section)):
            if isinstance(group, dict):
                units.append(_unit_from_group(len(units) + 1, group, role=role, ledger_by_id=ledger_by_id))
    return [unit for unit in units if unit.get("claim")]


def _unit_from_group(index: int, group: dict[str, Any], *, role: str, ledger_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_ids = _string_list(group.get("covered_evidence_item_ids"))
    source_labels = _source_labels(evidence_ids, ledger_by_id)
    source_appraisal = merged_source_appraisal(evidence_ids, ledger_by_id)
    source_context = _source_context_fields({}, [ledger_by_id.get(evidence_id, {}) for evidence_id in evidence_ids])
    return {
        "unit_id": f"decision_unit_{index:03d}",
        "section": SECTION_BY_ROLE.get(role, "context"),
        "role": role,
        "answer_relation": str(group.get("answer_relation") or group.get("answer_relation_to_default") or "").strip(),
        "claim": _short_text(str(group.get("proposition") or ""), 720),
        "decision_relevance": _short_text(str(group.get("answer_impact") or group.get("rationale") or ""), 520),
        "caveat": _short_text("; ".join(_string_list(group.get("applicability_limits"))), 360),
        "importance_rank": group.get("importance_rank"),
        "source_memo_role": str(group.get("memo_role") or "").strip(),
        "source_labels": source_labels,
        "primary_source_label": source_labels[0] if source_labels else "",
        "source_appraisal": source_appraisal,
        "source_use_warnings": _string_list(source_appraisal.get("source_use_warnings")),
        "allowed_wording": _dict(source_appraisal.get("allowed_wording")),
        **source_context,
        "quantities": _quantities(evidence_ids, ledger_by_id),
        "source_excerpts": _source_excerpts(evidence_ids, ledger_by_id),
        "lineage": {
            "global_group_id": group.get("group_id"),
            "covered_evidence_item_ids": evidence_ids,
        },
    }


def _compact_argument_plan(global_model: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(global_model.get("argument_plan")):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "step_id": row.get("step_id"),
                "section": row.get("section"),
                "writing_goal": row.get("writing_goal"),
                "required_points": _string_list(row.get("required_points"))[:6],
                "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
                "transition_from_previous": row.get("transition_from_previous"),
            }
        )
    return rows


def _source_trail(evidence_units: list[dict[str, Any]], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    for unit in evidence_units:
        role = str(unit.get("role") or "").strip()
        for evidence_id in _string_list(_dict(unit.get("lineage")).get("covered_evidence_item_ids")):
            for row in _source_rows(ledger_by_id.get(evidence_id, {})):
                key = _source_key(row)
                if not key:
                    continue
                existing = rows_by_key.setdefault(key, row | {"used_for": []})
                existing["used_for"] = _dedupe([*_string_list(existing.get("used_for")), role])
    return sorted(rows_by_key.values(), key=lambda row: (str(row.get("source_label") or ""), str(row.get("source_id") or "")))


def _source_aliases(evidence_units: list[dict[str, Any]], ledger_by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
    trail = _source_trail(evidence_units, ledger_by_id)
    return {
        str(row.get("source_label") or row.get("source_id") or ""): str(row.get("display_label") or row.get("source_label") or row.get("source_id") or "")
        for row in trail
        if str(row.get("source_label") or row.get("source_id") or "").strip()
    }

def _source_labels(evidence_ids: list[str], ledger_by_id: dict[str, dict[str, Any]]) -> list[str]:
    labels = []
    for evidence_id in evidence_ids:
        row = ledger_by_id.get(evidence_id, {})
        labels.extend(_string_list(row.get("source_labels")) or _string_list(row.get("source_ids")))
    return _dedupe(labels)

def _quantities(evidence_ids: list[str], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for evidence_id in evidence_ids:
        ledger_row = ledger_by_id.get(evidence_id, {})
        labels = _string_list(ledger_row.get("source_labels"))
        seen: set[str] = set()
        for quantity in _list(ledger_row.get("claim_quantities")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if not value:
                continue
            seen.add(" ".join(value.lower().split()))
            interpretation = str(quantity.get("local_interpretation") or quantity.get("measures") or ledger_row.get("why_it_matters") or ledger_row.get("claim") or "")
            rows.append(
                {
                    "value": value,
                    "source_evidence_item_id": evidence_id,
                    "source_label": labels[0] if labels else "",
                    "quantity_role": str(quantity.get("quantity_role") or ""),
                    "quantity_type": str(quantity.get("quantity_type") or ""),
                    "measures": str(quantity.get("measures") or ""),
                    "interpretation": _short_text(interpretation, 360),
                    "retention_hint": str(quantity.get("retention_hint") or ""),
                }
            )
        for value in _string_list(ledger_row.get("quantity_values")):
            if " ".join(value.lower().split()) in seen:
                continue
            rows.append(
                {
                    "value": value,
                    "source_evidence_item_id": evidence_id,
                    "source_label": labels[0] if labels else "",
                    "interpretation": _short_text(str(ledger_row.get("why_it_matters") or ledger_row.get("claim") or ""), 360),
                }
            )
    return rows


def _source_excerpts(evidence_ids: list[str], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for evidence_id in evidence_ids:
        ledger_row = ledger_by_id.get(evidence_id, {})
        excerpt = str(ledger_row.get("source_excerpt") or "").strip()
        if excerpt:
            rows.append({"evidence_item_id": evidence_id, "source_excerpt": _short_text(excerpt, 420)})
    return rows


def _source_rows(ledger_row: dict[str, Any]) -> list[dict[str, str]]:
    source_ids = _string_list(ledger_row.get("source_ids"))
    source_labels = _string_list(ledger_row.get("source_labels"))
    count = max(len(source_ids), len(source_labels), 1)
    rows = []
    for index in range(count):
        source_id = source_ids[index] if index < len(source_ids) else ""
        source_label = source_labels[index] if index < len(source_labels) else source_id
        if source_id or source_label:
            rows.append(
                {
                    "source_id": source_id,
                    "source_label": source_label,
                    "display_label": source_label or source_id,
                }
            )
    return rows


def _source_key(row: dict[str, Any]) -> str:
    return str(row.get("source_id") or row.get("source_label") or "").strip().lower()


def _ledger_by_id(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_item_id") or "").strip(): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _sections(evidence_units: list[dict[str, Any]]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    for unit in evidence_units:
        section = str(unit.get("section") or "context")
        sections.setdefault(section, []).append(str(unit.get("unit_id") or ""))
    return sections


def _missing_critical_evidence(global_model: dict[str, Any]) -> list[str]:
    accounting = _dict(global_model.get("evidence_accounting"))
    ledger_ids = set(_string_list(accounting.get("ledger_evidence_item_ids")))
    accounted_ids = set(_string_list(accounting.get("accounted_evidence_item_ids")))
    accounted_ids.update(_string_list(accounting.get("covered_evidence_item_ids")))
    accounted_ids.update(_string_list(accounting.get("downgraded_or_background_evidence_item_ids")))
    missing = sorted(ledger_ids - accounted_ids) if ledger_ids else _string_list(accounting.get("missing_accounting_ids"))
    omissions = _dict(accounting.get("obligation_omissions"))
    for value in omissions.values():
        for evidence_id in _string_list(value):
            if evidence_id not in accounted_ids:
                missing.append(evidence_id)
    return _dedupe(missing)
