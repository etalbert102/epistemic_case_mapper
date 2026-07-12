from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.map_briefing_memo_ready_packet import build_memo_ready_packet_synthesis_prompt
from epistemic_case_mapper.map_briefing_memo_ready_finalization import run_memo_ready_presentation_normalization
from epistemic_case_mapper.map_briefing_analyst_packet import build_analyst_packet_bundle
from epistemic_case_mapper.map_briefing_final_outputs import ModelBackendConfig, write_final_reader_outputs
from epistemic_case_mapper.map_briefing_decision_writer_packet import decision_writer_packet_to_memo_ready_packet
from epistemic_case_mapper.map_briefing_decision_packet_stage import _run_analyst_packet_builders
from epistemic_case_mapper.map_briefing_pipeline import _promote_analyst_packet_as_active

from test_decision_briefing_packet import _scaffold


def _packet() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "answer_frame": {"default_answer": "Adopt option A only if the cost exposure is bounded.", "confidence": "medium"},
        "source_trail": [
            {"source_id": "s1", "source_label": "Outcome Study", "source_url": "https://example.test/outcome"},
            {"source_id": "s2", "source_label": "Risk Review", "source_url": "https://example.test/risk"},
            {"source_id": "s3", "source_label": "Off Question Review", "source_url": "https://example.test/off-question"},
            {"source_id": "s4", "source_label": "Stale Context Review", "source_url": "https://example.test/stale"},
        ],
    }


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "bundle:support",
                "input_kind": "retained_bundle",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
                "claim": "Option A reduced losses in the main outcome study.",
                "quantity_values": ["25% reduction"],
            },
            {
                "evidence_item_id": "quantity:support_25",
                "input_kind": "top_quantity_anchor",
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
                "claim": "The main reduction estimate was 25%.",
                "quantity_values": ["25% reduction"],
            },
            {
                "evidence_item_id": "bundle:risk",
                "input_kind": "retained_bundle",
                "source_ids": ["s2"],
                "source_labels": ["Risk Review"],
                "claim": "Option A shifts risk to the operating budget.",
            },
            {
                "evidence_item_id": "bundle:off_question",
                "input_kind": "retained_bundle",
                "source_ids": ["s3"],
                "source_labels": ["Off Question Review"],
                "claim": "A different population had a different outcome.",
            },
        ],
    }


def _adjudication() -> dict:
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "bundle:support",
                "memo_use": "load_bearing_primary_support",
                "importance_rank": 1,
                "rationale": "This is the main support for adoption.",
                "source_ids": ["s1"],
                "quantity_values": ["25% reduction"],
            },
            {
                "evidence_item_id": "quantity:support_25",
                "memo_use": "quantitative_anchor",
                "importance_rank": 2,
                "rationale": "This quantity should travel with the support proposition.",
                "source_ids": ["s1"],
                "quantity_values": ["25% reduction"],
            },
            {
                "evidence_item_id": "bundle:risk",
                "memo_use": "load_bearing_counterweight",
                "importance_rank": 3,
                "rationale": "This limits the decision.",
                "source_ids": ["s2"],
            },
            {
                "evidence_item_id": "bundle:off_question",
                "memo_use": "not_decision_relevant",
                "importance_rank": 100,
                "rationale": "This row is outside the decision population.",
                "source_ids": ["s3"],
                "downgrade_reason": "Different decision population.",
            },
        ],
    }


