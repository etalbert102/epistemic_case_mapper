from __future__ import annotations

import json
import time
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_packet_critique_index import (
    build_packet_critique_index,
    build_packet_critique_shards,
    compact_global_critique_view,
    targets_from_packet,
)
from epistemic_case_mapper.model_backends import model_parallelism, run_parallel
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.model_schemas import parse_model_output_report


class PacketCritiqueVerificationOutput(BaseModel):
    schema_id: Literal["packet_critique_verification_v1"] = "packet_critique_verification_v1"
    verification_decision: Literal["accept", "warning_only", "reject"] = "warning_only"
    rationale: str = ""
    recommended_role: str = ""
    warnings: list[str] = Field(default_factory=list, max_length=8)


def should_use_parallel_packet_critique(packet: dict[str, Any], *, threshold: int = 8) -> bool:
    bundles = _list(packet.get("evidence_bundles"))
    return len([row for row in bundles if isinstance(row, dict)]) > max(1, threshold)


def run_parallel_packet_critique(
    packet: dict[str, Any],
    sufficiency_report: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
    critique_schema: type[Any],
    adjudicate: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    index = build_packet_critique_index(packet, sufficiency_report)
    shards = build_packet_critique_shards(index)
    _packet_progress(
        progress,
        "packet_critique_index",
        "completed",
        {"bundle_count": index.get("bundle_count", 0), "retain_item_count": index.get("retain_item_count", 0), "local_shard_count": len(shards)},
    )
    _packet_progress(progress, "packet_critique_local_shards", "started", {"local_shard_count": len(shards), "parallelism": model_parallelism(backend)})
    local_results = run_parallel(
        shards,
        lambda shard: _run_local_shard(
            shard,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            run_backend=run_backend,
            critique_schema=critique_schema,
        ),
        max_workers=model_parallelism(backend),
    )
    _packet_progress(
        progress,
        "packet_critique_local_shards",
        "completed",
        {
            "local_shard_count": len(shards),
            "local_shards_completed": sum(1 for row in local_results if row.get("status") == "parsed"),
            "failed_count": sum(1 for row in local_results if row.get("status") != "parsed"),
        },
    )
    local_payloads = [row.get("payload") for row in local_results if isinstance(row.get("payload"), dict)]
    local_reports = [row.get("summary", {}) for row in local_results if isinstance(row.get("summary"), dict)]
    _packet_progress(progress, "packet_critique_global", "started", {"local_shard_count": len(shards), "local_shards_completed": sum(1 for row in local_results if row.get("status") == "parsed")})
    global_result = _run_global_critique(
        index,
        local_reports,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        run_backend=run_backend,
        critique_schema=critique_schema,
    )
    _packet_progress(progress, "packet_critique_global", "completed", {"status": global_result.get("status"), "prompt_chars": global_result.get("prompt_chars", 0), "raw_chars": global_result.get("raw_chars", 0)})
    global_payload = global_result.get("payload") if isinstance(global_result.get("payload"), dict) else {}
    merged = _merge_critique_payloads(local_payloads, global_payload=global_payload)
    adjudication = adjudicate(merged, packet)
    _packet_progress(progress, "packet_critique_adjudication", "completed", {"accepted_count": adjudication.get("accepted_count", 0), "warning_only_count": adjudication.get("warning_only_count", 0)})
    _packet_progress(progress, "packet_critique_verification", "started", {"verification_task_count": len(_list(adjudication.get("accepted_recommendations")))})
    verification_results = _run_verification_tasks(
        packet,
        adjudication.get("accepted_recommendations", []),
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        run_backend=run_backend,
    )
    _packet_progress(
        progress,
        "packet_critique_verification",
        "completed",
        {
            "verification_task_count": len(verification_results),
            "verification_tasks_completed": sum(1 for row in verification_results if row.get("status") == "parsed"),
        },
    )
    final_adjudication = _apply_verification(adjudication, verification_results)
    report = _report(
        local_results=local_results,
        global_result=global_result,
        verification_results=verification_results,
        merged=merged,
        index=index,
        shards=shards,
        started=started,
        backend=backend,
    )
    return {
        "prompt": _join_texts([*[str(row.get("prompt") or "") for row in local_results], str(global_result.get("prompt") or ""), *[str(row.get("prompt") or "") for row in verification_results]], "packet critique prompt"),
        "raw": _join_texts([*[str(row.get("raw") or "") for row in local_results], str(global_result.get("raw") or ""), *[str(row.get("raw") or "") for row in verification_results]], "packet critique raw"),
        "report": report,
        "adjudication_report": final_adjudication,
    }


def _packet_progress(
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    substage: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    if progress is None:
        return
    progress("decision_packet_substage", status, {"substage": substage, **(details or {})})


def _run_local_shard(
    shard: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
    critique_schema: type[Any],
) -> dict[str, Any]:
    prompt = build_local_critique_prompt(shard)
    started = time.monotonic()
    try:
        raw = run_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries, response_schema=critique_schema.model_json_schema()).text
    except RuntimeError as exc:
        return _task_result(shard.get("shard_id"), "backend_error", prompt, "", started, issues=[str(exc)])
    parse_report = parse_model_output_report(raw, critique_schema)
    payload = parse_report.get("data") if parse_report.get("ok") else {}
    return _task_result(shard.get("shard_id"), "parsed" if parse_report.get("ok") else "parse_failed", prompt, canonical_json_output(raw), started, parse_report=parse_report, payload=payload)


def _run_global_critique(
    index: dict[str, Any],
    local_reports: list[dict[str, Any]],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
    critique_schema: type[Any],
) -> dict[str, Any]:
    prompt = build_global_critique_prompt(compact_global_critique_view(index, local_reports))
    started = time.monotonic()
    try:
        raw = run_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries, response_schema=critique_schema.model_json_schema()).text
    except RuntimeError as exc:
        return _task_result("packet_global_critique", "backend_error", prompt, "", started, issues=[str(exc)])
    parse_report = parse_model_output_report(raw, critique_schema)
    payload = parse_report.get("data") if parse_report.get("ok") else {}
    return _task_result("packet_global_critique", "parsed" if parse_report.get("ok") else "parse_failed", prompt, canonical_json_output(raw), started, parse_report=parse_report, payload=payload)


