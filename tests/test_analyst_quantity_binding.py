from __future__ import annotations

import json
import re

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_evidence_ledger import build_analyst_map_evidence_ledger
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_packet import build_analyst_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_quantity_binding import (
    build_analyst_quantity_binding_report,
    merge_quantity_adjudication,
    run_analyst_quantity_binding,
)
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_analyst_packet import _adjudication, _ledger, _packet


def test_analyst_quantity_binding_blocks_off_scope_age_quantity_from_memo_obligations() -> None:
    packet = {
        "decision_question": "For generally healthy adults, should eggs be treated as harmful or neutral for cardiovascular risk?",
        "answer_frame": {
            "default_answer": "Treat moderate egg intake as neutral for generally healthy adults.",
            "confidence": "medium",
        },
        "source_trail": [
            {"source_id": "adult_cvd", "source_label": "Adult CVD Cohort"},
            {"source_id": "child_guideline", "source_label": "Child Nutrition Guideline"},
        ],
    }
    ledger = {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": packet["decision_question"],
        "rows": [
            {
                "evidence_item_id": "claim:adult_cvd",
                "input_kind": "claim",
                "source_ids": ["adult_cvd"],
                "source_labels": ["Adult CVD Cohort"],
                "claim": "Moderate egg consumption up to one egg per day was not associated with incident cardiovascular disease risk in adults.",
                "source_excerpt": "At least one egg per day versus less than one egg per month had hazard ratio 0.93, 95% confidence interval 0.82 to 1.05.",
                "quantity_values": ["hazard ratio 0.93", "95% confidence interval 0.82 to 1.05"],
            },
            {
                "evidence_item_id": "claim:child_age_scope",
                "input_kind": "claim",
                "source_ids": ["child_guideline"],
                "source_labels": ["Child Nutrition Guideline"],
                "claim": "Eggs are included as a recommended food for children aged 6 months and older.",
                "source_excerpt": "For toddlers 12 to 24 months old whose diets do not include meat, the committee advised providing eggs.",
                "quantity_values": ["6 to 12 months old", "12 to 24 months old"],
            },
        ],
    }
    decision_model = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": packet["decision_question"],
        "direct_answer": "Treat moderate egg intake as neutral for generally healthy adults.",
        "confidence": "medium",
        "overall_rationale": "Adult CVD outcome evidence carries the decision; child feeding guidance is only background.",
        "evidence_groups": [
            {
                "group_id": "adult_safety",
                "proposition": "Moderate egg consumption up to one egg per day is not associated with increased cardiovascular disease risk in generally healthy adults.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["claim:adult_cvd", "claim:child_age_scope"],
                "rationale": "Use adult cardiovascular outcome evidence as the support proposition.",
            }
        ],
    }

    result = build_analyst_packet_bundle(packet=packet, ledger=ledger, adjudication={"rows": []}, decision_model=decision_model)

    binding = result["analyst_quantity_binding_report"]
    approved_values = {row["value"] for row in binding["approved_bindings"]}
    rejected_values = {row["value"] for row in binding["rejected_bindings"]}
    memo_item = result["analyst_memo_ready_packet"]["evidence_items"][0]
    memo_quantity_values = {row["value"] for row in memo_item["quantities"]}

    assert "95% confidence interval 0.82 to 1.05" in approved_values
    assert "6 to 12 months old" in rejected_values
    assert "12 to 24 months old" in rejected_values
    assert "6 to 12 months old" not in memo_quantity_values
    assert "12 to 24 months old" not in memo_quantity_values
    assert "6 to 12 months old" not in memo_item["reader_claim"]
    assert binding["rejected_count"] == 2


def test_analyst_quantity_binding_prompt_backend_returns_visible_report() -> None:
    result = build_analyst_packet_bundle(packet=_packet(), ledger=_ledger(), adjudication=_adjudication())

    binding = run_analyst_quantity_binding(
        synthesis_packet=result["analyst_synthesis_packet"],
        ledger=_ledger(),
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
    )

    assert binding["analyst_quantity_binding_report"]["schema_id"] == "analyst_quantity_binding_report_v1"
    assert binding["analyst_quantity_binding_run_report"]["status"] == "prompt_backend_deterministic"
    assert binding["analyst_quantity_binding_prompt"]


