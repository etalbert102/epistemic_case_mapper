from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)
from epistemic_case_mapper.map_briefing_decision_boundary_source_contract import build_decision_boundary_source_contract
from epistemic_case_mapper.map_briefing_adaptive_outline import build_adaptive_memo_outline
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_decision_usefulness_retention_report,
    build_memo_ready_packet_repair_prompt,
    build_memo_ready_packet_retention_report,
    run_decision_usefulness_memo_repair,
    run_memo_ready_packet_repair,
    run_memo_ready_packet_synthesis,
)
from epistemic_case_mapper.map_briefing_memo_obligations import build_memo_obligation_packet
from epistemic_case_mapper.map_briefing_memo_ready_prompt import (
    build_memo_ready_packet_synthesis_prompt,
    build_writer_packet_synthesis_prompt,
)
from epistemic_case_mapper.map_briefing_quantity_retention import retention_quantity_rows
from epistemic_case_mapper.map_briefing_writer_decision_interface import (
    build_writer_decision_interface,
    build_writer_decision_interface_quality_report,
    build_writer_model_context,
)
from epistemic_case_mapper.model_backends import ModelBackendResult


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "item:support",
                "claim_id": "support",
                "claim": "Option A improves the main outcome.",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Review"],
                "quantity_values": ["20% improvement"],
                "source_excerpt": "The main outcome improved by 20%.",
                "why_it_matters": "The improvement is the main support.",
                "natural_bottom_line": "Option A improved the main outcome in the studied setting.",
                "must_preserve_terms": ["20% improvement", "studied setting"],
                "claim_context": {
                    "population": "studied setting",
                    "exposure_or_option": "option A",
                    "outcome_or_endpoint": "main outcome",
                    "evidence_design": "outcome review",
                    "stated_limitations": "setting-specific evidence",
                },
            },
            {
                "evidence_item_id": "item:limit",
                "claim_id": "limit",
                "claim": "The result may not apply in a narrower setting.",
                "source_ids": ["s2"],
                "source_labels": ["Scope Review"],
                "source_excerpt": "The result did not cover the narrower setting.",
            },
            {
                "evidence_item_id": "item:missing",
                "claim_id": "missing",
                "claim": "This item has not been accounted for.",
                "source_ids": ["s3"],
                "source_labels": ["Open Question"],
            },
        ],
    }


def _global_model(*, missing: bool = False) -> dict:
    return {
        "schema_id": "global_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "bounded_answer": "Adopt option A only where the narrower setting is not decisive.",
        "confidence": "medium",
        "confidence_reasons": ["Support is meaningful but scope limits apply."],
        "strongest_support": [
            {
                "group_id": "support_group",
                "proposition": "Option A improves the main outcome.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["item:support"],
                "rationale": "This is the main support.",
            }
        ],
        "strongest_counterargument": [],
        "scope_boundaries": [
            {
                "group_id": "scope_group",
                "proposition": "The answer depends on whether the narrower setting matters.",
                "memo_role": "scope_or_applicability",
                "importance_rank": 2,
                "covered_evidence_item_ids": ["item:limit"],
                "rationale": "This bounds adoption.",
            }
        ],
        "decision_cruxes": [],
        "contextual_evidence": [],
        "argument_plan": [{"step_id": "support_then_scope", "evidence_item_ids": ["item:support", "item:limit"]}],
        "decision_logic": {"bounded_bottom_line": "Adopt option A only where the narrower setting is not decisive."},
        "evidence_accounting": {
            "missing_accounting_ids": ["item:missing"] if missing else [],
            "obligation_omissions": {"ungrouped_scope_boundary_ids": ["item:missing"]} if missing else {},
        },
        "reconciliation": {"issues": ["missing_evidence_accounting"] if missing else []},
    }


def test_decision_writer_packet_uses_global_model_as_answer_owner() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = bundle["decision_writer_packet"]
    quality = bundle["decision_writer_packet_quality_report"]

    assert packet["schema_id"] == "decision_writer_packet_v1"
    assert packet["answer"]["bounded_answer"] == "Adopt option A only where the narrower setting is not decisive."
    assert "answer_spine" not in packet
    assert "analyst_synthesis_packet" not in packet
    assert packet["evidence_units"][0]["role"] == "strongest_support"
    assert packet["evidence_units"][0]["quantities"][0]["value"] == "20% improvement"
    assert quality["status"] == "ready"