def _run_verification_tasks(
    packet: dict[str, Any],
    recommendations: Any,
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
) -> list[dict[str, Any]]:
    tasks = [
        {"verification_id": f"packet_critique_verification_{index:03d}", "recommendation": rec}
        for index, rec in enumerate(_list(recommendations), start=1)
        if isinstance(rec, dict)
    ][:16]
    return run_parallel(
        tasks,
        lambda task: _run_verification_task(packet, task, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries, run_backend=run_backend),
        max_workers=model_parallelism(backend),
    )


def _run_verification_task(
    packet: dict[str, Any],
    task: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
) -> dict[str, Any]:
    recommendation = task.get("recommendation") if isinstance(task.get("recommendation"), dict) else {}
    target_ids = _string_list(recommendation.get("target_ids"))
    prompt = build_verification_prompt(packet, recommendation, target_ids)
    started = time.monotonic()
    try:
        raw = run_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries, response_schema=PacketCritiqueVerificationOutput.model_json_schema()).text
    except RuntimeError as exc:
        return _task_result(task.get("verification_id"), "backend_error", prompt, "", started, issues=[str(exc)], recommendation=recommendation)
    parse_report = parse_model_output_report(raw, PacketCritiqueVerificationOutput)
    payload = parse_report.get("data") if parse_report.get("ok") else {}
    return _task_result(task.get("verification_id"), "parsed" if parse_report.get("ok") else "parse_failed", prompt, canonical_json_output(raw), started, parse_report=parse_report, payload=payload, recommendation=recommendation)


