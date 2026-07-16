from __future__ import annotations

from typing import Any

from epistemic_case_mapper import map_briefing_analyst_decision_logic as decision_logic
from epistemic_case_mapper.map_briefing_analyst_decision_repair import (
    compact_decision_model_repair_report,
    run_analyst_decision_model_repair,
)
from epistemic_case_mapper.map_briefing_decision_diagnosticity import apply_decision_diagnostic_ranking
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import dict_value as _dict


def try_repair_invalid_parallel_decision_model(
    *,
    payload: dict[str, Any],
    parse_report: dict[str, Any],
    context: dict[str, Any],
    ledger: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
) -> dict[str, Any]:
    repair = run_analyst_decision_model_repair(
        initial_model=payload,
        initial_parse_report=parse_report,
        context=context,
        ledger=ledger,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        num_predict=num_predict,
    )
    bundle = {
        "accepted": bool(repair.get("accepted")),
        "analyst_decision_model_repair_prompt": repair.get("analyst_decision_model_repair_prompt", ""),
        "analyst_decision_model_repair_raw": repair.get("analyst_decision_model_repair_raw", ""),
        "analyst_decision_model_repair_parse_report": repair.get("analyst_decision_model_repair_parse_report", {}),
        "analyst_decision_model_repair_report": compact_decision_model_repair_report(repair),
    }
    if not repair.get("accepted"):
        return bundle
    final_model = repair.get("analyst_decision_model", payload)
    final_model, ranking_guard = _apply_ranking_guard(final_model, context)
    final_parse_report = repair.get("analyst_decision_model_parse_report", parse_report)
    status = "accepted_parallel_after_repair" if final_parse_report.get("status") == "ready" else "accepted_parallel_after_repair_with_warnings"
    bundle.update(
        {
            "analyst_decision_model": final_model,
            "analyst_decision_model_parse_report": final_parse_report,
            "analyst_decision_model_report_status": status,
            "analyst_decision_model_report_issues": list(repair.get("issues") or []),
            "analyst_decision_model_ranking_guard": ranking_guard,
        }
    )
    return bundle


def invalid_parallel_decision_model_result(
    *,
    context: dict[str, Any],
    parallel: dict[str, Any],
    payload: dict[str, Any],
    parse_report: dict[str, Any],
    ledger: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
) -> dict[str, Any]:
    repair = try_repair_invalid_parallel_decision_model(
        payload=payload,
        parse_report=parse_report,
        context=context,
        ledger=ledger,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        num_predict=num_predict,
    )
    if repair.get("accepted"):
        final_parse_report = dict(repair.get("analyst_decision_model_parse_report") or parse_report)
        return _base_result(
            context=context,
            parallel=parallel,
            model=dict(repair.get("analyst_decision_model") or payload),
            parse_report=final_parse_report,
            report=_report(
                str(repair.get("analyst_decision_model_report_status") or "accepted_parallel_after_repair_with_warnings"),
                final_parse_report,
                issues=list(repair.get("analyst_decision_model_report_issues") or []),
            ),
            initial_model=payload,
            initial_parse_report=parse_report,
            repair=repair,
            ranking_guard=dict(repair.get("analyst_decision_model_ranking_guard") or {}),
        )
    result = _base_result(
        context=context,
        parallel=parallel,
        model=payload,
        parse_report=parse_report,
        report=_report(
            "parallel_model_output_invalid",
            parse_report,
            issues=["parallel analyst decision model failed schema or evidence ID checks"],
        ),
        initial_model=None,
        initial_parse_report=None,
        repair=repair,
        ranking_guard=None,
    )
    return result


def _apply_ranking_guard(model: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    groups, report = apply_decision_diagnostic_ranking(list(model.get("evidence_groups") or []), list(context.get("evidence_rows") or []))
    updated = dict(model)
    updated["evidence_groups"] = groups
    updated["decision_logic"] = decision_logic.naturalize_decision_logic_payload(_dict(updated.get("decision_logic")))
    return updated, report


def _base_result(
    *,
    context: dict[str, Any],
    parallel: dict[str, Any],
    model: dict[str, Any],
    parse_report: dict[str, Any],
    report: dict[str, Any],
    initial_model: dict[str, Any] | None,
    initial_parse_report: dict[str, Any] | None,
    repair: dict[str, Any],
    ranking_guard: dict[str, Any] | None,
) -> dict[str, Any]:
    result = {
        "analyst_decision_context": context,
        "analyst_decision_model": model,
        "analyst_decision_model_prompt": parallel["prompt"],
        "analyst_decision_model_raw": parallel["raw"],
        "analyst_decision_model_parse_report": parse_report,
        "analyst_decision_model_parallel_report": parallel["report"],
        "analyst_decision_model_report": report,
        "analyst_decision_model_repair_prompt": repair.get("analyst_decision_model_repair_prompt", ""),
        "analyst_decision_model_repair_raw": repair.get("analyst_decision_model_repair_raw", ""),
        "analyst_decision_model_repair_parse_report": repair.get("analyst_decision_model_repair_parse_report", {}),
        "analyst_decision_model_repair_report": repair.get("analyst_decision_model_repair_report", {}),
    }
    if initial_model is not None:
        result["analyst_decision_model_initial"] = initial_model
        result["analyst_decision_model_initial_parse_report"] = initial_parse_report or {}
    if ranking_guard is not None:
        result["analyst_decision_model_ranking_guard"] = ranking_guard
    return result


def _report(status: str, parse_report: dict[str, Any], *, issues: list[str] | None = None) -> dict[str, Any]:
    merged_issues = [*(issues or []), *list(parse_report.get("issues") or [])]
    return {
        "schema_id": "analyst_decision_model_report_v1",
        "status": status,
        "accepted": status.startswith("accepted"),
        "valid": bool(parse_report.get("valid")),
        "parse_status": parse_report.get("status"),
        "covered_evidence_item_count": parse_report.get("covered_evidence_item_count", 0),
        "group_count": parse_report.get("group_count", 0),
        "ledger_row_count": parse_report.get("ledger_row_count", 0),
        "attempt_count": 1,
        "retry_reports": [],
        "issues": list(dict.fromkeys(str(issue) for issue in merged_issues if str(issue).strip())),
    }