def test_decision_writer_packet_builds_deterministic_source_trail_and_traceability() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = bundle["decision_writer_packet"]
    matrix = bundle["evidence_unit_traceability_matrix"]

    assert [row["source_label"] for row in packet["source_trail"]] == ["Outcome Review", "Scope Review"]
    assert packet["source_aliases"]["Outcome Review"] == "Outcome Review"
    assert matrix["row_count"] == 3
    assert matrix["covered_row_count"] == 2
    missing_row = next(row for row in matrix["rows"] if row["evidence_item_id"] == "item:missing")
    assert missing_row["in_writer_packet"] is False


def test_decision_writer_packet_flags_missing_critical_evidence() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(missing=True), ledger=_ledger())
    quality = bundle["decision_writer_packet_quality_report"]

    assert quality["status"] == "warning"
    assert quality["missing_critical_evidence_item_ids"] == ["item:missing"]
    assert "critical_evidence_not_accounted" in quality["issues"]
    assert "global_model_has_reconciliation_warnings" in quality["issues"]


def test_decision_writer_packet_adapts_to_active_memo_ready_packet() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    assert packet["schema_id"] == "memo_ready_packet_v1"
    assert packet["method"] == "global_decision_writer_packet_adapter"
    assert packet["answer_spine"]["default_read"] == "Adopt option A only where the narrower setting is not decisive."
    assert packet["writer_packet"]["schema_id"] == "decision_writer_packet_v1"
    assert packet["evidence_items"][0]["reader_claim"] == "Option A improves the main outcome."
    assert packet["evidence_items"][0]["must_use"] is True
    assert packet["evidence_items"][0]["quantities"][0]["value"] == "20% improvement"
    assert packet["memo_obligations"]["required_count"] == 2
    assert packet["decision_synthesis_contract"]["required_memo_obligations"]
    assert packet["decision_obligation_plan"]["schema_id"] == "decision_obligation_plan_v1"
    assert packet["writer_packet_writeability_report"]["schema_id"] == "writer_packet_writeability_report_v1"
    assert packet["decision_memo_contract"]["schema_id"] == "decision_memo_contract_v1"
    assert packet["writer_decision_interface"]["schema_id"] == "writer_decision_interface_v1"
    assert packet["writer_decision_interface_quality_report"]["schema_id"] == "writer_decision_interface_quality_report_v1"


def test_decision_writer_packet_uses_explicit_answer_relation_for_writer_role() -> None:
    model = _global_model()
    model["strongest_support"] = []
    model["strongest_counterargument"] = [
        {
            "group_id": "countered_fear_group",
            "proposition": "The feared harm is not observed in the main outcome.",
            "memo_role": "load_bearing_counterweight",
            "importance_rank": 1,
            "covered_evidence_item_ids": ["item:support"],
            "rationale": "This counters a feared risk but supports the final answer.",
        }
    ]
    bundle = build_decision_writer_packet_bundle(global_decision_model=model, ledger=_ledger())
    adjudication = {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "item:support",
                "memo_use": "load_bearing_primary_support",
                "answer_relation": "supports_answer",
                "importance_rank": 1,
                "rationale": "It supports the selected bottom line even though it counters a feared risk.",
                "covered_by": [],
                "source_ids": ["s1"],
                "quantity_values": ["20% improvement"],
            }
        ],
    }

    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
        analyst_adjudication=adjudication,
    )

    item = packet["evidence_items"][0]
    assert item["source_role"] == "strongest_counterweight"
    assert item["role"] == "strongest_support"
    assert item["answer_relation"] == "supports_answer"
    assert item["answer_relation_basis"] == "analyst_adjudication_answer_relation"
    assert packet["memo_obligations"]["obligations"][0]["obligation_type"] == "must_weigh_support"


