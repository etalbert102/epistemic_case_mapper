from __future__ import annotations

from epistemic_case_mapper.map_briefing_global_decision_model import build_global_decision_model_bundle


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {"evidence_item_id": "item:support", "claim": "Option A improves the main outcome."},
            {"evidence_item_id": "item:limit", "claim": "The benefit may not hold in a narrower setting."},
            {"evidence_item_id": "item:extra", "claim": "A deferred item still needs review."},
        ],
    }


def _decision_model() -> dict:
    return {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only where the limiting condition is handled.",
        "confidence": "medium",
        "overall_rationale": "The support is meaningful but scope limits bound the answer.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Option A improves the main outcome.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["item:support"],
                "rationale": "This is the main support.",
            },
            {
                "group_id": "scope_group",
                "proposition": "The answer depends on whether the limiting condition applies.",
                "memo_role": "scope_or_applicability",
                "importance_rank": 2,
                "covered_evidence_item_ids": ["item:limit"],
                "rationale": "This bounds the answer.",
                "uncertainty_type": "scope",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "item:support", "disposition": "foreground", "group_id": "support_group"},
            {"evidence_item_id": "item:limit", "disposition": "foreground", "group_id": "scope_group"},
            {"evidence_item_id": "item:extra", "disposition": "background", "group_id": "", "rationale": "Deferred for review."},
        ],
        "quantitative_anchors": [],
        "what_would_change_the_answer": ["Better evidence on the limiting condition."],
        "decision_logic": {"bounded_bottom_line": "Adopt option A only where the limiting condition is handled."},
        "argument_plan": [{"step_id": "weigh_support_and_scope", "evidence_item_ids": ["item:support", "item:limit"]}],
    }


def test_global_decision_model_projects_analyst_model_side_by_side() -> None:
    bundle = build_global_decision_model_bundle(
        ledger=_ledger(),
        analyst_decision_model=_decision_model(),
        analyst_decision_model_report={"status": "accepted"},
        analyst_decision_model_parse_report={"status": "ready", "missing_accounting_ids": []},
    )

    model = bundle["global_decision_model"]
    report = bundle["global_decision_model_report"]

    assert model["schema_id"] == "global_decision_model_v1"
    assert model["bounded_answer"] == "Adopt option A only where the limiting condition is handled."
    assert model["strongest_support"][0]["covered_evidence_item_ids"] == ["item:support"]
    assert model["scope_boundaries"][0]["covered_evidence_item_ids"] == ["item:limit"]
    assert model["evidence_accounting"]["downgraded_or_background_evidence_item_ids"] == ["item:extra"]
    assert report["status"] == "ready"
    assert report["coverage_qualified"] is False


def test_global_decision_model_qualifies_coverage_when_parallel_tasks_fail() -> None:
    bundle = build_global_decision_model_bundle(
        ledger=_ledger(),
        analyst_decision_model=_decision_model(),
        analyst_decision_model_report={"status": "accepted_parallel_with_warnings"},
        analyst_decision_model_parse_report={"status": "ready", "missing_accounting_ids": []},
        parallel_report={
            "schema_id": "parallel_analyst_decision_model_report_v1",
            "task_count": 2,
            "parsed_count": 1,
            "failed_count": 1,
            "task_reports": [
                {"task_id": "task_001", "status": "backend_error", "issues": ["timeout"]},
                {"task_id": "task_002", "status": "parsed", "issues": []},
            ],
        },
    )

    report = bundle["global_decision_model_report"]
    failure = bundle["global_decision_model_failure_accounting"]
    reconciliation = bundle["global_decision_model_reconciliation_report"]

    assert report["status"] == "ready_with_warnings"
    assert report["coverage_qualified"] is True
    assert report["failure_count"] == 1
    assert failure["failed_task_ids"] == ["task_001"]
    assert "partial_semantic_owner_failure" in reconciliation["issues"]
    assert "coverage_qualified_by_model_failure_or_scaffold" in reconciliation["issues"]


def test_global_decision_model_accounts_for_deferred_and_missing_evidence() -> None:
    bundle = build_global_decision_model_bundle(
        ledger=_ledger(),
        analyst_decision_model=_decision_model(),
        analyst_decision_model_report={"status": "accepted"},
        analyst_decision_model_parse_report={
            "status": "warning",
            "missing_accounting_ids": ["item:extra"],
            "obligation_omissions": {"ungrouped_scope_boundary_ids": ["item:extra"]},
        },
        evidence_routing_report={"routing_counts": {"include": 2, "defer": 1, "exclude": 0}},
        deferred_evidence_audit={"deferred_evidence_unit_ids": ["unit:extra"], "deferred_reasons": [{"unit_id": "unit:extra"}]},
    )

    model = bundle["global_decision_model"]
    report = bundle["global_decision_model_report"]
    issues = bundle["global_decision_model_reconciliation_report"]["issues"]

    assert model["routing_accounting"]["deferred_count"] == 1
    assert model["evidence_accounting"]["missing_accounting_ids"] == []
    assert model["evidence_accounting"]["reported_missing_accounting_ids"] == ["item:extra"]
    assert report["status"] == "ready_with_warnings"
    assert "missing_evidence_accounting" not in issues
    assert "retention_obligations_not_fully_grouped" in issues
    assert "deferred_evidence_not_in_global_model" in issues


def test_global_decision_model_flags_only_actually_unaccounted_evidence() -> None:
    model = _decision_model()
    model["evidence_dispositions"] = [
        row for row in model["evidence_dispositions"] if row["evidence_item_id"] != "item:extra"
    ]

    bundle = build_global_decision_model_bundle(
        ledger=_ledger(),
        analyst_decision_model=model,
        analyst_decision_model_report={"status": "accepted"},
        analyst_decision_model_parse_report={"status": "warning", "missing_accounting_ids": ["item:extra"]},
    )

    assert bundle["global_decision_model"]["evidence_accounting"]["missing_accounting_ids"] == ["item:extra"]
    assert "missing_evidence_accounting" in bundle["global_decision_model_reconciliation_report"]["issues"]