def test_analyst_packet_accounts_for_rows_and_groups_quantity_anchors() -> None:
    result = build_analyst_packet_bundle(packet=_packet(), ledger=_ledger(), adjudication=_adjudication())

    synthesis = result["analyst_synthesis_packet"]
    quality = result["analyst_packet_quality_report"]
    memo_ready = result["analyst_memo_ready_packet"]

    assert synthesis["schema_id"] == "analyst_synthesis_packet_v1"
    assert synthesis["primary_reasoning_chain"][0]["covered_evidence_item_ids"] == ["bundle:support", "quantity:support_25"]
    assert "25% reduction" in synthesis["primary_reasoning_chain"][0]["quantity_values"]
    assert synthesis["main_counterweights"][0]["covered_evidence_item_ids"] == ["bundle:risk"]
    assert quality["status"] == "ready"
    assert quality["packet_accounted_row_count"] == 4
    assert "bundle:off_question" in synthesis["evidence_accounting_summary"]["explicitly_downgraded_evidence_item_ids"]
    assert memo_ready["method"] == "analyst_adjudicated_packet_adapter"
    assert len([item for item in memo_ready["evidence_items"] if item["must_use"]]) == 2
    assert not any(
        "bundle:off_question" in item.get("lineage", {}).get("evidence_item_ids", [])
        for item in memo_ready["evidence_items"]
    )
    source_ids = {row["source_id"] for row in memo_ready["source_trail"]}
    assert source_ids == {"s1", "s2"}
    assert "s3" not in source_ids
    assert "s4" not in source_ids


def test_analyst_packet_prefers_global_decision_model_groups() -> None:
    decision_model = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only if operating risk is bounded.",
        "confidence": "medium",
        "overall_rationale": "The support and quantity should be read together, while risk bounds the answer.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Outcome evidence supports option A, with a 25% loss reduction as the key quantitative anchor.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["bundle:support"],
                "rationale": "The model grouped the support claim with its quantity instead of creating isolated rows.",
                "evidence_strength": "moderate",
                "answer_impact": "Supports adoption.",
                "uncertainty_type": "implementation",
            },
            {
                "group_id": "risk_group",
                "proposition": "Operating-budget risk is the main counterweight.",
                "memo_role": "load_bearing_counterweight",
                "importance_rank": 2,
                "covered_evidence_item_ids": ["bundle:risk"],
                "rationale": "This bounds the recommendation.",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "bundle:support", "disposition": "foreground", "group_id": "support_group"},
            {"evidence_item_id": "bundle:risk", "disposition": "foreground", "group_id": "risk_group"},
            {"evidence_item_id": "bundle:off_question", "disposition": "not_decision_relevant", "rationale": "Different population."},
        ],
        "quantitative_anchors": ["25% reduction"],
        "what_would_change_the_answer": ["If operating risk cannot be bounded."],
        "argument_plan": [
            {
                "step_id": "support_then_risk",
                "section": "Decision Brief",
                "writing_goal": "State the support, then show how risk bounds it.",
                "required_points": ["Use the 25% reduction with the support.", "Bound the answer by operating risk."],
                "evidence_item_ids": ["bundle:support", "quantity:support_25", "bundle:risk"],
                "transition_from_previous": "Start with the answer.",
            }
        ],
        "decision_logic": {
            "bounded_bottom_line": "Adopt option A only if operating risk is bounded.",
            "support_summary": "Outcome evidence supports option A.",
            "strongest_counterweight": "Operating-budget risk.",
            "counterweight_weighting": "The counterweight bounds rather than erases the support.",
        },
    }

    result = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=_ledger(),
        adjudication=_adjudication(),
        decision_model=decision_model,
    )

    synthesis = result["analyst_synthesis_packet"]
    quality = result["analyst_packet_quality_report"]

    assert synthesis["bottom_line"] == "Adopt option A only if operating risk is bounded."
    assert synthesis["primary_reasoning_chain"][0]["group_id"] == "support_group"
    assert synthesis["primary_reasoning_chain"][0]["covered_evidence_item_ids"] == ["bundle:support", "quantity:support_25"]
    assert synthesis["primary_reasoning_chain"][0]["answer_impact"] == "Supports adoption."
    assert quality["group_accounting"]["grouped_quantity_row_ids"] == ["quantity:support_25"]
    assert quality["group_accounting"]["method"] == "global_analyst_decision_model_grouping"
    assert quality["packet_accounted_row_count"] == 4
    assert synthesis["argument_plan"][0]["step_id"] == "support_then_risk"