def test_decision_writer_packet_reuses_quantity_binding_for_required_quantities() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    quantity_binding = {
        "schema_id": "analyst_quantity_binding_report_v1",
        "status": "ready",
        "candidate_bindings": [
            {
                "candidate_id": "support_group::item:support::20_improvement",
                "group_id": "support_group",
                "value": "20% improvement",
                "source_evidence_item_id": "item:support",
                "source_labels": ["Outcome Review"],
                "memo_use": "yes",
                "quantity_role": "decision_anchor",
                "must_retain": True,
                "interpretation": "20% improvement in the main outcome.",
                "retention_phrase": "20% improvement in the main outcome",
                "rationale": "This is the decision-facing effect size.",
                "binding_source": "model",
            },
            {
                "candidate_id": "support_group::item:support::p_value",
                "group_id": "support_group",
                "value": "p = 0.04",
                "source_evidence_item_id": "item:support",
                "source_labels": ["Outcome Review"],
                "memo_use": "context_only",
                "quantity_role": "statistical_detail",
                "must_retain": False,
                "interpretation": "p-value trace statistic.",
                "rationale": "Not reader-facing for this decision.",
                "binding_source": "model",
            },
        ],
    }
    bundle["decision_writer_packet"]["evidence_units"][0]["quantities"].append(
        {
            "value": "p = 0.04",
            "source_evidence_item_id": "item:support",
            "source_label": "Outcome Review",
            "interpretation": "p-value trace statistic.",
        }
    )

    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
        analyst_quantity_binding_report=quantity_binding,
        global_decision_model=_global_model(),
    )

    support_item = packet["evidence_items"][0]
    assert [row["value"] for row in support_item["quantities"]] == ["20% improvement"]
    assert support_item["quantities"][0]["must_retain"] is True
    assert support_item["excluded_quantity_values"] == ["p = 0.04"]
    obligation = packet["memo_obligations"]["obligations"][0]
    assert obligation["quantities"][0]["must_retain"] is True
    assert [row["value"] for row in retention_quantity_rows(obligation)] == ["20% improvement"]
    assert packet["quantity_obligation_plan"]["must_retain_count"] == 1
    assert packet["writer_packet_writeability_report"]["model_call_accounting"]["new_default_model_call_added"] is False
    assert "analyst_quantity_binding_report" in packet["writer_packet_writeability_report"]["model_call_accounting"]["existing_judgment_artifacts_reused"]


def test_writer_decision_interface_compiles_visible_decision_context() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    interface = build_writer_decision_interface(packet)
    quality = build_writer_decision_interface_quality_report(interface)

    assert interface["schema_id"] == "writer_decision_interface_v1"
    assert interface["decision_question"] == "Should option A be adopted?"
    assert interface["support_that_drives_answer"][0]["claim"] == "Option A improves the main outcome."
    assert interface["scope_boundaries"][0]["claim"] == "The answer depends on whether the narrower setting matters."
    assert interface["answer_frame"]["scope_note"] == "The answer depends on whether the narrower setting matters."
    assert interface["answer_frame"]["direct_answer"] == "Adopt option A only where the narrower setting is not decisive."
    assert interface["answer_frame"]["main_support"] == "Option A improves the main outcome."
    assert interface["answer_frame"]["main_counterweight"] == ""
    assert interface["practical_implication_cards"] == []
    assert "missing_model_practical_implications" in quality["warnings"]
    assert interface["decision_evidence_table"][0]["answer_relation"] == "supports_answer"
    assert interface["decision_evidence_table"][0]["natural_bottom_line"] == "Option A improved the main outcome in the studied setting."
    assert interface["decision_evidence_table"][0]["must_preserve_terms"] == ["20% improvement", "studied setting"]
    assert interface["decision_evidence_table"][0]["source_local_context"]["population"] == "studied setting"
    assert interface["decision_evidence_table"][0]["source_local_context"]["outcome_or_endpoint"] == "main outcome"
    assert interface["quantity_anchors"][0]["value"] == "20% improvement"
    assert interface["reasoning_hierarchy"]["schema_id"] == "decision_reasoning_hierarchy_v1"
    assert interface["adaptive_memo_outline"]["schema_id"] == "adaptive_memo_outline_v1"
    assert interface["adaptive_memo_outline"]["must_write_cards"]
    assert [move["move"] for move in interface["reasoning_hierarchy"]["reasoning_moves"]][:2] == [
        "answer_frame",
        "primary_answer_evidence",
    ]
    assert interface["retention_checklist"]
    assert interface["lineage_report"]["model_visible_evidence_item_count"] == 2
    assert quality["status"] == "warning"
    assert "missing_counterweights" in quality["warnings"]
    assert "source_appraisal_summary_uninformative" in quality["warnings"]
    assert quality["source_appraisal_row_count"] == 2
    assert quality["informative_source_appraisal_row_count"] == 0


