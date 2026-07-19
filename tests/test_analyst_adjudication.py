from __future__ import annotations

import json

import pytest

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication import (
    build_analyst_adjudication_prompt,
    build_missing_row_adjudication_prompt,
    run_analyst_adjudication_single_call_for_test,
    run_analyst_adjudication,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet_stage import _assert_analyst_adjudication_complete
from epistemic_case_mapper.model_backends import ModelBackendResult


@pytest.fixture(autouse=True)
def _use_legacy_adjudication_schema(monkeypatch) -> None:
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v1")


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "stable_final_answer_frame": {
            "schema_id": "stable_final_answer_frame_v1",
            "decision_question": "Should option A be adopted?",
            "answer_status": "provisional",
            "current_best_answer": "Adopt option A only if the cost exposure is bounded.",
            "classification_target_policy": "Classify relative to the provisional current_best_answer.",
            "classification_rule": "Classify every row relative to current_best_answer.",
        },
        "rows": [
            {
                "evidence_item_id": "bundle:one",
                "input_kind": "retained_bundle",
                "current_role": "strongest_support",
                "current_priority": 9,
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
                "claim": "Option A reduced losses.",
                "source_bottom_lines": [
                    {
                        "source_id": "s1",
                        "source_bottom_line": "Option A reduced downstream losses in the main outcome study.",
                        "polarity_signal": "benefit_signal",
                    }
                ],
                "source_bottom_line_signals": ["benefit_signal"],
                "source_excerpt": "Raw excerpt should stay out of adjudication prompt.",
                "source_appraisal": {
                    "decision_directness": "direct",
                    "document_types": ["trial"],
                    "interpretation_caveats": ["Do not overstate."],
                    "large_internal_notes": "This bulky appraisal detail should stay out.",
                },
                "source_use_warnings": ["quality_limit"],
            },
            {
                "evidence_item_id": "warning:two",
                "input_kind": "memo_warning",
                "current_role": "counterweight",
                "current_priority": 10,
                "source_ids": ["s2"],
                "source_labels": ["Equity Review"],
                "claim": "Option A shifted risk downstream.",
                "existing_warning_codes": ["omitted_decision_critical_evidence"],
            },
        ],
    }


def _relation_ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "relation:r001",
                "input_kind": "candidate_decision_edge",
                "current_role": "load_bearing_primary_support",
                "current_weight": "medium",
                "directionality": "supports",
                "relation_semantic_role": "supports",
                "relation_contract": {
                    "edge_basis": "source_inferred",
                    "source_anchor_a": "mechanism changed",
                    "source_anchor_b": "outcome improved",
                    "failure_condition": "The edge fails if the mechanism does not apply to the outcome.",
                },
                "candidate_pair": {
                    "pair_id": "pair_001",
                    "decision_edge_contract": "mechanism_to_outcome",
                    "pair_intent": {"intent": "mechanism_to_outcome", "allowed_relation_types": ["supports", "none"]},
                },
                "endpoint_claims": [
                    {
                        "endpoint": "source",
                        "claim_id": "c001",
                        "decision_edge_role": "mechanism_or_biomarker",
                        "source_bottom_lines": [
                            {
                                "source_id": "s1",
                                "source_bottom_line": "Mechanism evidence increased the risk marker.",
                                "polarity_signal": "increased_harm_or_risk_signal",
                            }
                        ],
                        "source_bottom_line_signals": ["increased_harm_or_risk_signal"],
                    },
                    {"endpoint": "target", "claim_id": "c002", "decision_edge_role": "outcome_finding"},
                ],
                "relation_context": [
                    {
                        "relation_id": "too_broad",
                        "rationale": "Broad neighboring relation context should not be forwarded to the model.",
                    }
                ],
                "claim": "supports: mechanism evidence may explain the outcome finding.",
                "source_excerpt": "mechanism changed | outcome improved",
            }
        ],
    }