def build_local_critique_prompt(shard: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Critique this shard of a source-grounded decision briefing packet. Return strict JSON only.",
            "decision_question": shard.get("decision_question"),
            "answer_frame": shard.get("answer_frame", {}),
            "bundles_to_check": shard.get("bundles", []),
            "retain_items_to_check": shard.get("retain_items", []),
            "sufficiency_summary": shard.get("sufficiency_summary", {}),
            "instructions": [
                "Perform local QA only for the supplied bundles and retain items.",
                "Check role, directionality, claim quality, source quality, quantity interpretation, and section-use problems tied to existing IDs.",
                "Use target_ids for existing bundle IDs when recommending edits.",
                "Use warning-only insufficiency fields for source-level or packet-level problems without a concrete target.",
                "Leave reader_facing_guidance empty; global reader-facing guidance will be consolidated in a separate pass.",
                "Do not invent sources, quantities, claims, or IDs.",
                "Return JSON matching packet_critique_v1.",
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def build_global_critique_prompt(view: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Perform global packet critique and consolidate reader-facing memo guidance. Return strict JSON only.",
            "view": view,
            "instructions": [
                "Use the local critique summaries as telemetry, not as final memo instructions.",
                "Look across all shards for recurring evidence-type distinctions, confidence limits, subgroup boundaries, source-type caveats, and synthesis traps.",
                "Return 4 to 6 reader_facing_guidance items total. Each item should be a consolidated theme, not a duplicate local issue.",
                "Merge overlapping themes such as association-vs-causation, observational-vs-outcome limits, moderate-vs-high intake, subgroup boundaries, and biomarker-vs-clinical-outcome distinctions.",
                "Each reader_facing_guidance item must include instruction, why_it_matters, source_ids, target_ids when available, and validation_terms.",
                "Recommend edits only for existing IDs visible in the inventory.",
                "Use warning-only fields when the problem is global but not target-local.",
                "Return JSON matching packet_critique_v1.",
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def build_verification_prompt(packet: dict[str, Any], recommendation: dict[str, Any], target_ids: list[str]) -> str:
    return json.dumps(
        {
            "task": "Verify whether this critique recommendation is supported by the affected packet targets. Return strict JSON only.",
            "decision_question": packet.get("decision_question", ""),
            "recommendation": recommendation,
            "affected_targets": targets_from_packet(packet, target_ids),
            "allowed_decisions": ["accept", "warning_only", "reject"],
            "instructions": [
                "Accept only if the recommendation is supported by the supplied targets.",
                "Use warning_only when the concern is plausible but not strong enough for automatic packet changes.",
                "Reject when the target context does not support the recommendation.",
                "Return JSON matching packet_critique_verification_v1.",
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def _merge_critique_payloads(payloads: list[dict[str, Any]], *, global_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global_payload = global_payload if isinstance(global_payload, dict) else {}
    all_payloads = [*payloads, global_payload]
    merged: dict[str, Any] = {"schema_id": "packet_critique_v1", "packet_sufficiency_judgment": _merged_judgment(all_payloads)}
    list_fields = (
        "bundle_role_checks",
        "bad_answer_frame_risks",
        "answer_frame_issues",
        "answer_frame_challenges",
        "misleading_synthesis_risks",
        "misleading_risks",
        "insufficiency_warnings",
        "claim_quality_issues",
        "section_routing_issues",
        "missing_decision_functions",
        "misassigned_roles",
        "overweighted_bundles",
        "underweighted_bundles",
        "missing_or_weak_cruxes",
        "section_plan_risks",
        "recommended_packet_edits",
    )
    for field in list_fields:
        rows = []
        for payload in all_payloads:
            rows.extend(_list(payload.get(field)))
        merged[field] = _dedupe_jsonish(rows)[:32]
    merged["reader_facing_guidance"] = _dedupe_jsonish(_list(global_payload.get("reader_facing_guidance")))[:8]
    return merged


def _apply_verification(adjudication: dict[str, Any], verification_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not verification_results:
        return adjudication
    final = dict(adjudication)
    decisions = {
        _recommendation_key(row.get("recommendation")): row
        for row in verification_results
        if isinstance(row.get("recommendation"), dict)
    }
    accepted = []
    rejected = list(_list(final.get("rejected_recommendations")))
    warning = list(_list(final.get("warning_only_recommendations")))
    for rec in _list(final.get("accepted_recommendations")):
        if not isinstance(rec, dict):
            continue
        result = decisions.get(_recommendation_key(rec), {})
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        decision = str(payload.get("verification_decision") or "").strip()
        if result.get("status") != "parsed" or decision == "warning_only":
            warning.append({**rec, "reason": "verification_warning_or_unparsed", "verification": _verification_note(result)})
        elif decision == "reject":
            rejected.append({**rec, "reason": "verification_rejected", "verification": _verification_note(result)})
        else:
            accepted.append(_verified_recommendation(rec, payload))
    final["accepted_recommendations"] = accepted[:24]
    final["rejected_recommendations"] = rejected[:24]
    final["warning_only_recommendations"] = warning[:24]
    final["accepted_count"] = len(accepted)
    final["rejected_count"] = len(rejected)
    final["warning_only_count"] = len(warning)
    final["verification_report"] = {
        "schema_id": "packet_critique_verification_report_v1",
        "task_count": len(verification_results),
        "parsed_count": sum(1 for row in verification_results if row.get("status") == "parsed"),
        "accepted_count": len(accepted),
        "warning_or_rejected_count": len(rejected) + len(warning),
        "task_reports": [_task_public_report(row) for row in verification_results],
    }
    return final


def _report(
    *,
    local_results: list[dict[str, Any]],
    global_result: dict[str, Any],
    verification_results: list[dict[str, Any]],
    merged: dict[str, Any],
    index: dict[str, Any],
    shards: list[dict[str, Any]],
    started: float,
    backend: str,
) -> dict[str, Any]:
    parsed_count = sum(1 for row in local_results if row.get("status") == "parsed")
    global_ok = global_result.get("status") == "parsed"
    return {
        "schema_id": "packet_critique_report_v1",
        "status": "parsed" if parsed_count or global_ok else "parse_failed",
        "method": "parallel_hierarchical_packet_critique",
        "parse_report": {"ok": bool(parsed_count or global_ok), "local_parsed_count": parsed_count, "global_ok": global_ok},
        "judgment": merged.get("packet_sufficiency_judgment", "unknown"),
        "parallelism": {
            "backend": backend,
            "configured_max_workers": model_parallelism(backend),
            "local_shard_count": len(shards),
            "local_shards_completed": parsed_count,
            "local_shards_failed": sum(1 for row in local_results if row.get("status") != "parsed"),
            "verification_task_count": len(verification_results),
            "verification_tasks_completed": sum(1 for row in verification_results if row.get("status") == "parsed"),
            "wall_seconds": round(time.monotonic() - started, 3),
        },
        "index_summary": {"bundle_count": index.get("bundle_count", 0), "retain_item_count": index.get("retain_item_count", 0)},
        "local_task_reports": [_task_public_report(row) for row in local_results],
        "global_task_report": _task_public_report(global_result),
        "verification_task_reports": [_task_public_report(row) for row in verification_results],
    }


def _task_result(
    task_id: Any,
    status: str,
    prompt: str,
    raw: str,
    started: float,
    *,
    parse_report: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    issues: list[str] | None = None,
    recommendation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "task_id": str(task_id or ""),
        "status": status,
        "prompt": prompt,
        "raw": raw,
        "duration_seconds": round(time.monotonic() - started, 3),
        "prompt_chars": len(prompt),
        "raw_chars": len(raw),
        "parse_report": parse_report or {},
        "payload": payload if isinstance(payload, dict) else {},
        "issues": issues or [],
    }
    if recommendation is not None:
        result["recommendation"] = recommendation
    result["summary"] = _payload_summary(result)
    return result


def _payload_summary(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    return {
        "task_id": result.get("task_id"),
        "status": result.get("status"),
        "judgment": payload.get("packet_sufficiency_judgment", ""),
        "recommended_packet_edits": _list(payload.get("recommended_packet_edits"))[:8],
        "bundle_role_checks": _list(payload.get("bundle_role_checks"))[:8],
        "misleading_synthesis_risks": _list(payload.get("misleading_synthesis_risks"))[:5],
        "reader_facing_guidance": _list(payload.get("reader_facing_guidance"))[:5],
        "insufficiency_warnings": _list(payload.get("insufficiency_warnings"))[:5],
        "claim_quality_issues": _list(payload.get("claim_quality_issues"))[:5],
        "section_routing_issues": _list(payload.get("section_routing_issues"))[:5],
    }


def _task_public_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": row.get("task_id"),
        "status": row.get("status"),
        "duration_seconds": row.get("duration_seconds"),
        "prompt_chars": row.get("prompt_chars"),
        "raw_chars": row.get("raw_chars"),
        "issues": row.get("issues", []),
    }


def _merged_judgment(payloads: list[dict[str, Any]]) -> str:
    rank = {"not_sufficient": 3, "needs_repair": 2, "ready": 1}
    best = "ready"
    for payload in payloads:
        judgment = str(payload.get("packet_sufficiency_judgment") or "ready")
        if rank.get(judgment, 0) > rank.get(best, 0):
            best = judgment
    return best


def _dedupe_jsonish(rows: list[Any]) -> list[Any]:
    seen = set()
    output = []
    for row in rows:
        key = json.dumps(row, sort_keys=True, ensure_ascii=False) if isinstance(row, (dict, list)) else str(row)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _join_texts(texts: list[str], label: str) -> str:
    return f"\n\n--- {label} ---\n\n".join(text for text in texts if text)


def _recommendation_key(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return json.dumps(
        {
            "edit_type": value.get("edit_type"),
            "target_ids": _string_list(value.get("target_ids")),
            "recommended_role": value.get("recommended_role", ""),
            "recommended_weight": value.get("recommended_weight", ""),
        },
        sort_keys=True,
    )


def _verified_recommendation(rec: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    updated = dict(rec)
    if str(payload.get("recommended_role") or "").strip():
        updated["recommended_role"] = str(payload.get("recommended_role")).strip()
    updated["verification"] = _verification_note({"payload": payload, "status": "parsed"})
    return updated


def _verification_note(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    return {
        "status": result.get("status"),
        "decision": payload.get("verification_decision", ""),
        "rationale": payload.get("rationale", ""),
        "warnings": _dedupe(_string_list(payload.get("warnings")))[:6],
    }