def test_writer_quality_ignores_internal_outline_writing_goals() -> None:
    interface = {
        "support_that_drives_answer": [{"claim": "Option A improves the main outcome."}],
        "counterweights_and_disposition": [{"claim": "The result may not transport.", "disposition_rationale": "Scope is narrower."}],
        "quantity_anchors": [{"value": "20% improvement"}],
        "reasoning_hierarchy": {"reasoning_moves": [{"move": "answer_frame"}]},
        "retention_checklist": [],
        "must_use_evidence": [],
        "source_appraisal_summary": [],
        "adaptive_memo_outline": {
            "sections": [
                {
                    "section_id": "bottom_line",
                    "writing_goal": "Answer the decision question directly from the strongest evidence.",
                }
            ]
        },
    }

    quality = build_writer_decision_interface_quality_report(interface)

    assert "generic_or_scaffolded_judgment_present" not in quality["warnings"]


def test_writer_quality_flags_reader_facing_scaffolded_counterweight() -> None:
    interface = {
        "support_that_drives_answer": [{"claim": "Option A improves the main outcome."}],
        "counterweights_and_disposition": [
            {
                "claim": "The result may not transport.",
                "disposition_rationale": (
                    "Use counterweights to bound the answer if they do not overturn the primary support."
                ),
            }
        ],
        "quantity_anchors": [{"value": "20% improvement"}],
        "reasoning_hierarchy": {"reasoning_moves": [{"move": "answer_frame"}]},
        "retention_checklist": [],
        "must_use_evidence": [],
        "source_appraisal_summary": [],
    }

    quality = build_writer_decision_interface_quality_report(interface)

    assert "generic_or_scaffolded_judgment_present" in quality["warnings"]


def test_writer_decision_interface_logs_but_hides_non_visible_evidence_text() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )
    packet["evidence_items"].append(
        {
            "item_id": "decision_writer_item_optional",
            "role": "strongest_support",
            "reader_claim": "Off-question omega seafood context should not guide the memo.",
            "source_label": "Nutrition Context",
            "source_labels": ["Nutrition Context"],
            "obligation_level": "optional_context",
            "must_use": False,
        }
    )

    interface = build_writer_decision_interface(packet)
    model_context = build_writer_model_context(interface)
    serialized = str(interface)
    model_serialized = str(model_context)

    assert "Off-question omega seafood context should not guide the memo" not in serialized
    assert interface["excluded_evidence_log"][0]["item_id"] == "decision_writer_item_optional"
    assert interface["excluded_evidence_log"][0]["filter_reason"] == "not_marked_must_use_for_memo_synthesis"
    assert "excluded_evidence_log" not in model_serialized
    assert "lineage_report" not in model_serialized
    assert "decision_evidence_table" in model_serialized
    assert "adaptive_memo_outline" in model_serialized
    assert "must_use_evidence" not in model_serialized
    assert "decision_writer_item_optional" not in model_serialized