def test_analyst_adjudication_prompt_contains_all_ledger_rows() -> None:
    prompt = build_analyst_adjudication_prompt(_ledger())

    assert "Return a strict JSON object only" in prompt
    assert "bundle:one" in prompt
    assert "warning:two" in prompt
    assert "allowed_memo_use" in prompt
    assert "allowed_answer_relation" in prompt
    assert '"answer_frame"' in prompt
    assert "current_best_answer" in prompt
    assert "classification_target_policy" in prompt
    assert "multi_option or unresolved" in prompt
    assert "rebuts an alternative answer but supports the selected/provisional current_best_answer" in prompt
    assert "Use challenges_answer only when the row weakens" in prompt
    assert "decision_contribution" in prompt
    assert "use_in_reasoning" in prompt
    assert "key_qualifier" in prompt
    assert "quantity_takeaway" in prompt
    assert "source_weight_note" in prompt
    assert "misuse_warning" in prompt
    assert "if_omitted" in prompt
    assert "Raw excerpt should stay out" not in prompt
    assert "large_internal_notes" not in prompt
    assert "source_quality" in prompt
    assert "quality_limit" in prompt
    assert "source_bottom_lines" in prompt
    assert "Option A reduced downstream losses" in prompt
    assert "benefit_signal" in prompt
    assert "source_ids" in prompt
    assert "source_labels" not in prompt
    assert "Outcome Study" not in prompt
    assert "Equity Review" not in prompt


def test_analyst_adjudication_prompt_exposes_candidate_relation_metadata() -> None:
    ledger = _relation_ledger()
    ledger["rows"][0]["relation_endpoint_answer_matrix"] = {
        "schema_id": "relation_endpoint_answer_matrix_v1",
        "relation_semantic_role": "supports",
        "endpoint_signal_summary": "mixed_endpoint_polarity",
        "endpoints": ledger["rows"][0]["endpoint_claims"],
    }
    prompt = build_analyst_adjudication_prompt(ledger)

    assert "relation labels as provisional model proposals" in prompt
    assert "classify endpoint source bottom lines first" in prompt
    assert "relation_semantic_role" in prompt
    assert "relation_endpoint_answer_matrix" in prompt
    assert "mixed_endpoint_polarity" in prompt
    assert "mechanism_to_outcome" in prompt
    assert "source_anchor_a" in prompt
    assert "failure_condition" in prompt
    assert "endpoint_claims" in prompt
    assert "Mechanism evidence increased the risk marker" in prompt
    assert "increased_harm_or_risk_signal" in prompt
    assert "Broad neighboring relation context" not in prompt


def test_missing_row_repair_prompt_is_focused_on_expected_rows() -> None:
    ledger = _ledger()
    ledger["rows"] = [ledger["rows"][1]]

    full_prompt = build_analyst_adjudication_prompt(ledger)
    repair_prompt = build_missing_row_adjudication_prompt(ledger)

    assert len(repair_prompt) < len(full_prompt)
    assert "Repair missing analyst adjudication rows" in repair_prompt
    assert "expected_evidence_item_ids" in repair_prompt
    assert "warning:two" in repair_prompt
    assert "Return exactly one row for each expected_evidence_item_id" in repair_prompt
    assert "stable_final_answer_frame" not in repair_prompt
    assert "multi_option or unresolved" not in repair_prompt


