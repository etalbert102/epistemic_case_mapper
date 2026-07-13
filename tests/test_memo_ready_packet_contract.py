from __future__ import annotations

from epistemic_case_mapper.map_briefing_analytical_balance_contract import build_analytical_balance_contract
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_finalization import build_memo_ready_packet_retention_report
from epistemic_case_mapper.map_briefing_memo_ready_packet import (
    build_memo_ready_packet_synthesis_prompt,
    build_quality_synthesis_packet_bundle,
)

from test_decision_briefing_packet import _scaffold


def test_memo_ready_packet_includes_general_decision_synthesis_contract() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    contract = packet["decision_synthesis_contract"]

    assert contract["schema_id"] == "decision_synthesis_contract_v1"
    assert "best-supported answer or action stance" in contract["stance_task"]
    assert "strongest evidence" in contract["counterweight_task"]
    assert "subgroups, contexts, or assumptions" in contract["scope_task"]
    assert contract["answer_spine_to_use"]
    assert contract["strongest_support_to_weigh"]
    assert contract["strongest_counterweights_to_weigh"]
    assert contract["quantitative_anchors_to_interpret"]
    assert "egg" not in str(contract).lower()


def test_memo_ready_synthesis_prompt_uses_contract_as_flexible_guidance() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "writer model context" in prompt
    assert "writer_model_context_v1" in prompt
    assert "The writer model context is the complete model-visible evidence and judgment record" in prompt
    assert "Use reader_brief_plan.paragraph_jobs as the writing plan" in prompt
    assert "Use decision_interpretation_plan as the meaning layer" in prompt
    assert "not as the memo outline" in prompt
    assert "reader_brief_plan" in prompt
    assert "decision_interpretation_plan" in prompt
    assert "Weigh support against counterweights and scope boundaries" in prompt
    assert "Non-negotiable retention rule" in prompt
    assert "mandatory_evidence_ledger" in prompt
    assert "quantity_anchors" in prompt


def test_memo_ready_prompt_without_evidence_items_does_not_dump_raw_packet() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "decision_synthesis_contract": {"schema_id": "decision_synthesis_contract_v1"},
        "memo_warning_packet": {"warnings": [{"claim": "Raw warning should not be dumped."}]},
    }

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "synthesis prompt unavailable" in prompt
    assert "Raw warning should not be dumped" not in prompt
    assert "decision_synthesis_contract" not in prompt


def test_analytical_balance_contract_promotes_high_rank_counterweight_without_domain_terms() -> None:
    packet = _balance_packet()

    contract = build_analytical_balance_contract(packet)
    required = contract["required_balance_cards"]

    assert contract["schema_id"] == "analytical_balance_contract_v1"
    assert required[0]["role"] == "strongest_counterweight"
    assert required[0]["statement"] == "Option A increased serious implementation failures in one study."
    assert "RR 1.19" in required[0]["surface_numbers"]
    assert "egg" not in str(contract).lower()


def test_analytical_calibration_contract_exposes_answer_scope_quantity_and_causal_guidance() -> None:
    contract = build_analytical_balance_contract(_calibration_packet())

    assert contract["answer_classification"]["question_options"] == ["harmful", "neutral", "beneficial"]
    assert contract["answer_classification"]["answer_shape"] == "bounded_neutral_or_no_clear_harm"
    assert any(row["scope_use"] == "study_or_context_specific" and "2 units daily" in row["value"] for row in contract["scope_dose_guardrails"])
    assert any(row["scope_use"] == "candidate_decision_scope" and "1 unit per week" in row["value"] for row in contract["scope_dose_guardrails"])
    assert any(row["role"] == "subgroup_boundary" for row in contract["subgroup_boundary_cards"])
    assert any(row["card_id"] == "balance_boundary" for row in contract["required_balance_cards"])
    assert any(row["requirement_type"] == "uncertainty_or_interval" for row in contract["targeted_quantity_requirements"])
    assert any(row["requirement_type"] == "counterweight_magnitude" for row in contract["targeted_quantity_requirements"])
    assert any("causal wording" in row["writing_job"] for row in contract["causal_language_discipline"])
    assert any(row["required_evidence_type_move"] for row in contract["evidence_type_contrasts"])
    assert "egg" not in str(contract).lower()


