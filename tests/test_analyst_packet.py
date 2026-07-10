from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.map_briefing_memo_ready_packet import build_memo_ready_packet_synthesis_prompt
from epistemic_case_mapper.map_briefing_analyst_packet import build_analyst_packet_bundle
from epistemic_case_mapper.map_briefing_final_outputs import ModelBackendConfig, write_final_reader_outputs
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

    assert "analyst_argument_plan" in prompt
    assert "analyst_decision_logic" in prompt
    assert "Treat these as guidance for what matters" in prompt
    assert "Exercise analyst judgment" in prompt
    assert "weigh_risk" in prompt


def test_analyst_packet_promotion_makes_analyst_packet_active_and_keeps_legacy_diagnostics() -> None:
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
    assert scaffold["legacy_deterministic_memo_ready_packet"]["method"] == "deterministic_legacy"
    assert scaffold["memo_ready_packet_quality_report"]["active_packet"] == "analyst_memo_ready_packet"
    assert scaffold["active_memo_ready_packet_report"]["status"] == "analyst_active"
    assert scaffold["active_memo_ready_packet_report"]["downgraded_evidence_item_ids"] == ["bundle:off_question"]


def test_final_reader_outputs_prefer_analyst_memo_ready_packet(tmp_path: Path) -> None:
    scaffold = _scaffold()
    scaffold["question"] = "Should option A be adopted?"
    scaffold["analyst_memo_ready_packet"] = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=_ledger(),
        adjudication=_adjudication(),
    )["analyst_memo_ready_packet"]

    result = write_final_reader_outputs(
        rendered="## Decision Brief\n\nSeed memo.",
        scaffold=scaffold,
        prioritized_map={"claims": []},
        artifacts=tmp_path,
        backend_config=ModelBackendConfig(backend="prompt", timeout=30, retries=0),
    )

    assert result["rewrite_result"]["report"]["analyst_memo_ready_packet_path"] is True
    assert "Should option A be adopted?" in result["briefing_path"].read_text()