def test_analyst_adjudication_repairs_source_faithfulness_conflicted_relation(monkeypatch) -> None:
    ledger = _relation_ledger()
    ledger["stable_final_answer_frame"] = {
        "schema_id": "stable_final_answer_frame_v1",
        "answer_status": "provisional",
        "current_best_answer": "Treat option A as neutral.",
    }
    ledger["rows"][0]["source_bottom_lines"] = [
        {
            "source_id": "s1",
            "source_bottom_line": "Higher exposure was associated with increased downstream risk.",
            "polarity_signal": "increased_harm_or_risk_signal",
        }
    ]
    ledger["rows"][0]["source_bottom_line_signals"] = ["increased_harm_or_risk_signal"]
    payload = {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": ledger["decision_question"],
        "rows": [
            {
                "evidence_item_id": "relation:r001",
                "memo_use": "load_bearing_primary_support",
                "answer_relation": "supports_answer",
                "target_answer_option": "neutral_or_not_meaningfully_harmful",
                "effect_on_final_answer": "supports current_best_answer",
                "importance_rank": 1,
                "rationale": "Treats the relation as support for neutral exposure.",
            }
        ],
        "overall_rationale": "fixture",
    }

    def fake_backend(prompt, *args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", "1")

    result = run_analyst_adjudication(ledger, backend="fake", backend_timeout=30, backend_retries=0)

    row = result["analyst_adjudication"]["rows"][0]
    assert row["memo_use"] == "load_bearing_counterweight"
    assert row["answer_relation"] == "challenges_answer"
    assert row["effect_on_final_answer"] == "weakens current_best_answer"
    repair = result["analyst_source_faithfulness_repair_report"]
    assert repair["status"] == "repaired"
    assert repair["warning_count_before"] == 1
    assert repair["warning_count_after"] == 0
    assert repair["repaired_evidence_item_ids"] == ["relation:r001"]


def test_analyst_adjudication_prompt_backend_scaffolds_all_rows() -> None:
    result = run_analyst_adjudication(_ledger(), backend="prompt", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "prompt_backend_scaffold"
    assert result["analyst_adjudication_parse_report"]["status"] == "ready"
    assert [row["evidence_item_id"] for row in result["analyst_adjudication"]["rows"]] == ["bundle:one", "warning:two"]
    assert result["analyst_adjudication"]["rows"][1]["memo_use"] == "needs_human_or_model_review"
    assert result["analyst_adjudication"]["rows"][0]["answer_relation"] == "supports_answer"
    assert result["analyst_adjudication_chunk_reports"]["chunks"][0]["status"] == "prompt_backend_scaffold"


def test_analyst_adjudication_accepts_valid_live_backend(monkeypatch) -> None:
    payload = {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "bundle:one",
                "memo_use": "load_bearing_primary_support",
                "importance_rank": 1,
                "rationale": "Direct outcome evidence.",
                "decision_contribution": "This is the main observed benefit of option A.",
                "use_in_reasoning": "answer anchor",
                "key_qualifier": "Only applies if cost exposure is bounded.",
                "quantity_takeaway": "",
                "source_weight_note": "Direct study evidence should move the answer substantially.",
                "misuse_warning": "Do not treat this as evidence that downstream risk disappears.",
                "if_omitted": "The decision model would lose the main support for adoption.",
            },
            {
                "evidence_item_id": "warning:two",
                "memo_use": "load_bearing_counterweight",
                "importance_rank": 2,
                "rationale": "Important omitted limitation.",
            },
        ],
    }

    calls = []

    def fake_backend(prompt, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        rows = [row for row in payload["rows"] if row["evidence_item_id"] in prompt]
        return ModelBackendResult(text=json.dumps({**payload, "rows": rows}), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", "1")
    monkeypatch.setenv("ECM_MODEL_PARALLELISM", "2")

    progress_events = []

    def progress(stage: str, status: str, details: dict | None = None) -> None:
        progress_events.append((stage, status, details or {}))

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0, progress=progress)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication_chunk_reports"]["chunk_count"] == 2
    assert result["analyst_adjudication_chunk_reports"]["parallelism"] == 2
    assert len(calls) == 2
    assert result["analyst_adjudication_parse_report"]["valid"] is True
    assert result["analyst_adjudication"]["rows"][1]["memo_use"] == "load_bearing_counterweight"
    assert result["analyst_adjudication"]["rows"][0]["decision_contribution"] == "This is the main observed benefit of option A."
    chunk_events = [event for event in progress_events if event[2].get("substage") == "analyst_adjudication_chunk"]
    assert [event[1] for event in chunk_events].count("started") == 2
    assert [event[1] for event in chunk_events].count("completed") == 2
    assert {event[2]["chunk_index"] for event in chunk_events if event[1] == "completed"} == {1, 2}


def test_analyst_adjudication_default_chunk_size_is_eight(monkeypatch) -> None:
    ledger = _ledger()
    ledger["rows"] = [
        *ledger["rows"],
        {
            "evidence_item_id": "scope:three",
            "input_kind": "memo_warning",
            "current_role": "scope_limit",
            "current_priority": 8,
            "source_ids": ["s3"],
            "source_labels": ["Scope Review"],
            "claim": "Option A only applies to bounded deployments.",
        },
    ]

    def fake_backend(prompt, *args, **kwargs) -> ModelBackendResult:
        evidence_ids = [
            evidence_id
            for evidence_id in ["bundle:one", "warning:two", "scope:three"]
            if evidence_id in prompt
        ]
        rows = [
            {
                "evidence_item_id": evidence_id,
                "memo_use": "scope_or_applicability",
                "answer_relation": "bounds_scope",
                "importance_rank": index + 1,
                "rationale": "Fixture row for default chunk-size behavior.",
                "source_ids": [],
                "quantity_values": [],
            }
            for index, evidence_id in enumerate(evidence_ids)
        ]
        return ModelBackendResult(
            text=json.dumps(
                {
                    "schema_id": "analyst_adjudication_v1",
                    "decision_question": ledger["decision_question"],
                    "rows": rows,
                    "overall_rationale": "Fixture adjudication.",
                }
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)
    monkeypatch.delenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", raising=False)

    result = run_analyst_adjudication(ledger, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication_chunk_reports"]["chunk_count"] == 1
    assert [chunk["row_count"] for chunk in result["analyst_adjudication_chunk_reports"]["chunks"]] == [3]


def test_analyst_adjudication_invalid_live_backend_reports_failure_without_fallback(monkeypatch) -> None:
    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text='{"rows": [{"evidence_item_id": "bundle:one", "memo_use": "bad"}]}', backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "model_output_invalid"
    assert result["analyst_adjudication_report"]["accepted"] is False
    assert result["analyst_adjudication_chunk_reports"]["scaffold_chunk_count"] == 0
    assert result["analyst_adjudication_chunk_reports"]["failed_chunk_count"] == 1
    assert result["analyst_adjudication_parse_report"]["status"] == "warning"
    assert result["analyst_adjudication_parse_report"]["valid"] is False
    assert result["analyst_adjudication"]["rows"] == []


def test_analyst_adjudication_salvages_valid_rows_from_invalid_chunk(monkeypatch) -> None:
    payload = {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "bundle:one",
                "memo_use": "load_bearing_primary_support",
                "answer_relation": "supports_answer",
                "importance_rank": 1,
                "rationale": "The model identified direct outcome evidence as load-bearing.",
                "source_ids": ["s1"],
                "quantity_values": [],
            },
            {
                "evidence_item_id": "warning:two",
                "memo_use": "not an allowed label",
                "importance_rank": 2,
                "rationale": "This row should fail local validation.",
            },
        ],
        "unexpected_extra_field": "makes the whole payload invalid",
    }

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    rows = {row["evidence_item_id"]: row for row in result["analyst_adjudication"]["rows"]}
    chunk_report = result["analyst_adjudication_chunk_reports"]["chunks"][0]
    assert result["analyst_adjudication_report"]["status"] == "model_output_invalid"
    assert result["analyst_adjudication_report"]["accepted"] is False
    assert chunk_report["status"] == "model_output_invalid_salvaged_model_rows"
    assert chunk_report["salvaged_model_row_count"] == 1
    assert chunk_report["missing_unsalvaged_row_count"] == 1
    assert rows["bundle:one"]["rationale"] == "The model identified direct outcome evidence as load-bearing."
    assert "warning:two" not in rows


def test_analyst_adjudication_repairs_missing_salvaged_rows_with_focused_call(monkeypatch) -> None:
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        if '"warning:two"' in prompt and '"bundle:one"' not in prompt:
            return ModelBackendResult(
                text=json.dumps(
                    {
                        "schema_id": "analyst_adjudication_v1",
                        "decision_question": "Should option A be adopted?",
                        "rows": [
                            {
                                "evidence_item_id": "warning:two",
                                "memo_use": "load_bearing_counterweight",
                                "answer_relation": "challenges_answer",
                                "importance_rank": 2,
                                "rationale": "Focused retry recovered the omitted warning row.",
                                "source_ids": ["s2"],
                                "quantity_values": [],
                            }
                        ],
                        "overall_rationale": "Focused repair.",
                    }
                ),
                backend="fake",
            )
        return ModelBackendResult(
            text=json.dumps(
                {
                    "schema_id": "analyst_adjudication_v1",
                    "decision_question": "Should option A be adopted?",
                    "rows": [
                        {
                            "evidence_item_id": "bundle:one",
                            "memo_use": "load_bearing_primary_support",
                            "answer_relation": "supports_answer",
                            "importance_rank": 1,
                            "rationale": "The model returned only the support row.",
                            "source_ids": ["s1"],
                            "quantity_values": [],
                        }
                    ],
                    "overall_rationale": "Incomplete first pass.",
                }
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    rows = {row["evidence_item_id"]: row for row in result["analyst_adjudication"]["rows"]}
    assert result["analyst_adjudication_report"]["status"] == "accepted_after_missing_row_repair"
    assert result["analyst_adjudication_parse_report"]["valid"] is True
    assert result["analyst_adjudication_chunk_reports"]["missing_row_repair_chunk_count"] == 1
    assert rows["warning:two"]["rationale"] == "Focused retry recovered the omitted warning row."


def test_analyst_adjudication_retries_missing_row_repair_rounds(monkeypatch) -> None:
    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "2")
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        if len(calls) <= 2:
            return ModelBackendResult(
                text=json.dumps(
                    {
                        "schema_id": "analyst_adjudication_v1",
                        "decision_question": "Should option A be adopted?",
                        "rows": [
                            {
                                "evidence_item_id": "bundle:one",
                                "memo_use": "load_bearing_primary_support",
                                "answer_relation": "supports_answer",
                                "importance_rank": 1,
                                "rationale": "The first chunk retained only the support row.",
                                "source_ids": ["s1"],
                                "quantity_values": [],
                            }
                        ],
                        "overall_rationale": "Incomplete first pass.",
                    }
                ),
                backend="fake",
            )
        if len(calls) <= 4:
            return ModelBackendResult(
                text=json.dumps(
                    {
                        "schema_id": "analyst_adjudication_v1",
                        "decision_question": "Should option A be adopted?",
                        "rows": [],
                        "overall_rationale": "The first focused repair still omitted the missing row.",
                    }
                ),
                backend="fake",
            )
        return ModelBackendResult(
            text=json.dumps(
                {
                    "schema_id": "analyst_adjudication_v1",
                    "decision_question": "Should option A be adopted?",
                    "rows": [
                        {
                            "evidence_item_id": "warning:two",
                            "memo_use": "load_bearing_counterweight",
                            "answer_relation": "challenges_answer",
                            "importance_rank": 2,
                            "rationale": "The second focused repair recovered the omitted warning row.",
                            "source_ids": ["s2"],
                            "quantity_values": [],
                        }
                    ],
                    "overall_rationale": "Focused repair.",
                }
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    rows = {row["evidence_item_id"]: row for row in result["analyst_adjudication"]["rows"]}
    assert result["analyst_adjudication_report"]["status"] == "accepted_after_missing_row_repair"
    assert result["analyst_adjudication_parse_report"]["valid"] is True
    assert result["analyst_adjudication_chunk_reports"]["missing_row_repair_round_count"] == 2
    assert rows["warning:two"]["rationale"] == "The second focused repair recovered the omitted warning row."


def test_analyst_adjudication_stage_gate_fails_before_decision_model_on_missing_rows() -> None:
    with pytest.raises(RuntimeError, match="warning:two"):
        _assert_analyst_adjudication_complete(
            {
                "analyst_adjudication_report": {"status": "model_output_invalid"},
                "analyst_adjudication_parse_report": {
                    "schema_id": "analyst_adjudication_parse_report_v1",
                    "status": "warning",
                    "valid": False,
                    "missing_evidence_item_ids": ["warning:two"],
                    "issues": ["missing_ledger_rows"],
                },
            }
        )


def test_single_call_accepts_repairable_model_json(monkeypatch) -> None:
    raw = """```json
{
  "schema_id": "analyst_adjudication_v1",
  "decision_question": "Should option A be adopted?",
  "rows": [
    {
      "evidence_item_id": "bundle:one",
      "memo_use": "load_bearing_primary_support",
      "importance_rank": 1,
      "rationale": "Direct outcome evidence.",
      "covered_by": null,
      "source_ids": ["s1",],
      "quantity_values": [],
    },
    {
      "evidence_item_id": "warning:two",
      "memo_use": "load_bearing_counterweight",
      "importance_rank": 2,
      "rationale": "Important omitted limitation.",
      "covered_by": [],
      "source_ids": ["s2"],
      "quantity_values": [],
    },
  ],
  "overall_rationale": "Repairs should handle trailing commas and null lists."
}
```"""

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=raw, backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication_single_call_for_test(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication"]["rows"][0]["covered_by"] == []
    assert result["analyst_adjudication_parse_report"]["valid"] is True


def test_analyst_adjudication_repairs_unambiguous_covered_by_id_alias(monkeypatch) -> None:
    ledger = {
        **_ledger(),
        "rows": [
            {"evidence_item_id": "quantity:source:95_ci_1.25_1.57"},
            {"evidence_item_id": "quantity:source:95_ci_1.21_1.37"},
        ],
    }
    payload = {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "quantity:source:95_ci_1.25_1.57",
                "memo_use": "quantitative_anchor",
                "importance_rank": 1,
                "rationale": "Anchor.",
            },
            {
                "evidence_item_id": "quantity:source:95_ci_1.21_1.37",
                "memo_use": "covered_by_group",
                "importance_rank": 2,
                "rationale": "Redundant interval.",
                "covered_by": ["quantity:source:95_ci_1.25-1.57"],
            },
        ],
    }

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication_single_call_for_test(ledger, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication"]["rows"][1]["covered_by"] == ["quantity:source:95_ci_1.25_1.57"]