def test_analyst_packet_binds_quantity_rows_by_source_label_when_source_id_is_missing() -> None:
    ledger = _ledger()
    ledger["rows"][1] = {
        **ledger["rows"][1],
        "source_ids": [],
        "source_labels": ["Outcome Study final report"],
    }
    decision_model = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only if operating risk is bounded.",
        "confidence": "medium",
        "overall_rationale": "The support group should inherit the source-matched quantity.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Outcome evidence reports a loss reduction that supports option A.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["bundle:support"],
                "rationale": "Main support.",
            },
        ],
    }

    result = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=ledger,
        adjudication=_adjudication(),
        decision_model=decision_model,
    )

    group = result["analyst_synthesis_packet"]["primary_reasoning_chain"][0]
    assert "quantity:support_25" in group["covered_evidence_item_ids"]
    assert "quantity:support_25" not in result["analyst_packet_quality_report"]["missing_from_packet_accounting"]


def test_analyst_packet_does_not_bind_source_matched_quantity_to_semantically_wrong_group() -> None:
    ledger = _ledger()
    ledger["rows"].append(
        {
            "evidence_item_id": "quantity:risk_ratio",
            "input_kind": "top_quantity_anchor",
            "source_ids": [],
            "source_labels": ["Outcome Study extended report"],
            "claim": "hazard ratio 1.15",
            "quantity_values": ["hazard ratio 1.15"],
            "quantity_type": "effect_size",
        }
    )
    decision_model = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only if operating risk is bounded.",
        "confidence": "medium",
        "overall_rationale": "The support group should not absorb a risk quantity only because labels overlap.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Outcome evidence reports a loss reduction that supports option A.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["bundle:support"],
                "rationale": "Main support.",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "bundle:risk", "disposition": "background", "rationale": "Not modeled in this fixture."},
            {"evidence_item_id": "bundle:off_question", "disposition": "not_decision_relevant", "rationale": "Different population."},
        ],
    }

    result = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=ledger,
        adjudication=_adjudication(),
        decision_model=decision_model,
    )

    group = result["analyst_synthesis_packet"]["primary_reasoning_chain"][0]
    assert "quantity:risk_ratio" not in group["covered_evidence_item_ids"]
    assert "quantity:risk_ratio" not in result["analyst_packet_quality_report"]["missing_from_packet_accounting"]
    assert result["analyst_synthesis_packet"]["quantitative_anchors"][0]["covered_evidence_item_ids"] == ["quantity:risk_ratio"]


