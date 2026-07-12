from __future__ import annotations

import json
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import model_parallelism, run_parallel
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.model_schemas import parse_model_output_report


def run_targeted_packet_refinement(
    *,
    packet: dict[str, Any],
    sufficiency_report: dict[str, Any],
    critique_adjudication: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
    refinement_schema: type[Any],
    apply_refinement: Callable[[dict[str, Any], dict[str, Any]], tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]],
    apply_cleanup: Callable[[dict[str, Any], dict[str, Any]], tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    repair_packet: Callable[[dict[str, Any], dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    tasks = build_targeted_refinement_tasks(packet, sufficiency_report, critique_adjudication)
    if not tasks:
        repaired, repair_report = repair_packet(packet, critique_adjudication)
        return _result(
            packet=repaired,
            prompts=[],
            raws=[],
            status="no_targeted_refinement_tasks",
            applied=[],
            rejected=[],
            repair_report=repair_report,
            task_reports=[],
        )
    task_results = run_parallel(
        tasks,
        lambda task: _run_task(
            task,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            run_backend=run_backend,
            refinement_schema=refinement_schema,
        ),
        max_workers=model_parallelism(backend),
    )
    payload = _merge_task_payloads(task_results)
    refined, applied, rejected = apply_refinement(packet, payload)
    cleanup_applied, cleanup_rejected = apply_cleanup(refined, critique_adjudication)
    applied.extend(cleanup_applied)
    rejected.extend(cleanup_rejected)
    repaired, repair_report = repair_packet(refined, critique_adjudication)
    status = _status(task_results, applied)
    return _result(
        packet=repaired,
        prompts=[str(row.get("prompt") or "") for row in task_results],
        raws=[str(row.get("raw") or "") for row in task_results],
        status=status,
        applied=applied,
        rejected=rejected,
        repair_report=repair_report,
        task_reports=[row.get("report", {}) for row in task_results if isinstance(row.get("report"), dict)],
        payload=payload,
    )


def build_targeted_refinement_tasks(
    packet: dict[str, Any],
    sufficiency_report: dict[str, Any],
    critique_adjudication: dict[str, Any],
) -> list[dict[str, Any]]:
    bundles = {str(row.get("bundle_id") or ""): row for row in _list(packet.get("evidence_bundles")) if isinstance(row, dict)}
    retain = {str(row.get("item_id") or ""): row for row in _list(packet.get("must_retain_ledger")) if isinstance(row, dict)}
    tasks = []
    for index, rec in enumerate(_list(critique_adjudication.get("accepted_recommendations")), start=1):
        if not isinstance(rec, dict):
            continue
        target_ids = [target for target in _string_list(rec.get("target_ids")) if target in bundles or target in retain]
        if not target_ids:
            continue
        tasks.append(
            {
                "task_id": f"packet_refinement_task_{index:03d}",
                "decision_question": packet.get("decision_question"),
                "recommendation": rec,
                "target_ids": target_ids,
                "bundles": [bundles[target] for target in target_ids if target in bundles],
                "retain_items": [retain[target] for target in target_ids if target in retain],
                "sufficiency_context": _sufficiency_context(sufficiency_report, target_ids),
            }
        )
    return tasks


def build_targeted_refinement_prompt(task: dict[str, Any]) -> str:
    contract = {
        "schema_id": "decision_briefing_packet_refinement_v1",
        "packet_ready_for_synthesis": True,
        "bundle_updates": [
            {
                "bundle_id": "copy affected bundle_id",
                "decision_role": "optional refined role",
                "weight": "optional refined weight",
                "why_it_matters": "optional role-consistent decision relevance",
                "limits": ["optional scope/caveat limits"],
                "section_use": "optional role-consistent memo use",
                "section_targets": ["optional section names"],
                "rationale": "why this edit follows from supplied context",
            }
        ],
        "retain_item_updates": [],
        "warnings": [],
        "rationale": "short task-level rationale",
    }
    packet = {
        "task": "Repair only the supplied packet targets. Do not edit unrelated bundle or retain IDs.",
        "decision_question": task.get("decision_question"),
        "accepted_recommendation": task.get("recommendation"),
        "affected_bundles": [_compact_bundle(row) for row in _list(task.get("bundles")) if isinstance(row, dict)],
        "affected_retain_items": [_compact_retain(row) for row in _list(task.get("retain_items")) if isinstance(row, dict)],
        "sufficiency_context": task.get("sufficiency_context", {}),
        "rules": [
            "Return strict JSON only.",
            "Reference only affected IDs.",
            "Do not add new sources, claims, quantities, or IDs.",
            "Use empty arrays for update lists you do not need.",
        ],
        "required_output_schema": contract,
    }
    return json.dumps(packet, indent=2, ensure_ascii=False)


def _run_task(
    task: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
    refinement_schema: type[Any],
) -> dict[str, Any]:
    prompt = build_targeted_refinement_prompt(task)
    try:
        result = run_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            response_schema=refinement_schema.model_json_schema(),
        )
    except RuntimeError as exc:
        return {"task_id": task.get("task_id"), "prompt": prompt, "raw": "", "payload": {}, "report": _task_report("backend_error", issues=[str(exc)])}
    raw = str(getattr(result, "text", result))
    parse_report = parse_model_output_report(raw, refinement_schema)
    payload = parse_report.get("data") if parse_report.get("ok") else {}
    return {
        "task_id": task.get("task_id"),
        "prompt": prompt,
        "raw": canonical_json_output(raw),
        "payload": payload if isinstance(payload, dict) else {},
        "report": _task_report("accepted" if parse_report.get("ok") else "parse_failed", parse_report=parse_report),
    }


def _merge_task_payloads(task_results: list[dict[str, Any]]) -> dict[str, Any]:
    bundle_updates = []
    retain_updates = []
    warnings = []
    for result in task_results:
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        bundle_updates.extend(row for row in _list(payload.get("bundle_updates")) if isinstance(row, dict))
        retain_updates.extend(row for row in _list(payload.get("retain_item_updates")) if isinstance(row, dict))
        warnings.extend(_string_list(payload.get("warnings")))
    return {
        "schema_id": "decision_briefing_packet_refinement_v1",
        "packet_ready_for_synthesis": True,
        "bundle_updates": bundle_updates,
        "retain_item_updates": retain_updates,
        "warnings": _dedupe(warnings)[:24],
        "rationale": "Merged from targeted packet refinement tasks.",
    }


def _result(
    *,
    packet: dict[str, Any],
    prompts: list[str],
    raws: list[str],
    status: str,
    applied: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    repair_report: dict[str, Any],
    task_reports: list[dict[str, Any]],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "packet": packet,
        "prompt": "\n\n--- targeted packet refinement task ---\n\n".join(prompt for prompt in prompts if prompt),
        "raw": "\n\n--- targeted packet refinement raw ---\n\n".join(raw for raw in raws if raw),
        "report": {
            "schema_id": "decision_briefing_packet_refinement_report_v1",
            "status": status,
            "method": "parallel_targeted_packet_refinement",
            "task_count": len(task_reports),
            "task_reports": task_reports,
            "parse_report": {"ok": all(row.get("status") == "accepted" for row in task_reports), "targeted_task_count": len(task_reports)},
            "packet_ready_for_synthesis": (payload or {}).get("packet_ready_for_synthesis", True),
            "applied_update_count": len(applied),
            "rejected_update_count": len(rejected),
            "applied_updates": applied[:30],
            "rejected_updates": rejected[:30],
            "warnings": _string_list((payload or {}).get("warnings"))[:24],
            "packet_quality_repair_report": repair_report,
        },
    }


def _status(task_results: list[dict[str, Any]], applied: list[dict[str, Any]]) -> str:
    if any(_report_status(row) == "backend_error" for row in task_results):
        return "targeted_partial_backend_error"
    if any(_report_status(row) == "parse_failed" for row in task_results):
        return "targeted_partial_parse_failed"
    return "targeted_applied" if applied else "targeted_no_model_updates"


def _report_status(row: dict[str, Any]) -> str:
    report = row.get("report") if isinstance(row.get("report"), dict) else {}
    return str(report.get("status") or "")


def _task_report(status: str, *, parse_report: dict[str, Any] | None = None, issues: list[str] | None = None) -> dict[str, Any]:
    return {"schema_id": "targeted_packet_refinement_task_report_v1", "status": status, "parse_report": parse_report or {}, "issues": issues or []}


def _compact_bundle(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("bundle_id", "decision_role", "weight", "directionality", "section_use", "section_targets", "source_ids", "source_labels", "quantity_values")
    compact = {key: row.get(key) for key in keys if row.get(key) not in (None, "", [])}
    compact["claim"] = _short_text(str(row.get("claim") or ""), 520)
    compact["why_it_matters"] = _short_text(str(row.get("why_it_matters") or ""), 360)
    compact["limits"] = _string_list(row.get("limits"))[:6]
    compact["source_quality"] = _source_quality_summary(row)
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _source_quality_summary(row: dict[str, Any]) -> dict[str, Any]:
    appraisal = row.get("source_appraisal") if isinstance(row.get("source_appraisal"), dict) else {}
    return {
        key: value
        for key, value in {
            "quality": row.get("quality"),
            "warnings": _string_list(row.get("source_use_warnings"))[:4],
            "decision_directness": appraisal.get("decision_directness"),
            "document_types": _string_list(appraisal.get("document_types"))[:4],
            "evidence_proximity": _string_list(appraisal.get("evidence_proximity"))[:4],
            "recommended_uses": _string_list(appraisal.get("recommended_uses"))[:4],
            "interpretation_caveats": [_short_text(str(item), 180) for item in _string_list(appraisal.get("interpretation_caveats"))[:3]],
        }.items()
        if value not in (None, "", [], {})
    }


def _compact_retain(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": row.get("item_id"),
        "decision_role": row.get("decision_role"),
        "statement": _short_text(str(row.get("statement") or ""), 420),
        "importance": row.get("importance"),
        "bundle_ids": _string_list(row.get("bundle_ids")),
        "required_terms": _string_list(row.get("required_terms"))[:8],
    }


def _sufficiency_context(report: dict[str, Any], target_ids: list[str]) -> dict[str, Any]:
    del target_ids
    return {
        "status": report.get("status"),
        "warnings": _list(report.get("warnings"))[:8],
        "truly_lost_decision_critical_count": report.get("truly_lost_decision_critical_count", 0),
        "quantity_missing_count": report.get("quantity_missing_count", 0),
    }