def test_synthesis_prompt_exposes_analytical_balance_contract_as_source_ids() -> None:
    prompt = build_memo_ready_packet_synthesis_prompt(_balance_packet())

    assert "analytical_balance_contract" in prompt
    assert "mandatory_evidence_ledger" in prompt
    assert '"item_id": "support"' in prompt
    assert '"quantities_to_preserve"' in prompt
    assert '"source_id": "support_study"' in prompt
    assert '"source_id": "risk_study"' in prompt
    assert "Risk Study" not in prompt
    assert "source_labels" not in prompt


def test_synthesis_prompt_exposes_calibration_fields_as_source_ids() -> None:
    prompt = build_memo_ready_packet_synthesis_prompt(_calibration_packet())

    assert "answer_classification" in prompt
    assert "scope_dose_guardrails" in prompt
    assert "targeted_quantity_requirements" in prompt
    assert "causal_language_discipline" in prompt
    assert "subgroup_boundary_cards" in prompt
    assert '"source_id": "boundary_source"' in prompt
    assert "Boundary Source" not in prompt
    assert "source_labels" not in prompt


def test_synthesis_prompt_projects_internal_language_for_model_context() -> None:
    packet = _balance_packet()
    packet["evidence_items"][0]["decision_relevance"] = "This must-write card changes the decision read."

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "This required point changes the answer." in prompt
    assert "This must-write card changes the decision read." not in prompt
    assert '"role": "strongest_counterweight"' in prompt
    assert '"source_id": "support_study"' in prompt


def test_retention_warns_when_required_balance_counterweight_is_missing() -> None:
    report = build_memo_ready_packet_retention_report(
        "Support Study found Option A improved the main outcome by 20%.",
        _balance_packet(),
    )

    assert report["status"] == "warning"
    assert report["missing_analytical_balance_count"] == 1
    assert report["issues"][0]["issue_type"] == "missing_analytical_balance_card"
    assert report["issues"][0]["role"] == "strongest_counterweight"


def test_retention_accepts_required_balance_counterweight_when_weighed() -> None:
    memo = (
        "Support Study found Option A improved the main outcome by 20%. "
        "Risk Study is the main counterweight: Option A increased serious implementation failures, "
        "with RR 1.19, so this weakens and bounds the default answer."
    )

    report = build_memo_ready_packet_retention_report(memo, _balance_packet())

    assert report["status"] == "ready"
    assert report["missing_analytical_balance_count"] == 0


def test_retention_warns_when_required_boundary_card_is_missing() -> None:
    report = build_memo_ready_packet_retention_report(
        "Evidence supports a neutral answer for the main population.",
        _calibration_packet(),
    )

    missing_roles = [issue["role"] for issue in report["issues"] if issue["issue_type"] == "missing_analytical_balance_card"]
    assert "scope_boundary" in missing_roles


def test_retention_accepts_required_subgroup_boundary_when_named() -> None:
    memo = (
        "Support Source reports no increased failure at 1 unit per week, with RR 0.98 and a 95% CI. "
        "Risk Source is a counterweight because RR 1.19 weakens but does not overturn the neutral read. "
        "Boundary Source bounds the answer: the finding applies to adults without prior eligibility problems, "
        "so the subgroup boundary affects how the answer should be used."
    )

    report = build_memo_ready_packet_retention_report(memo, _calibration_packet())

    assert report["missing_analytical_balance_count"] == 0