def test_analyst_packet_uses_refined_answer_and_warning_obligations() -> None:
    warning_packet = {
        "schema_id": "memo_warning_packet_v1",
        "warnings": [
            {
                "warning_id": "memo_warning_001",
                "severity": "critical",
                "source_labels": ["Risk Review"],
                "claim": "Raw excerpt that should not become the memo obligation.",
                "anchor_terms": ["raw", "excerpt"],
            },
            {
                "warning_id": "memo_warning_002",
                "severity": "moderate",
                "source_labels": ["Outcome Study"],
                "claim": "Already covered raw excerpt.",
                "anchor_terms": ["already", "covered"],
            }
        ],
    }
    refinement = {
        "schema_id": "analyst_packet_refinement_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only if operating risk is bounded.",
        "answer_rationale": "Support is strong, but operating risk is the limiting condition.",
        "decision_logic": {
            "bounded_bottom_line": "Adopt option A only where operating risk is bounded.",
            "support_summary": "The loss-reduction evidence supports adoption.",
            "strongest_counterweight": "Operating-budget risk can erase the benefit.",
            "counterweight_weighting": "The counterweight bounds the recommendation but does not erase the outcome signal.",
            "reconciled_cruxes": ["The answer changes if operating risk cannot be bounded."],
            "scope_boundaries": ["Applies only where maintenance capacity is reliable."],
            "practical_implications": ["Recommend adoption with an operating-risk condition."],
            "do_not_overstate": ["Do not recommend unconditional adoption."],
        },
        "warning_obligations": [
            {
                "warning_id": "memo_warning_001",
                "memo_action": "bound_scope_or_confidence",
                "obligation": "State that operating risk limits confidence in adoption.",
                "rationale": "The warning should bound the recommendation.",
                "source_labels": ["Risk Review"],
                "key_terms": ["operating", "risk", "confidence"],
            },
            {
                "warning_id": "memo_warning_002",
                "memo_action": "not_needed_for_memo",
                "obligation": "No separate action because the support section already covers this.",
                "rationale": "Already covered by primary support.",
                "source_labels": ["Outcome Study"],
                "key_terms": [],
            }
        ],
        "argument_plan": [
            {
                "step_id": "weigh_risk",
                "section": "Why This Is the Best Current Read",
                "writing_goal": "State the support, then immediately explain how operating risk bounds it.",
                "required_points": ["Operating risk is the limiting condition."],
                "evidence_item_ids": ["bundle:support", "memo_warning_001"],
                "source_labels": ["Outcome Study", "Risk Review"],
                "transition_from_previous": "Use the warning to bound the support.",
            }
        ],
    }

    result = build_analyst_packet_bundle(
        packet={**_packet(), "answer_frame": {"default_answer": "The current answer frame is bounded by the source packet."}},
        ledger=_ledger(),
        adjudication=_adjudication(),
        memo_warning_packet=warning_packet,
        refinement=refinement,
    )

    assert result["analyst_synthesis_packet"]["bottom_line"] == "Adopt option A only if operating risk is bounded."
    assert result["analyst_synthesis_packet"]["decision_logic"]["bounded_bottom_line"] == "Adopt option A only where operating risk is bounded."
    assert result["analyst_memo_ready_packet"]["analyst_decision_logic"]["counterweight_weighting"].startswith("The counterweight")
    assert result["analyst_synthesis_packet"]["argument_plan"][0]["step_id"] == "weigh_risk"
    assert result["analyst_memo_ready_packet"]["analyst_argument_plan"][0]["writing_goal"].startswith("State the support")
    assert len(result["analyst_synthesis_packet"]["warning_obligations"]) == 2
    assert result["analyst_synthesis_packet"]["warning_obligations"][0]["obligation"].startswith("State that operating risk")
    warning = result["analyst_memo_ready_packet"]["memo_warning_packet"]["warnings"][0]
    assert warning["claim"] == "State that operating risk limits confidence in adoption."
    assert {"operating", "risk", "confidence"}.issubset(set(warning["anchor_terms"]))
    assert len(result["analyst_memo_ready_packet"]["memo_warning_packet"]["warnings"]) == 1
    warning_items = [
        item
        for item in result["analyst_memo_ready_packet"]["evidence_items"]
        if str(item.get("item_id", "")).startswith("analyst_warning_item_")
    ]
    assert len(warning_items) == 1
    assert warning_items[0]["must_use"] is True
    assert warning_items[0]["reader_claim"] == "State that operating risk limits confidence in adoption."


def test_memo_ready_prompt_treats_analyst_argument_plan_as_controlling_order() -> None:
    result = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=_ledger(),
        adjudication=_adjudication(),
        refinement={
            "direct_answer": "Adopt option A only if operating risk is bounded.",
            "answer_rationale": "The counterweight bounds the support.",
            "decision_logic": {
                "bounded_bottom_line": "Adopt option A only if operating risk is bounded.",
                "support_summary": "The support shows losses fall.",
                "strongest_counterweight": "Operating risk can erase benefits.",
                "counterweight_weighting": "This bounds the recommendation rather than eliminating it.",
                "reconciled_cruxes": ["The answer changes if risk cannot be bounded."],
                "scope_boundaries": ["Applies to comparable sites."],
                "practical_implications": ["Use a risk condition."],
                "do_not_overstate": ["Do not imply unconditional adoption."],
            },
            "argument_plan": [
                {
                    "step_id": "weigh_risk",
                    "section": "Why This Is the Best Current Read",
                    "writing_goal": "Weigh the operating-risk counterweight immediately after support.",
                    "required_points": ["Do not leave the counterweight to repair."],
                    "evidence_item_ids": ["bundle:risk"],
                    "source_labels": ["Risk Review"],
                    "transition_from_previous": "Contrast support with risk.",
                }
            ],
        },
    )

    prompt = build_memo_ready_packet_synthesis_prompt(result["analyst_memo_ready_packet"])

    assert "writer model context" in prompt
    assert "writer_model_context_v1" in prompt
    assert "Required obligation ledger" in prompt
    assert "excluded_evidence_log" not in prompt
    assert "lineage_report" not in prompt
    assert '"evidence_items"' not in prompt


