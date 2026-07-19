from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from epistemic_case_mapper.model_backends import ModelBackendResult
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication import (
    build_analyst_adjudication_prompt,
    run_analyst_adjudication,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2 import (
    adapt_analyst_adjudication_v2,
    build_analyst_adjudication_prompt_v2,
    build_analyst_adjudication_schema_comparison,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_evidence_routing import (
    build_analyst_evidence_routing_bundle,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_schemas import (
    build_analyst_adjudication_parse_report,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_faithfulness import (
    repair_adjudication_source_faithfulness,
)


FIXTURE = Path(__file__).parent / "fixtures" / "analyst_adjudication" / "v1_baseline.json"


def _fixture() -> tuple[dict, dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return payload["ledger"], payload["adjudication"]


def _compact_row(evidence_id: str) -> dict:
    if evidence_id == "warning:risk":
        return {
            "evidence_item_id": evidence_id,
            "memo_use": "load_bearing_counterweight",
            "answer_relation": "challenges_answer",
            "priority": "core",
            "reason": "Increased downstream risk materially weakens the provisional answer.",
            "target_answer_option": "neutral",
        }
    if evidence_id == "context:mechanism":
        return {
            "evidence_item_id": evidence_id,
            "memo_use": "mechanism_or_context",
            "answer_relation": "contextualizes_answer",
            "priority": "context",
            "reason": "Mechanism evidence explains but does not drive the answer.",
        }
    return {
        "evidence_item_id": evidence_id,
        "memo_use": "load_bearing_primary_support",
        "answer_relation": "supports_answer",
        "priority": "core",
        "reason": "Direct outcome evidence supports the provisional answer.",
    }


def _run_v2(monkeypatch, ledger: dict, *, chunk_size: int) -> dict:
    ids = [str(row["evidence_item_id"]) for row in ledger["rows"]]

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        returned = [evidence_id for evidence_id in ids if evidence_id in prompt]
        return ModelBackendResult(
            text=json.dumps({"rows": [_compact_row(evidence_id) for evidence_id in returned]}),
            backend="fake",
        )

    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v2")
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", str(chunk_size))
    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2.run_model_backend",
        fake_backend,
    )
    return run_analyst_adjudication(ledger, backend="fake", backend_timeout=30, backend_retries=0)


def test_v2_prompt_reduces_contract_size_by_at_least_forty_percent() -> None:
    ledger, _ = _fixture()
    legacy = build_analyst_adjudication_prompt(ledger)
    compact = build_analyst_adjudication_prompt_v2(ledger)

    assert len(compact) <= len(legacy) * 0.60


def test_v2_prompt_ignores_labels_excerpts_and_unowned_metadata() -> None:
    ledger, _ = _fixture()
    mutated = deepcopy(ledger)
    for row in mutated["rows"]:
        row["source_labels"] = ["Renamed display label"]
        row["source_excerpt"] = "Irrelevant raw excerpt."
        row["large_internal_notes"] = {"arbitrary": "metadata"}

    assert build_analyst_adjudication_prompt_v2(mutated) == build_analyst_adjudication_prompt_v2(ledger)


def test_v2_runtime_is_invariant_to_chunk_size(monkeypatch) -> None:
    ledger, _ = _fixture()

    one_at_a_time = _run_v2(monkeypatch, ledger, chunk_size=1)
    all_at_once = _run_v2(monkeypatch, ledger, chunk_size=3)

    assert one_at_a_time["analyst_adjudication"] == all_at_once["analyst_adjudication"]
    assert one_at_a_time["analyst_adjudication_parse_report"]["valid"] is True
    assert all_at_once["analyst_adjudication_parse_report"]["valid"] is True


def test_v2_adapter_is_semantically_invariant_to_input_order() -> None:
    ledger, _ = _fixture()
    rows = [_compact_row(str(row["evidence_item_id"])) for row in ledger["rows"]]
    reversed_ledger = {**ledger, "rows": list(reversed(ledger["rows"]))}

    original = adapt_analyst_adjudication_v2({"rows": rows}, ledger)
    reordered = adapt_analyst_adjudication_v2({"rows": list(reversed(rows))}, reversed_ledger)
    semantic_fields = ("memo_use", "answer_relation", "target_answer_option", "effect_on_final_answer")
    original_by_id = {row["evidence_item_id"]: row for row in original["rows"]}
    reordered_by_id = {row["evidence_item_id"]: row for row in reordered["rows"]}

    assert {
        evidence_id: tuple(row[field] for field in semantic_fields)
        for evidence_id, row in original_by_id.items()
    } == {
        evidence_id: tuple(row[field] for field in semantic_fields)
        for evidence_id, row in reordered_by_id.items()
    }


def test_v2_matches_repaired_v1_routing_for_baseline_fixture() -> None:
    ledger, baseline = _fixture()
    repaired_baseline, _ = repair_adjudication_source_faithfulness(ledger, baseline)
    compact = adapt_analyst_adjudication_v2(
        {"rows": [_compact_row(str(row["evidence_item_id"])) for row in ledger["rows"]]},
        ledger,
    )
    comparison = build_analyst_adjudication_schema_comparison(repaired_baseline, compact)

    baseline_parse = build_analyst_adjudication_parse_report(repaired_baseline, ledger)
    compact_parse = build_analyst_adjudication_parse_report(compact, ledger)
    baseline_routes = build_analyst_evidence_routing_bundle(
        ledger=ledger,
        adjudication=repaired_baseline,
        adjudication_parse_report=baseline_parse,
    )["analyst_evidence_routing"]
    compact_routes = build_analyst_evidence_routing_bundle(
        ledger=ledger,
        adjudication=compact,
        adjudication_parse_report=compact_parse,
    )["analyst_evidence_routing"]

    assert comparison["high_impact_difference_count"] == 0
    assert {
        row["evidence_item_id"]: row["route"] for row in baseline_routes["rows"]
    } == {
        row["evidence_item_id"]: row["route"] for row in compact_routes["rows"]
    }


def test_v2_canonical_output_retains_source_faithfulness_repair() -> None:
    ledger, _ = _fixture()
    rows = [_compact_row(str(row["evidence_item_id"])) for row in ledger["rows"]]
    risk = next(row for row in rows if row["evidence_item_id"] == "warning:risk")
    risk.update(
        {
            "memo_use": "load_bearing_primary_support",
            "answer_relation": "supports_answer",
            "reason": "Incorrectly supports neutrality.",
        }
    )
    canonical = adapt_analyst_adjudication_v2({"rows": rows}, ledger)
    repaired, report = repair_adjudication_source_faithfulness(ledger, canonical)
    repaired_risk = next(row for row in repaired["rows"] if row["evidence_item_id"] == "warning:risk")

    assert report["status"] == "repaired"
    assert repaired_risk["memo_use"] == "load_bearing_counterweight"
    assert repaired_risk["answer_relation"] == "challenges_answer"


def test_v2_runtime_rejects_target_option_not_in_answer_frame(monkeypatch) -> None:
    ledger, _ = _fixture()
    ledger["stable_final_answer_frame"]["live_answer_options"] = ["adopt", "reject"]

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        evidence_ids = [str(row["evidence_item_id"]) for row in ledger["rows"] if str(row["evidence_item_id"]) in prompt]
        rows = [{**_compact_row(evidence_id), "target_answer_option": "fabricated option"} for evidence_id in evidence_ids]
        return ModelBackendResult(text=json.dumps({"rows": rows}), backend="fake")

    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v2")
    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", "3")
    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "1")
    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2.run_model_backend",
        fake_backend,
    )

    result = run_analyst_adjudication(ledger, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "model_output_invalid"
    assert result["analyst_adjudication_parse_report"]["valid"] is False
    issues = result["analyst_adjudication_chunk_reports"]["chunks"][0]["issues"]
    assert "unsupported_target_answer_options" in issues[0]


def test_v2_runtime_accepts_canonical_candidate_answer_id(monkeypatch) -> None:
    ledger, _ = _fixture()
    ledger["rows"] = ledger["rows"][:1]
    ledger["stable_final_answer_frame"]["live_answer_options"] = [
        {
            "candidate_answer_id": "subgroup_or_scope_dependent",
            "answer": "depends on subgroup, dose, endpoint, or scope",
            "stance": "conditional",
        }
    ]

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        row = {
            **_compact_row("bundle:support"),
            "target_answer_option": "subgroup_or_scope_dependent",
        }
        return ModelBackendResult(text=json.dumps({"rows": [row]}), backend="fake")

    monkeypatch.setenv("ECM_ANALYST_ADJUDICATION_SCHEMA", "v2")
    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "1")
    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2.run_model_backend",
        fake_backend,
    )

    result = run_analyst_adjudication(ledger, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["analyst_adjudication_report"]["status"] == "accepted"
    assert result["analyst_adjudication"]["rows"][0]["target_answer_option"] == "subgroup_or_scope_dependent"