def _balance_packet() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "answer_spine": {"default_read": "Option A is supported but bounded."},
        "source_trail": [
            {"source_id": "support_study", "source_label": "Support Study"},
            {"source_id": "risk_study", "source_label": "Risk Study"},
        ],
        "evidence_items": [
            {
                "item_id": "support",
                "must_use": True,
                "obligation_level": "must_include",
                "role": "strongest_support",
                "importance_rank": 1,
                "reader_claim": "Option A improved the main outcome.",
                "source_label": "Support Study",
                "source_labels": ["Support Study"],
                "quantities": [{"value": "20%", "interpretation": "main outcome improvement"}],
            },
            {
                "item_id": "counter",
                "must_use": False,
                "obligation_level": "should_include",
                "role": "strongest_counterweight",
                "answer_relation": "challenges_answer",
                "memo_function": "counterweight",
                "importance_rank": 2,
                "reader_claim": "Option A increased serious implementation failures in one study.",
                "decision_relevance": "Provides a challenge estimate, RR 1.19, that may bound adoption.",
                "source_label": "Risk Study",
                "source_labels": ["Risk Study"],
            },
            {
                "item_id": "minor_context",
                "must_use": False,
                "obligation_level": "should_include",
                "role": "context_only",
                "importance_rank": 80,
                "reader_claim": "Option A has a long implementation history.",
                "source_label": "Support Study",
                "source_labels": ["Support Study"],
            },
        ],
    }


def _calibration_packet() -> dict:
    return {
        "decision_question": "Should option A be treated as harmful, neutral, or beneficial for the main outcome?",
        "answer_spine": {"default_read": "Option A shows no clear harm at the stated scope."},
        "source_trail": [
            {"source_id": "support_source", "source_label": "Support Source"},
            {"source_id": "risk_source", "source_label": "Risk Source"},
            {"source_id": "boundary_source", "source_label": "Boundary Source"},
            {"source_id": "context_source", "source_label": "Context Source"},
        ],
        "evidence_items": [
            {
                "item_id": "support",
                "must_use": True,
                "obligation_level": "must_include",
                "role": "strongest_support",
                "importance_rank": 1,
                "reader_claim": "Option A at 1 unit per week was not associated with increased failure.",
                "decision_relevance": "Main support estimate RR 0.98 with 95% CI 0.90-1.07.",
                "source_label": "Support Source",
                "source_labels": ["Support Source"],
                "quantities": [{"value": "RR 0.98 (95% CI 0.90-1.07)", "interpretation": "main uncertainty estimate"}],
                "source_appraisal": {
                    "evidence_proximity": ["observational association"],
                    "decision_directness": "direct for the main outcome but not causal by itself",
                },
            },
            {
                "item_id": "counter",
                "must_use": False,
                "obligation_level": "should_include",
                "role": "strongest_counterweight",
                "answer_relation": "challenges_answer",
                "memo_function": "counterweight",
                "importance_rank": 2,
                "reader_claim": "Option A was associated with more implementation failures in one comparison.",
                "decision_relevance": "Provides a challenge estimate, RR 1.19, that may bound the neutral answer.",
                "source_label": "Risk Source",
                "source_labels": ["Risk Source"],
            },
            {
                "item_id": "boundary",
                "must_use": False,
                "obligation_level": "should_include",
                "role": "scope_boundary",
                "importance_rank": 12,
                "reader_claim": "The finding applies to adults without prior eligibility problems.",
                "decision_relevance": "Population boundary for high-risk or previously excluded participants.",
                "source_label": "Boundary Source",
                "source_labels": ["Boundary Source"],
            },
            {
                "item_id": "context",
                "must_use": False,
                "obligation_level": "should_include",
                "role": "decision_crux",
                "importance_rank": 50,
                "reader_claim": "In one trial, 2 units daily was tested during a 4 month study.",
                "decision_relevance": "This is study context, not a broad decision recommendation.",
                "source_label": "Context Source",
                "source_labels": ["Context Source"],
            },
            {
                "item_id": "causal",
                "must_use": False,
                "obligation_level": "should_include",
                "role": "decision_crux",
                "importance_rank": 55,
                "reader_claim": "The observed difference was described as driven by selection patterns.",
                "decision_relevance": "The causal explanation is plausible but comes from association evidence.",
                "source_label": "Risk Source",
                "source_labels": ["Risk Source"],
                "source_appraisal": {
                    "evidence_proximity": ["observational association"],
                    "decision_directness": "indirect for mechanism",
                },
            },
        ],
    }