def test_writer_model_context_exposes_compact_source_appraisal() -> None:
    ledger = _ledger()
    ledger["rows"][0]["source_appraisal"] = {
        "status": "ready",
        "source_appraisal_ids": ["sa_s1"],
        "document_types": ["empirical_study"],
        "evidence_proximity": ["primary"],
        "recommended_uses": ["load_bearing_with_qualification"],
        "decision_directness": "partial",
        "allowed_wording": {
            "causal_language_allowed": False,
            "must_qualify_with": ["observational evidence"],
        },
        "source_use_warnings": ["association_not_causation"],
        "interpretation_caveats": ["Associational evidence should not be written as causal."],
    }
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=ledger)
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    interface = build_writer_decision_interface(packet)
    context = build_writer_model_context(interface)

    support = context["decision_evidence_table"][0]
    assert "association_not_causation" in support["source_appraisal_note"]
    assert context["source_appraisal_summary"][0]["decision_directness"] == "partial"
    assert context["source_appraisal_summary"][0]["allowed_wording"]["causal_language_allowed"] is False
    contract = context["decision_boundary_source_contract"]
    assert contract["source_use_cards"][0]["source_id"] == "s1"
    assert "source_label" not in contract["source_use_cards"][0]
    assert "observational evidence" in str(contract["source_use_cards"][0]["wording_cautions"])
    assert contract["quantity_priority_cards"][0]["quantity"] == "20% improvement"
    assert contract["quantity_priority_cards"][0]["priority"] == "primary_decision_anchor"
    assert contract["boundary_obligations"]
    quality = build_writer_decision_interface_quality_report(interface)
    assert quality["informative_source_appraisal_row_count"] == 1
    assert quality["decision_boundary_source_contract_quality"]["source_card_count"] >= 1
    assert "source_appraisal_summary_uninformative" not in quality["warnings"]
    assert "source_weighting" in context["adaptive_memo_outline"]["section_selection_summary"]["selected_section_ids"]


def test_writer_model_context_calibrates_overclaiming_claim_surfaces() -> None:
    ledger = _ledger()
    ledger["rows"][0]["claim"] = "Option A is safe and is independent of implementation conditions."
    ledger["rows"][0]["source_appraisal"] = {
        "status": "ready",
        "recommended_uses": ["load_bearing_with_qualification"],
        "decision_directness": "partial",
        "allowed_wording": {
            "causal_language_allowed": False,
            "avoid_terms": ["safe", "independent"],
            "must_qualify_with": ["observational evidence"],
        },
        "source_use_warnings": ["association_not_causation"],
    }
    model = _global_model()
    model["strongest_support"][0]["proposition"] = "Option A is safe and is independent of implementation conditions."
    bundle = build_decision_writer_packet_bundle(global_decision_model=model, ledger=ledger)
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    context = build_writer_model_context(build_writer_decision_interface(packet))
    support = context["decision_evidence_table"][0]
    canonical = packet["canonical_decision_writer_packet"]
    priority = canonical["priority_evidence"][0]

    assert "safe" not in support["claim"].lower()
    assert "independent of" not in support["claim"].lower()
    assert "not clearly harmful in the stated scope" in support["claim"]
    assert "not fully explained by" in support["claim"]
    assert support["original_claim"] == "Option A is safe and is independent of implementation conditions."
    assert "source_appraisal_requires_qualified_wording" in support["claim_calibration_notes"]
    assert priority["claim"] == support["claim"]
    assert priority["original_claim"] == support["original_claim"]


def test_boundary_source_contract_prioritizes_effect_quantities_before_context_quantities() -> None:
    contract = build_decision_boundary_source_contract(
        {"decision_question": "Should option A be adopted?"},
        [
            {
                "item_id": "support",
                "role": "strongest_support",
                "reader_claim": "Option A improved the main outcome.",
                "source_labels": ["Outcome Review"],
                "importance_rank": 1,
                "quantities": [
                    {"value": "1 unit per week", "interpretation": "comparison exposure baseline"},
                    {"value": "HR 0.76", "interpretation": "hazard ratio for the main outcome"},
                    {"value": "95% CI 0.62 to 0.91", "interpretation": "confidence interval for the hazard ratio"},
                ],
            }
        ],
    )

    quantities = contract["quantity_priority_cards"]
    assert [row["quantity_kind"] for row in quantities[:3]] == [
        "effect_estimate",
        "uncertainty_interval",
        "dose_or_context_boundary",
    ]
    assert quantities[0]["quantity"] == "HR 0.76"


