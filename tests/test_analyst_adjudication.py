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
        "rows": [
            {
                "evidence_item_id": "bundle:one",
                "input_kind": "retained_bundle",
                "current_role": "strongest_support",
                "current_priority": 9,
                "source_ids": ["s1"],
                "source_labels": ["Outcome Study"],
                "claim": "Option A reduced losses.",
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
                "claim": "supports: mechanism evidence may explain the outcome finding.",
                "source_excerpt": "mechanism changed | outcome improved",
            }
        ],
    }


def test_analyst_adjudication_prompt_contains_all_ledger_rows() -> None:
    prompt = build_analyst_adjudication_prompt(_ledger())

    assert "Return strict JSON only" in prompt
    assert "bundle:one" in prompt
    assert "warning:two" in prompt
    assert "allowed_memo_use" in prompt


def test_analyst_adjudication_prompt_exposes_candidate_relation_metadata() -> None:
    prompt = build_analyst_adjudication_prompt(_relation_ledger())

    assert "relation labels as provisional model proposals" in prompt
    assert "relation_semantic_role" in prompt
    assert "mechanism_to_outcome" in prompt
    assert "source_anchor_a" in prompt
    assert "failure_condition" in prompt
    assert "endpoint_claims" in prompt


def test_analyst_adjudication_prompt_backend_scaffolds_all_rows() -> None:
    result = run_analyst_adjudication(_ledger(), backend="prompt", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "prompt_backend_scaffold"
    assert result["analyst_adjudication_parse_report"]["status"] == "ready"
    assert [row["evidence_item_id"] for row in result["analyst_adjudication"]["rows"]] == ["bundle:one", "warning:two"]
    assert result["analyst_adjudication"]["rows"][1]["memo_use"] == "needs_human_or_model_review"
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


def test_analyst_adjudication_invalid_live_backend_falls_back_with_report(monkeypatch) -> None:
    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text='{"rows": [{"evidence_item_id": "bundle:one", "memo_use": "bad"}]}', backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_analyst_adjudication.run_model_backend", fake_backend)

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted_with_chunk_scaffold"
    assert result["analyst_adjudication_chunk_reports"]["scaffold_chunk_count"] == 1
    assert result["analyst_adjudication_parse_report"]["status"] == "ready"
    assert result["analyst_adjudication"]["rows"][0]["evidence_item_id"] == "bundle:one"


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