def test_analyst_quantity_binding_prompt_compacts_audit_only_fields() -> None:
    result = build_analyst_packet_bundle(packet=_packet(), ledger=_ledger(), adjudication=_adjudication())

    binding = run_analyst_quantity_binding(
        synthesis_packet=result["analyst_synthesis_packet"],
        ledger=_ledger(),
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
    )

    prompt = binding["analyst_quantity_binding_prompt"]
    assert "source_excerpt" not in prompt
    assert "deterministic_memo_use" not in prompt
    assert "deterministic_warnings" not in prompt


def test_analyst_quantity_binding_prompt_only_sends_residual_claim_relevant_quantities(monkeypatch) -> None:
    ledger = {
        "decision_question": "Should option A be treated as lowering outcome risk?",
        "rows": [
            {
                "evidence_item_id": "claim:outcome",
                "claim": "Option A at one serving per day was associated with lower outcome risk.",
                "source_excerpt": "The hazard ratio was 0.93 with 95% confidence interval 0.82 to 1.05 in 33 risk estimates from 2019.",
                "source_labels": ["Outcome Review"],
                "claim_quantities": [
                    {
                        "value": "one serving per day",
                        "quantity_role": "exposure_or_intervention_level",
                        "quantity_type": "dose",
                        "local_interpretation": "Exposure level already bound to the claim.",
                        "retention_hint": "must_retain",
                    }
                ],
                "claim_bound_quantity_values": ["one serving per day"],
                "quantity_values": ["one serving per day", "0.93", "33 risk estimates", "2019"],
                "residual_quantity_values": ["0.93", "33 risk estimates", "2019"],
                "residual_quantity_candidate_values": ["0.93"],
            }
        ],
    }
    packet = {
        "decision_question": ledger["decision_question"],
        "primary_reasoning_chain": [
            {
                "group_id": "outcome_group",
                "memo_role": "quantitative_anchor",
                "proposition": "Option A was associated with lower outcome risk.",
                "covered_evidence_item_ids": ["claim:outcome"],
            }
        ],
    }
    prompts = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        payload = json.loads(re.search(r"\{.*\}", prompt, flags=re.DOTALL).group(0))
        assert [row["quantity"] for row in payload["candidates"]] == ["0.93"]
        return ModelBackendResult(
            text=json.dumps(
                {
                    "schema_id": "analyst_quantity_binding_adjudication_v1",
                    "bindings": [
                        {
                            "candidate_id": payload["candidates"][0]["candidate_id"],
                            "memo_use": "yes",
                            "quantity_role": "decision_anchor",
                            "must_retain": True,
                            "interpretation": "0.93 is the residual risk estimate for the outcome claim.",
                            "rationale": "It calibrates the outcome direction.",
                            "retention_phrase": "hazard ratio 0.93",
                            "required_for_memo_reason": "It quantifies the answer-relevant effect estimate.",
                            "safe_to_omit_reason": "",
                        }
                    ],
                }
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_quantity_binding.run_model_backend", fake_backend)

    result = run_analyst_quantity_binding(
        synthesis_packet=packet,
        ledger=ledger,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    prompt = prompts[0]
    assert "0.93" in prompt
    assert "33 risk estimates" not in prompt
    assert "2019" not in prompt
    assert "one serving per day" not in prompt
    values = {row["value"]: row for row in result["analyst_quantity_binding_report"]["approved_bindings"]}
    assert values["one serving per day"]["candidate_origin"] == "claim_map_bound"
    assert values["0.93"]["candidate_origin"] == "residual_source_quantity"


def test_map_ledger_residual_quantity_candidates_exclude_bare_descriptor_percentages() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "claim": "Option A was associated with lower cardiovascular risk.",
                "source_id": "s1",
                "claim_quantities": [
                    {
                        "value": "0.93",
                        "quantity_role": "effect_estimate",
                        "local_interpretation": "Main effect estimate.",
                        "retention_hint": "must_retain",
                    }
                ],
                "whole_doc_source_card": {
                    "quantities": [
                        "0.93",
                        "95% confidence interval 0.82 to 1.05",
                        "62.3%",
                        "33 risk estimates",
                        "2019",
                    ]
                },
            }
        ],
        "relations": [],
    }
    scaffold = {"source_citation_labels": {"s1": "Outcome Review"}}

    ledger = build_analyst_map_evidence_ledger(candidate_map, scaffold, question="Should option A be used?")
    row = ledger["rows"][0]

    assert row["claim_bound_quantity_values"] == ["0.93"]
    assert "95% confidence interval 0.82 to 1.05" in row["residual_quantity_candidate_values"]
    assert "62.3%" not in row["residual_quantity_candidate_values"]
    assert "33 risk estimates" not in row["residual_quantity_candidate_values"]
    assert "2019" not in row["residual_quantity_candidate_values"]