def test_writer_decision_interface_rescues_should_include_quantity_context() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )
    packet["evidence_items"].append(
        {
            "item_id": "decision_writer_item_should_include",
            "role": "context_only",
            "reader_claim": "The implementation threshold is two cycles.",
            "source_label": "Implementation Review",
            "source_labels": ["Implementation Review"],
            "quantities": [{"value": "two cycles", "interpretation": "implementation threshold"}],
            "obligation_level": "should_include",
            "memo_function": "answer_anchor",
            "source_memo_role": "quantitative_anchor",
            "importance_rank": 5,
            "must_use": False,
        }
    )

    interface = build_writer_decision_interface(packet)
    model_context = build_writer_model_context(interface)
    hierarchy = model_context["reasoning_hierarchy"]
    interpretive = next(move for move in hierarchy["reasoning_moves"] if move["move"] == "interpretive_context")

    assert interpretive["evidence_refs"][0]["item_id"] == "decision_writer_item_should_include"
    assert model_context["rescued_context_table"][0]["item_id"] == "decision_writer_item_should_include"
    assert "two cycles" in str(model_context)


def test_decision_writer_packet_prompt_exposes_adaptive_retention_cards() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "canonical_decision_writer_packet_v1" in prompt
    assert "reader_synthesis_packet_v1" in prompt
    assert "answer_frame" in prompt
    assert "must_include_points" in prompt
    assert "limiting_evidence" in prompt
    assert "mandatory_retention_checklist" not in prompt
    assert "counterweight_dispositions" not in prompt
    assert "reader_brief_plan" not in prompt
    assert "decision_interpretation_plan" not in prompt
    assert "mandatory_evidence_ledger" not in prompt
    assert "decision_boundary_source_contract" not in prompt
    assert "Required obligation ledger" not in prompt
    assert "Option A improves the main outcome" in prompt
    assert "The answer depends on whether the narrower setting matters" in prompt
    assert "Suggested memo shape" not in prompt
    assert "analyst_synthesis_packet" not in prompt


def test_adaptive_outline_merges_duplicate_cards_without_dropping_quantities() -> None:
    interface = {
        "schema_id": "writer_decision_interface_v1",
        "decision_question": "What should we believe about option A?",
        "decision_evidence_table": [
            {
                "item_id": "a",
                "role": "quantitative_anchor",
                "answer_relation": "supports_answer",
                "claim": "Option A changes the main outcome.",
                "source_labels": ["Outcome Review"],
                "quantities": [
                    {"value": "1.17", "interpretation": "effect estimate"},
                    {"value": "3.24%", "interpretation": "absolute difference"},
                ],
            }
        ],
        "retention_checklist": [
            {
                "obligation_id": "one",
                "obligation_type": "must_interpret_quantity",
                "role": "quantitative_anchor",
                "statement": "Interpret this load-bearing quantity for the decision: Option A changes the main outcome.",
                "source_labels": ["Outcome Review"],
                "quantities": [{"value": "1.17", "interpretation": "effect estimate"}],
                "evidence_item_ids": ["a"],
            },
            {
                "obligation_id": "two",
                "obligation_type": "must_interpret_quantity",
                "role": "quantitative_anchor",
                "statement": "Interpret this load-bearing quantity for the decision: Option A changes the main outcome.",
                "source_labels": ["Outcome Review"],
                "quantities": [{"value": "3.24%", "interpretation": "absolute difference"}],
                "evidence_item_ids": ["a"],
            },
        ],
        "source_appraisal_summary": [],
    }

    outline = build_adaptive_memo_outline(interface)
    card = outline["must_write_cards"][0]

    assert len(outline["must_write_cards"]) == 1
    assert sorted(card["obligation_ids"]) == ["one", "two"]
    assert [row["value"] for row in card["quantities_to_keep_together"]] == ["1.17", "3.24%"]
    assert card["section_id"] == "answer_evidence"
    assert outline["merge_report"]["input_card_count"] == 2


def test_adaptive_outline_uses_evidence_roles_for_counterweight_sections() -> None:
    interface = {
        "schema_id": "writer_decision_interface_v1",
        "decision_question": "Should option A be adopted?",
        "decision_evidence_table": [
            {
                "item_id": "limit",
                "role": "scope_boundary",
                "answer_relation": "bounds_scope",
                "claim": "Option A has only been tested in the initial setting.",
                "source_labels": ["Scope Review"],
            }
        ],
        "retention_checklist": [
            {
                "obligation_id": "scope",
                "obligation_type": "must_bound_scope",
                "role": "scope_boundary",
                "statement": "Bound the answer's applicability using this source-backed scope boundary.",
                "source_labels": ["Scope Review"],
                "evidence_item_ids": ["limit"],
            }
        ],
        "source_appraisal_summary": [],
    }

    outline = build_adaptive_memo_outline(interface)

    assert "counterweights" in outline["section_selection_summary"]["selected_section_ids"]
    assert outline["must_write_cards"][0]["section_id"] == "counterweights"