def test_analyst_packet_builds_source_bound_writer_packet() -> None:
    result = build_analyst_packet_bundle(packet=_packet(), ledger=_ledger(), adjudication=_adjudication())

    writer_packet = result["analyst_memo_ready_packet"]["writer_packet"]
    quality = result["analyst_memo_ready_packet"]["writer_packet_quality_report"]
    support = next(unit for unit in writer_packet["evidence_units"] if unit["role"] == "strongest_support")

    assert writer_packet["schema_id"] == "writer_packet_v1"
    assert quality["status"] == "ready"
    assert support["quantities"][0]["value"] == "25% reduction"
    assert support["quantities"][0]["source_evidence_item_id"] == "bundle:support"
    assert support["quantities"][0]["source_label"] == "Outcome Study"
    assert quality["source_bound_quantity_count"] >= 1


def test_presentation_normalization_replaces_source_ids_from_source_trail() -> None:
    packet = build_analyst_packet_bundle(packet=_packet(), ledger=_ledger(), adjudication=_adjudication())[
        "analyst_memo_ready_packet"
    ]
    memo = "## Decision Brief\n\nThe estimate was 25% [s1].\n\n## Sources\n\n* s1\n"

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[Outcome Study]" in result["memo"]
    assert "[s1]" not in result["memo"]


def test_analyst_packet_promotion_makes_analyst_packet_the_single_active_packet() -> None:
    analyst_packet = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=_ledger(),
        adjudication=_adjudication(),
    )["analyst_memo_ready_packet"]
    scaffold = {
        "memo_ready_packet": {"schema_id": "memo_ready_packet_v1", "method": "deterministic_legacy", "evidence_items": []},
        "memo_ready_packet_quality_report": {"schema_id": "memo_ready_packet_quality_report_v1", "status": "legacy"},
        "analyst_memo_ready_packet": analyst_packet,
        "analyst_packet_quality_report": {"schema_id": "analyst_packet_quality_report_v1", "status": "ready"},
        "analyst_synthesis_packet": {
            "evidence_accounting_summary": {
                "explicitly_downgraded_evidence_item_ids": ["bundle:off_question"],
            }
        },
    }

    _promote_analyst_packet_as_active(scaffold)

    assert scaffold["memo_ready_packet"]["method"] == "analyst_adjudicated_packet_adapter"
    assert "legacy_deterministic_memo_ready_packet" not in scaffold
    assert "legacy_deterministic_memo_ready_packet_quality_report" not in scaffold
    assert scaffold["memo_ready_packet_quality_report"]["active_packet"] == "memo_ready_packet"
    assert scaffold["active_memo_ready_packet_report"]["status"] == "analyst_active"
    assert scaffold["active_memo_ready_packet_report"]["active_packet"] == "memo_ready_packet"
    assert scaffold["active_memo_ready_packet_report"]["downgraded_evidence_item_ids"] == ["bundle:off_question"]


