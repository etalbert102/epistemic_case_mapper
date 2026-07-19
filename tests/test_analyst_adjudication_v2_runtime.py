from __future__ import annotations

import json

import pytest

from epistemic_case_mapper.model_backends import ModelBackendResult
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication import run_analyst_adjudication
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2 import (
    build_analyst_adjudication_schema_comparison,
)


def _ledger() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "stable_final_answer_frame": {
            "answer_status": "provisional",
            "current_best_answer": "Adopt option A when cost exposure is bounded.",
        },
        "rows": [
            {
                "evidence_item_id": "support:one",
                "current_role": "strongest_support",
                "current_priority": 4,
                "source_ids": ["s1"],
                "quantity_values": ["12%"],
                "claim": "Option A reduced losses by 12%.",
            },
            {
                "evidence_item_id": "warning:two",
                "current_role": "counterweight",
                "current_priority": 2,
                "source_ids": ["s2"],
                "claim": "Option A shifted risk downstream.",
            },
        ],
    }


def _compact_row(evidence_id: str) -> dict:
    counterweight = evidence_id.startswith("warning")
    return {
        "evidence_item_id": evidence_id,
        "memo_use": "load_bearing_counterweight" if counterweight else "load_bearing_primary_support",
        "answer_relation": "challenges_answer" if counterweight else "supports_answer",
        "priority": "core",
        "reason": "Decision-bearing fixture evidence.",
    }


def test_v2_runtime_supplies_response_schema_and_returns_canonical_artifact(monkeypatch) -> None:
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(kwargs)
        evidence_ids = [evidence_id for evidence_id in ("support:one", "warning:two") if evidence_id in prompt]
        return ModelBackendResult(text=json.dumps({"rows": [_compact_row(evidence_id) for evidence_id in evidence_ids]}), backend="fake")

    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v2")
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", "1")
    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2.run_model_backend", fake_backend)

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication_parse_report"]["valid"] is True
    assert result["analyst_adjudication_schema_report"]["schema_version"] == "v2"
    assert result["analyst_adjudication_schema_report"]["model_row_field_count"] == 7
    assert all(call["response_schema"] for call in calls)
    rows = {row["evidence_item_id"]: row for row in result["analyst_adjudication"]["rows"]}
    assert rows["support:one"]["source_ids"] == ["s1"]
    assert rows["support:one"]["quantity_values"] == ["12%"]
    assert rows["warning:two"]["memo_use"] == "load_bearing_counterweight"


def test_v2_is_the_default_schema(monkeypatch) -> None:
    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        evidence_ids = [evidence_id for evidence_id in ("support:one", "warning:two") if evidence_id in prompt]
        return ModelBackendResult(
            text=json.dumps({"rows": [_compact_row(evidence_id) for evidence_id in evidence_ids]}),
            backend="fake",
        )

    monkeypatch.delenv("ECM_ANALYST_ADJUDICATION_SCHEMA", raising=False)
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", "2")
    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2.run_model_backend",
        fake_backend,
    )

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_schema_report"]["schema_version"] == "v2"
    assert result["analyst_adjudication_parse_report"]["valid"] is True


def test_v2_prompt_backend_reports_no_response_schema(monkeypatch) -> None:
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v2")

    result = run_analyst_adjudication(_ledger(), backend="prompt", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_schema_report"]["response_schema_supplied"] is False


def test_v2_runtime_repairs_a_missing_row_with_focused_call(monkeypatch) -> None:
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        if len(calls) == 1:
            return ModelBackendResult(text=json.dumps({"rows": [_compact_row("support:one")]}), backend="fake")
        return ModelBackendResult(text=json.dumps({"rows": [_compact_row("warning:two")]}), backend="fake")

    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v2")
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", "2")
    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "1")
    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2.run_model_backend", fake_backend)

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted_after_missing_row_repair"
    assert result["analyst_adjudication_schema_report"]["first_pass_missing_row_count"] == 1
    assert result["analyst_adjudication_chunk_reports"]["missing_row_repair_chunk_count"] == 1
    assert result["analyst_adjudication_parse_report"]["valid"] is True


def test_runtime_rejects_unknown_schema_version(monkeypatch) -> None:
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v3")
    with pytest.raises(ValueError, match="must be v1 or v2"):
        run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)


def test_schema_comparison_flags_high_impact_role_changes() -> None:
    baseline = {"rows": [{"evidence_item_id": "one", "memo_use": "load_bearing_primary_support", "answer_relation": "supports_answer"}]}
    candidate = {"rows": [{"evidence_item_id": "one", "memo_use": "load_bearing_counterweight", "answer_relation": "challenges_answer"}]}

    report = build_analyst_adjudication_schema_comparison(baseline, candidate)

    assert report["difference_count"] == 1
    assert report["high_impact_difference_count"] == 1
    assert report["differences"][0]["changed_fields"] == ["memo_use", "answer_relation"]


@pytest.mark.parametrize(
    "wrapper",
    [None, "results", "evidence_items", "evidence_evaluations", "triaged_evidence"],
)
def test_v2_runtime_repairs_known_gemma_response_shapes(monkeypatch, wrapper) -> None:
    ledger = _ledger()
    ledger["rows"] = ledger["rows"][:1]
    payload = [
        {
            "evidence_item_id": "support:one",
            "memo_use": "contextualizes_answer",
            "answer_relation": "context",
            "priority": "medium",
            "reason": "Gemma-style compact response.",
        }
    ]

    response = payload if wrapper is None else {wrapper: payload}

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(response), backend="fake")

    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v2")
    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "1")
    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2.run_model_backend",
        fake_backend,
    )

    result = run_analyst_adjudication(ledger, backend="fake", backend_timeout=30, backend_retries=0)
    row = result["analyst_adjudication"]["rows"][0]

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert row["memo_use"] == "mechanism_or_context"
    assert row["answer_relation"] == "contextualizes_answer"
    assert row["importance_rank"] == 1


@pytest.mark.parametrize(
    "response",
    [
        {"items": ["not-a-row"]},
        {"items": [_compact_row("support:one")], "metadata": {}},
    ],
)
def test_v2_runtime_rejects_non_row_response_wrappers(monkeypatch, response) -> None:
    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(response), backend="fake")

    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v2")
    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "1")
    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2.run_model_backend",
        fake_backend,
    )

    result = run_analyst_adjudication(_ledger(), backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "model_output_invalid"
    assert result["analyst_adjudication"]["rows"] == []
