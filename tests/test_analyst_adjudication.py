from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_analyst_adjudication import (
    build_analyst_adjudication_prompt,
    run_analyst_adjudication_single_call_for_test,
    run_analyst_adjudication,
)
from epistemic_case_mapper.model_backends import ModelBackendResult


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
                    {"endpoint": "source", "claim_id": "c001", "decision_edge_role": "mechanism_or_biomarker"},
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
    assert "stable_final_answer_frame" in prompt
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
    assert "source_ids" in prompt
    assert "source_labels" not in prompt
    assert "Outcome Study" not in prompt
    assert "Equity Review" not in prompt


def test_analyst_adjudication_prompt_exposes_candidate_relation_metadata() -> None:
    prompt = build_analyst_adjudication_prompt(_relation_ledger())

    assert "relation labels as provisional model proposals" in prompt
    assert "relation_semantic_role" in prompt
    assert "mechanism_to_outcome" in prompt
    assert "source_anchor_a" in prompt
    assert "failure_condition" in prompt
    assert "endpoint_claims" in prompt
    assert "Broad neighboring relation context" not in prompt


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

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_adjudication.run_model_backend", fake_backend)
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", "1")
    monkeypatch.setenv("ECM_MODEL_PARALLELISM", "2")

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication_chunk_reports"]["chunk_count"] == 2
    assert result["analyst_adjudication_chunk_reports"]["parallelism"] == 2
    assert len(calls) == 2
    assert result["analyst_adjudication_parse_report"]["valid"] is True
    assert result["analyst_adjudication"]["rows"][1]["memo_use"] == "load_bearing_counterweight"
    assert result["analyst_adjudication"]["rows"][0]["decision_contribution"] == "This is the main observed benefit of option A."


def test_analyst_adjudication_default_chunk_size_is_two(monkeypatch) -> None:
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

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_adjudication.run_model_backend", fake_backend)
    monkeypatch.delenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", raising=False)

    result = run_analyst_adjudication(ledger, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication_chunk_reports"]["chunk_count"] == 2
    assert [chunk["row_count"] for chunk in result["analyst_adjudication_chunk_reports"]["chunks"]] == [2, 1]


def test_analyst_adjudication_invalid_live_backend_reports_failure_without_fallback(monkeypatch) -> None:
    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text='{"rows": [{"evidence_item_id": "bundle:one", "memo_use": "bad"}]}', backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

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

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

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

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    rows = {row["evidence_item_id"]: row for row in result["analyst_adjudication"]["rows"]}
    assert result["analyst_adjudication_report"]["status"] == "accepted_after_missing_row_repair"
    assert result["analyst_adjudication_parse_report"]["valid"] is True
    assert result["analyst_adjudication_chunk_reports"]["missing_row_repair_chunk_count"] == 1
    assert rows["warning:two"]["rationale"] == "Focused retry recovered the omitted warning row."


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

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

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

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication_single_call_for_test(ledger, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication"]["rows"][1]["covered_by"] == ["quantity:source:95_ci_1.25_1.57"]