def test_analyst_quantity_binding_missing_model_rows_do_not_create_mandatory_quantities() -> None:
    ledger = {
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "claim:support",
                "claim": "Option A reduced losses in the main outcome study.",
                "source_labels": ["Outcome Study"],
                "quantity_values": ["25% reduction", "18% reduction"],
                "residual_quantity_candidate_values": ["25% reduction", "18% reduction"],
            }
        ],
    }
    packet = {
        "decision_question": "Should option A be adopted?",
        "primary_reasoning_chain": [
            {
                "group_id": "support",
                "memo_role": "quantitative_anchor",
                "proposition": "Option A reduced losses.",
                "covered_evidence_item_ids": ["claim:support"],
            }
        ],
    }
    deterministic = build_analyst_quantity_binding_report(
        synthesis_packet=packet,
        ledger=ledger,
    )
    first_candidate = deterministic["candidate_bindings"][0]

    merged, parse_report = merge_quantity_adjudication(
        deterministic,
        {
            "schema_id": "analyst_quantity_binding_adjudication_v1",
            "bindings": [
                {
                    "candidate_id": first_candidate["candidate_id"],
                    "memo_use": "yes",
                    "quantity_role": "decision_anchor",
                    "must_retain": True,
                    "interpretation": "The key quantity calibrates the decision.",
                    "rationale": "It is the only load-bearing quantity in this fixture.",
                    "retention_phrase": "key quantity for the decision",
                    "required_for_memo_reason": "The answer would be less calibrated without it.",
                    "safe_to_omit_reason": "",
                }
            ],
        },
    )

    assert parse_report["status"] == "warning"
    assert merged["must_retain_count"] == 1
    assert len(merged["must_retain_bindings"]) == 1
    assert all(
        row["memo_use"] != "yes"
        for row in merged["candidate_bindings"]
        if row["candidate_id"] != first_candidate["candidate_id"]
    )