def test_bare_decision_writer_packet_prompt_is_explicitly_unavailable() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())

    prompt = build_writer_packet_synthesis_prompt(bundle["decision_writer_packet"])

    assert "synthesis prompt unavailable" in prompt
    assert "writer_model_context_v1" not in prompt
    assert "decision_writer_packet_v1" not in prompt


def test_decision_writer_packet_prompt_filters_non_must_use_evidence_from_model_context() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )
    packet["answer_spine"]["why_this_read"] = (
        "Option A improves the main outcome; Off-question omega seafood context should not guide the memo."
    )
    packet["evidence_items"].append(
        {
            "item_id": "decision_writer_item_optional",
            "role": "strongest_support",
            "reader_claim": "Off-question omega seafood context should not guide the memo.",
            "source_label": "Nutrition Context",
            "source_labels": ["Nutrition Context"],
            "obligation_level": "optional_context",
            "must_use": False,
        }
    )

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "Off-question omega seafood context should not guide the memo" not in prompt
    assert "decision_writer_item_optional" not in prompt
    assert "not_marked_must_use_for_memo_synthesis" not in prompt
    assert "canonical_decision_writer_packet_v1" in prompt
    assert "writer_model_context_v1" not in prompt
    assert "excluded_evidence_log" not in prompt
    assert "lineage_report" not in prompt


def _decision_usefulness_packet() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "evidence_items": [],
        "source_trail": [{"source_id": "s1", "source_label": "Outcome Review"}],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["s1"],
                    "main_use": "drives the main outcome read",
                    "why_weight_this_way": "directly measures the outcome that matters",
                    "what_not_to_use_it_for": "does not settle implementation burden alone",
                    "evidence_item_ids": ["item:support"],
                }
            ]
        },
        "decision_usefulness_packet": {
            "schema_id": "decision_usefulness_packet_v1",
            "answer_shape": "single_stance",
            "recommended_stance": {
                "stance": "Adopt option A conditionally.",
                "why_this_stance": "The main outcome improves when implementation risk is bounded.",
                "source_ids": ["s1"],
                "evidence_item_ids": ["item:support"],
            },
            "tradeoffs": [
                {
                    "tradeoff": "Outcome gain versus implementation burden.",
                    "choose_a_if": "Adopt if burden remains manageable.",
                    "choose_b_if": "Delay if burden rises.",
                    "source_ids": ["s1"],
                    "evidence_item_ids": ["item:support"],
                }
            ],
            "cruxes_and_thresholds": [
                {
                    "crux": "Whether implementation burden stays below the acceptable threshold.",
                    "would_change_if": "New evidence shows burden overwhelms the outcome gain.",
                    "source_ids": ["s1"],
                    "evidence_item_ids": ["item:support"],
                }
            ],
            "monitoring_triggers": [
                {
                    "trigger": "New implementation failure evidence.",
                    "would_update": "Shift from adoption to delay.",
                    "source_ids": ["s1"],
                    "evidence_item_ids": ["item:support"],
                }
            ],
        },
    }


def test_decision_usefulness_retention_warns_on_missing_tradeoff_and_trigger() -> None:
    memo = "## Decision Memo\n\nAdopt option A conditionally because the main outcome improves."

    report = build_decision_usefulness_retention_report(memo, _decision_usefulness_packet())

    assert report["status"] == "warning"
    issue_types = {row["obligation_type"] for row in report["issues"]}
    assert "tradeoff" in issue_types
    assert "monitoring_trigger" in issue_types
    assert "presentation_gap" in issue_types


