from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_repair_prompt,
    build_memo_ready_packet_retention_report,
    run_memo_ready_packet_repair,
    run_memo_ready_packet_synthesis,
)
from epistemic_case_mapper.map_briefing_memo_obligations import build_memo_obligation_packet
from epistemic_case_mapper.map_briefing_memo_ready_prompt import build_memo_ready_packet_synthesis_prompt
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
    assert support_item["excluded_quantity_values"] == ["p = 0.04"]
    assert packet["quantity_obligation_plan"]["must_retain_count"] == 1
    assert packet["writer_packet_writeability_report"]["model_call_accounting"]["new_default_model_call_added"] is False
    assert "analyst_quantity_binding_report" in packet["writer_packet_writeability_report"]["model_call_accounting"]["existing_judgment_artifacts_reused"]


def test_decision_writer_packet_prompt_exposes_required_obligation_ledger() -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "Narrative blueprint" in prompt
    assert "Required obligation ledger" in prompt
    assert "retention checklist, not an outline" in prompt
    assert "Use this as load-bearing support for the default answer" in prompt
    assert "Bound the answer's applicability" in prompt
    assert "analyst_synthesis_packet" not in prompt


def test_decision_writer_packet_synthesis_warnings_are_not_marked_accepted(monkeypatch) -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(
            text=(
                "## Decision Brief\n\n"
                "Outcome Review reports that Option A improves the main outcome by 20% improvement."
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["contract_mode"] == "strict_writer_packet"
    assert result["report"]["status"] == "accepted_with_retention_warnings"
    assert result["report"]["accepted"] is False
    assert result["report"]["missing_mandatory_count"] == 1


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

    assert before["missing_mandatory_count"] == 2
    assert result["report"]["contract_mode"] == "strict_writer_packet"
    assert result["report"]["status"] == "partial_retention_improvement_applied_with_warnings"
    assert result["report"]["accepted"] is False
    assert result["report"]["applied"] is True
    assert result["report"]["final_missing_mandatory_count"] == 1
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