def test_analyst_quantity_binding_salvages_valid_rows_from_invalid_payload() -> None:
    ledger = {
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "claim:support",
                "claim": "Option A reduced losses in the main outcome study.",
                "source_labels": ["Outcome Study"],
                "quantity_values": ["25% reduction", "18% reduction"],
                "residual_quantity_candidate_values": ["25% reduction", "18% reduction"],
            }
        ],
    }
    packet = {
        "decision_question": "Should option A be adopted?",
        "primary_reasoning_chain": [
            {
                "group_id": "support",
                "memo_role": "quantitative_anchor",
                "proposition": "Option A reduced losses.",
                "covered_evidence_item_ids": ["claim:support"],
            }
        ],
    }
    deterministic = build_analyst_quantity_binding_report(synthesis_packet=packet, ledger=ledger)
    first_candidate, second_candidate = deterministic["candidate_bindings"][:2]

    merged, parse_report = merge_quantity_adjudication(
        deterministic,
        {
            "schema_id": "analyst_quantity_binding_adjudication_v1",
            "bindings": [
                {
                    "candidate_id": first_candidate["candidate_id"],
                    "memo_use": "yes",
                    "quantity_role": "decision_anchor",
                    "must_retain": True,
                    "interpretation": "The 25% reduction calibrates the answer-relevant effect.",
                    "rationale": "It quantifies the load-bearing support proposition.",
                    "retention_phrase": "25% reduction",
                    "required_for_memo_reason": "The memo would be less calibrated without the effect size.",
                    "safe_to_omit_reason": "",
                },
                {
                    "candidate_id": second_candidate["candidate_id"],
                    "memo_use": "no",
                    "quantity_role": "audit_only",
                    "must_retain": True,
                    "interpretation": "",
                    "rationale": "",
                },
            ],
            "extra_field": "invalidates full payload but not the first row",
        },
    )

    rows = {row["candidate_id"]: row for row in merged["candidate_bindings"]}
    assert parse_report["status"] == "salvaged_with_warnings"
    assert parse_report["accepted_binding_count"] == 1
    assert parse_report["invalid_model_row_count"] == 1
    assert rows[first_candidate["candidate_id"]]["binding_source"] == "model"
    assert rows[first_candidate["candidate_id"]]["must_retain"] is True
    assert rows[second_candidate["candidate_id"]]["binding_source"] == "model_missing_context_only"
    assert rows[second_candidate["candidate_id"]]["memo_use"] == "context_only"


def test_analyst_quantity_binding_batches_large_candidate_sets(monkeypatch) -> None:
    ledger = {
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": f"claim:{index}",
                "claim": f"Outcome claim {index}",
                "source_labels": ["Synthetic Review"],
                "quantity_values": [f"{index}% effect"],
                "residual_quantity_candidate_values": [f"{index}% effect"],
            }
            for index in range(40)
        ],
    }
    packet = {
        "decision_question": "Should option A be adopted?",
        "primary_reasoning_chain": [
            {
                "group_id": "large_group",
                "memo_role": "quantitative_anchor",
                "proposition": "Option A has many quantitative traces.",
                "covered_evidence_item_ids": [f"claim:{index}" for index in range(40)],
            }
        ],
    }
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        payload = json.loads(re.search(r"\{.*\}", prompt, flags=re.DOTALL).group(0))
        is_anchor = lambda candidate_id: candidate_id.endswith("::0_effect")
        bindings = [
            {
                "candidate_id": row["candidate_id"],
                "memo_use": "yes" if is_anchor(row["candidate_id"]) else "context_only",
                "quantity_role": "decision_anchor" if is_anchor(row["candidate_id"]) else "study_descriptor",
                "must_retain": is_anchor(row["candidate_id"]),
                "interpretation": "Quantity interpretation.",
                "rationale": "Batch test rationale.",
                "retention_phrase": "0% effect anchor" if is_anchor(row["candidate_id"]) else "",
                "required_for_memo_reason": "Synthetic anchor." if is_anchor(row["candidate_id"]) else "",
                "safe_to_omit_reason": "" if is_anchor(row["candidate_id"]) else "Not the synthetic anchor.",
            }
            for row in payload["candidates"]
        ]
        return ModelBackendResult(text=json.dumps({"schema_id": "analyst_quantity_binding_adjudication_v1", "bindings": bindings}), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_quantity_binding.run_model_backend", fake_backend)

    result = run_analyst_quantity_binding(
        synthesis_packet=packet,
        ledger=ledger,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    report = result["analyst_quantity_binding_report"]
    parse = result["analyst_quantity_binding_parse_report"]
    assert len(calls) == 1
    assert parse["missing_candidate_ids"] == []
    assert parse["model_candidate_prefilter_report"]["selected_candidate_count"] == 4
    assert parse["model_candidate_prefilter_report"]["prefiltered_context_only_count"] == 36
    assert report["candidate_count"] == 40
    assert report["must_retain_count"] == 1
    assert sum(row["memo_use"] == "context_only" for row in report["candidate_bindings"]) == 39