def test_decision_usefulness_memo_repair_applies_targeted_improvement(monkeypatch) -> None:
    packet = _decision_usefulness_packet()
    memo = "## Decision Memo\n\nAdopt option A conditionally because the main outcome improves."
    before = build_decision_usefulness_retention_report(memo, packet)

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        assert "Missing decision-support rows" in prompt
        assert "Outcome gain versus implementation burden" in prompt
        return ModelBackendResult(
            text=(
                "## Decision Memo\n\n"
                "Adopt option A conditionally because the main outcome improves. "
                "The useful distinction is not whether Option A helps at all, but whether the outcome gain remains worth the implementation burden. "
                "The direct outcome evidence carries the answer, while implementation evidence bounds it. "
                "The key tradeoff is outcome gain versus implementation burden: adopt if the burden remains manageable, "
                "but delay if it rises. The crux is whether implementation burden stays below the acceptable threshold. "
                    "New implementation failure evidence would shift the read from adoption to delay [s1].\n\n"
                    "## Practical Implication\n"
                    "Proceed only while implementation burden remains manageable, and delay adoption if new implementation evidence shows the burden is rising."
                ),
                backend="fake",
            )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_decision_usefulness_memo_repair(memo, packet, before, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "accepted"
    assert result["report"]["applied"] is True
    assert result["report"]["final_missing_count"] < before["missing_count"]
    assert result["report"]["final_missing_count"] == 0
    assert "New implementation failure evidence" in result["memo"]


def test_decision_writer_packet_repair_partial_improvement_is_visible(monkeypatch) -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )
    weak_memo = "## Decision Brief\n\nOption A is plausible.\n"
    before = build_memo_ready_packet_retention_report(weak_memo, packet)

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(
            text=(
                "## Decision Brief\n\n"
                "Outcome Review reports that Option A improves the main outcome by 20% improvement."
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_repair(weak_memo, packet, before, backend="fake", backend_timeout=30, backend_retries=0)

    assert before["missing_mandatory_count"] == 6
    assert result["report"]["contract_mode"] == "strict_writer_packet"
    assert result["report"]["status"] == "partial_retention_improvement_applied_with_warnings"
    assert result["report"]["accepted"] is False
    assert result["report"]["applied"] is True
    assert result["report"]["final_missing_mandatory_count"] == 3
    assert "Outcome Review" in result["memo"]


def test_strict_writer_repair_does_not_apply_quantity_only_improvement(monkeypatch) -> None:
    evidence_item = {
        "item_id": "decision_writer_item_001",
        "must_use": True,
        "role": "strongest_support",
        "reader_claim": "Option A improves the main outcome.",
        "source_label": "Outcome Review",
        "source_labels": ["Outcome Review"],
        "quantities": [{"value": "10%"}, {"value": "20%"}],
    }
    packet = {
        "method": "global_decision_writer_packet_adapter",
        "writer_packet": {"schema_id": "decision_writer_packet_v1"},
        "decision_question": "Should option A be adopted?",
        "evidence_items": [evidence_item],
        "memo_obligations": build_memo_obligation_packet([evidence_item], {"warnings": []}),
        "source_trail": [{"source_label": "Outcome Review"}],
    }
    weak_memo = "## Decision Brief\n\nOutcome Review says Option A improves the main outcome.\n"
    before = build_memo_ready_packet_retention_report(weak_memo, packet)

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(
            text="## Decision Brief\n\nOutcome Review says Option A improves the main outcome by 10%.\n",
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_repair(weak_memo, packet, before, backend="fake", backend_timeout=30, backend_retries=0)

    assert before["missing_mandatory_count"] == 1
    assert before["missing_quantity_count"] == 2
    assert result["report"]["final_missing_mandatory_count"] == 1
    assert result["report"]["final_retention_report"]["missing_quantity_count"] == 1
    assert result["report"]["status"] == "no_retention_improvement_kept_original"
    assert result["report"]["applied"] is False
    assert result["memo"] == weak_memo


def test_decision_writer_packet_repair_prompt_carries_originating_evidence_context() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )
    weak_memo = "## Decision Brief\n\nOption A is plausible.\n"
    before = build_memo_ready_packet_retention_report(weak_memo, packet)

    prompt = build_memo_ready_packet_repair_prompt(weak_memo, packet, before)

    assert '"contract_mode": "strict_writer_packet"' in prompt
    assert "This is the main support." in prompt
    assert "This bounds adoption." in prompt