def test_ready_decision_writer_packet_becomes_active_synthesis_packet() -> None:
    analyst_packet = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=_ledger(),
        adjudication=_adjudication(),
    )["analyst_memo_ready_packet"]
    scaffold = {
        "analyst_memo_ready_packet": analyst_packet,
        "analyst_packet_quality_report": {"schema_id": "analyst_packet_quality_report_v1", "status": "ready"},
        "decision_writer_packet": {
            "schema_id": "decision_writer_packet_v1",
            "decision_question": "Should option A be adopted?",
            "answer": {
                "bounded_answer": "Adopt option A only if risk is bounded.",
                "confidence": "medium",
                "confidence_reasons": ["Support is bounded by risk."],
            },
            "decision_logic": {"bounded_bottom_line": "Adopt option A only if risk is bounded."},
            "argument_plan": [],
            "evidence_units": [
                {
                    "unit_id": "decision_unit_001",
                    "role": "strongest_support",
                    "claim": "Option A reduces losses.",
                    "decision_relevance": "This is the main support.",
                    "source_labels": ["Outcome Study"],
                    "quantities": [{"value": "25% reduction", "source_label": "Outcome Study"}],
                    "lineage": {"covered_evidence_item_ids": ["bundle:support"]},
                }
            ],
            "source_trail": [{"source_id": "s1", "source_label": "Outcome Study"}],
            "global_reconciliation": {"issues": []},
        },
        "decision_writer_packet_quality_report": {
            "schema_id": "decision_writer_packet_quality_report_v1",
            "status": "ready",
            "evidence_unit_count": 1,
        },
    }

    _promote_analyst_packet_as_active(scaffold)

    assert scaffold["memo_ready_packet"]["method"] == "global_decision_writer_packet_adapter"
    assert scaffold["memo_ready_packet"]["writer_packet"]["schema_id"] == "decision_writer_packet_v1"
    assert scaffold["memo_ready_packet"]["evidence_items"][0]["reader_claim"] == "Option A reduces losses."
    assert scaffold["active_memo_ready_packet_report"]["status"] == "decision_writer_active"
    assert scaffold["memo_ready_packet_quality_report"]["active_packet_source"] == "decision_writer_packet"


def test_ready_decision_writer_path_skips_legacy_analyst_refinement() -> None:
    scaffold = {
        "analyst_adjudication": _adjudication(),
        "memo_warning_packet": {"schema_id": "memo_warning_packet_v1", "warnings": []},
        "decision_writer_packet": {
            "schema_id": "decision_writer_packet_v1",
            "decision_question": "Should option A be adopted?",
            "answer": {
                "bounded_answer": "Adopt option A only if risk is bounded.",
                "confidence": "medium",
                "confidence_reasons": ["Support is bounded by risk."],
            },
            "decision_logic": {"bounded_bottom_line": "Adopt option A only if risk is bounded."},
            "argument_plan": [],
            "evidence_units": [
                {
                    "unit_id": "decision_unit_001",
                    "role": "strongest_support",
                    "claim": "Option A reduces losses.",
                    "decision_relevance": "This is the main support.",
                    "source_labels": ["Outcome Study"],
                    "quantities": [{"value": "25% reduction", "source_label": "Outcome Study"}],
                    "lineage": {"covered_evidence_item_ids": ["bundle:support"]},
                }
            ],
            "source_trail": [{"source_id": "s1", "source_label": "Outcome Study"}],
            "global_reconciliation": {"issues": []},
        },
        "decision_writer_packet_quality_report": {
            "schema_id": "decision_writer_packet_quality_report_v1",
            "status": "ready",
            "evidence_unit_count": 1,
        },
    }

    _run_analyst_packet_builders(
        scaffold,
        _packet(),
        _ledger(),
        backend_config=ModelBackendConfig(backend="prompt", timeout=30, retries=0),
        progress=None,
    )

    assert scaffold["analyst_packet_refinement_report"]["status"] == "skipped"
    assert scaffold["analyst_packet_refinement_report"]["active_path"] == "decision_writer_packet"
    assert scaffold["active_memo_ready_packet_report"]["status"] == "decision_writer_active"


def test_decision_writer_budget_keeps_adjudicated_quantified_support_mandatory() -> None:
    packet = {
        "schema_id": "decision_writer_packet_v1",
        "decision_question": "Should the intervention be treated as harmful, neutral, or beneficial?",
        "answer": {"bounded_answer": "The intervention is included in general guidance.", "confidence": "medium"},
        "decision_logic": {},
        "argument_plan": [],
        "source_trail": [
            {"source_id": "guidance", "source_label": "Guidance"},
            {"source_id": "outcome", "source_label": "Outcome Study"},
        ],
        "global_reconciliation": {"issues": []},
        "evidence_units": [
            {
                "unit_id": f"decision_unit_{index:03d}",
                "role": "strongest_support",
                "claim": f"Contextual support item {index}.",
                "importance_rank": index,
                "source_labels": ["Guidance"],
                "lineage": {"covered_evidence_item_ids": [f"claim:context_{index}"]},
            }
            for index in range(1, 5)
        ]
        + [
            {
                "unit_id": "decision_unit_005",
                "role": "strongest_support",
                "claim": "Moderate exposure was not associated with the main adverse outcome.",
                "importance_rank": 5,
                "decision_relevance": "Quantified outcome evidence calibrates the decision.",
                "source_labels": ["Outcome Study"],
                "quantities": [
                    {
                        "value": "0.93",
                        "source_evidence_item_id": "claim:outcome",
                        "source_label": "Outcome Study",
                    }
                ],
                "lineage": {"covered_evidence_item_ids": ["claim:outcome"]},
            }
        ],
    }
    adjudication = {
        "rows": [
            *[
                {
                    "evidence_item_id": f"claim:context_{index}",
                    "memo_use": "load_bearing_primary_support",
                    "importance_rank": 10 + index,
                }
                for index in range(1, 5)
            ],
            {
                "evidence_item_id": "claim:outcome",
                "memo_use": "load_bearing_primary_support",
                "importance_rank": 1,
            },
        ]
    }
    quantity_binding = {
        "schema_id": "analyst_quantity_binding_report_v1",
        "status": "ready",
        "candidate_bindings": [
            {
                "candidate_id": "q_outcome",
                "source_evidence_item_id": "claim:outcome",
                "value": "0.93",
                "memo_use": "yes",
                "quantity_role": "decision_anchor",
                "must_retain": True,
                "interpretation": "hazard ratio of 0.93",
            }
        ],
    }

    memo_ready = decision_writer_packet_to_memo_ready_packet(
        packet,
        analyst_adjudication=adjudication,
        analyst_quantity_binding_report=quantity_binding,
    )

    outcome_item = next(item for item in memo_ready["evidence_items"] if item["reader_claim"].startswith("Moderate exposure"))
    mandatory_support = [item for item in memo_ready["evidence_items"] if item["role"] == "strongest_support" and item["must_use"]]

    assert outcome_item["must_use"] is True
    assert outcome_item["decision_diagnosticity"]["best_adjudicated_importance_rank"] == 1
    assert outcome_item["quantities"][0]["value"] == "0.93"
    assert len(mandatory_support) == 4


def test_final_reader_outputs_prefer_analyst_memo_ready_packet(tmp_path: Path) -> None:
    scaffold = _scaffold()
    scaffold["question"] = "Should option A be adopted?"
    scaffold["analyst_memo_ready_packet"] = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=_ledger(),
        adjudication=_adjudication(),
    )["analyst_memo_ready_packet"]
    _promote_analyst_packet_as_active(scaffold)

    result = write_final_reader_outputs(
        rendered="## Decision Brief\n\nSeed memo.",
        scaffold=scaffold,
        prioritized_map={"claims": []},
        artifacts=tmp_path,
        backend_config=ModelBackendConfig(backend="prompt", timeout=30, retries=0),
    )

    assert result["rewrite_result"]["report"]["memo_ready_packet_path"] is True
    assert result["rewrite_result"]["report"]["active_memo_ready_packet_method"] == "analyst_adjudicated_packet_adapter"
    assert "Should option A be adopted?" in result["briefing_path"].read_text()
