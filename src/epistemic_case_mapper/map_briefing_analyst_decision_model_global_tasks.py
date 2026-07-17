from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_analyst_decision_group_schema import schema_safe_decision_group
from epistemic_case_mapper.map_briefing_analyst_decision_model_global_task_prompts import (
    build_global_analyst_task_prompt,
    build_global_analyst_tasks,
)
from epistemic_case_mapper.map_briefing_analyst_decision_logic import (
    argument_plan_transition,
    naturalize_decision_logic_payload,
)
from epistemic_case_mapper.map_briefing_decision_diagnosticity import apply_decision_diagnostic_ranking
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_source_hierarchy import normalize_source_hierarchy
from epistemic_case_mapper.model_backends import model_parallelism, run_parallel
from epistemic_case_mapper.model_stage_retry import model_stage_attempts


def should_use_global_task_analyst_decision_model(context: dict[str, Any]) -> bool:
    mode = str(os.environ.get("ECM_ANALYST_DECISION_MODEL_MODE", "global_tasks")).strip().lower()
    if mode in {"row_sharded", "parallel_rows", "legacy_parallel"}:
        return False
    if mode in {"global_tasks", "global", "task_specific"}:
        return len(_rows(context)) > _threshold()
    return len(_rows(context)) > _threshold()


def run_global_task_analyst_decision_model(
    *,
    context: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
    run_backend: Callable[..., Any],
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    tasks = build_global_analyst_tasks(context)
    _emit_progress(
        progress,
        "analyst_decision_model_global_tasks",
        "started",
        {
            "task_count": len(tasks),
            "row_count": len(_rows(context)),
            "parallelism": model_parallelism(backend),
        },
    )
    task_results = run_parallel(
        tasks,
        lambda task: _run_task(
            task,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            num_predict=num_predict,
            run_backend=run_backend,
            progress=progress,
        ),
        max_workers=model_parallelism(backend),
    )
    payload = build_analyst_decision_model_from_global_tasks(context, task_results)
    _emit_progress(
        progress,
        "analyst_decision_model_global_tasks",
        "completed",
        {
            "task_count": len(tasks),
            "parsed_count": sum(1 for row in task_results if row.get("status") == "parsed"),
            "failed_count": sum(1 for row in task_results if row.get("status") != "parsed"),
            "wall_seconds": round(time.monotonic() - started, 3),
        },
    )
    return {
        "payload": payload,
        "prompt": _join([str(row.get("prompt") or "") for row in task_results], "global analyst task prompt"),
        "raw": _join([str(row.get("raw") or "") for row in task_results], "global analyst task raw"),
        "report": {
            "schema_id": "global_task_analyst_decision_model_report_v1",
            "method": "task_specific_global_analyst_decision_model",
            "task_count": len(tasks),
            "parsed_count": sum(1 for row in task_results if row.get("status") == "parsed"),
            "failed_count": sum(1 for row in task_results if row.get("status") != "parsed"),
            "parallelism": model_parallelism(backend),
            "wall_seconds": round(time.monotonic() - started, 3),
            "task_reports": [_public_task_report(row) for row in task_results],
            "context_mode": "task_specific",
        },
    }


def build_analyst_decision_model_from_global_tasks(
    context: dict[str, Any],
    task_results: list[dict[str, Any]],
) -> dict[str, Any]:
    payloads = {
        str(result.get("task_id") or ""): _dict(result.get("payload"))
        for result in task_results
        if result.get("status") == "parsed"
    }
    answer_frame = _dict(payloads.get("answer_frame"))
    evidence_roles = _valid_evidence_roles(context, _list(_dict(payloads.get("evidence_roles")).get("evidence_roles")))
    quantity_decisions = _valid_quantity_decisions(context, _list(_dict(payloads.get("quantity_plan")).get("quantity_decisions")))
    source_hierarchy, source_report = normalize_source_hierarchy(
        _dict(payloads.get("source_hierarchy")),
        allowed_source_ids=_context_source_ids(context),
    )
    blueprint = _dict(payloads.get("argument_blueprint"))
    groups = _groups_from_global_tasks(context, answer_frame, evidence_roles, blueprint)
    groups, _ranking_guard = apply_decision_diagnostic_ranking(groups, _rows(context))
    groups = [schema_safe_decision_group(group) for group in groups]
    covered = {
        evidence_id
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    dispositions = _dispositions_from_roles(context, groups, evidence_roles, covered)
    memo_relevance = _memo_relevance_from_roles(context, groups, evidence_roles, dispositions)
    quantity_relevance = _quantity_relevance_from_decisions(context, quantity_decisions, memo_relevance)
    return {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": str(context.get("decision_question") or ""),
        "direct_answer": _short_text(answer_frame.get("best_answer") or _stable_answer(context), 700),
        "confidence": _confidence(answer_frame.get("confidence")),
        "overall_rationale": _overall_rationale(answer_frame, source_hierarchy, blueprint),
        "evidence_groups": groups,
        "evidence_dispositions": dispositions,
        "memo_relevance_decisions": memo_relevance,
        "quantity_relevance_decisions": quantity_relevance,
        "source_hierarchy": source_hierarchy,
        "source_hierarchy_report": source_report,
        "quantitative_anchors": _quantity_anchors(quantity_relevance),
        "what_would_change_the_answer": _what_would_change(answer_frame, evidence_roles),
        "decision_logic": _decision_logic(answer_frame, groups),
        "argument_plan": _argument_plan_from_blueprint(blueprint, groups),
    }


def _run_task(
    task: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
    run_backend: Callable[..., Any],
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    prompt = build_global_analyst_task_prompt(task)
    started = time.monotonic()
    raw = ""
    payload: Any = {}
    error = ""
    attempts = model_stage_attempts()
    retry_reports: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        _emit_progress(
            progress,
            "analyst_decision_model_global_task",
            "started" if attempt == 1 else "retry_started",
            _task_progress_details(task, prompt, attempt=attempt),
        )
        try:
            result = run_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                num_predict=max(2048, min(num_predict, _task_num_predict(str(task["task_id"])))),
                json_mode=True,
            )
            raw = str(getattr(result, "text", result))
            payload = _extract_json(raw)
        except RuntimeError as exc:
            error = str(exc)
            retry_reports.append({"attempt": attempt, "status": "backend_error", "error": error})
            if attempt < attempts:
                _emit_progress(progress, "analyst_decision_model_global_task", "retry_needed", _task_progress_details(task, prompt, attempt=attempt, status="backend_error", error=error, wall_seconds=round(time.monotonic() - started, 3)))
                continue
            break
        status = "parsed" if isinstance(payload, dict) and payload.get("schema_id") else "parse_failed"
        retry_reports.append({"attempt": attempt, "status": status})
        if status == "parsed":
            _emit_progress(progress, "analyst_decision_model_global_task", "completed", _task_progress_details(task, prompt, attempt=attempt, status=status, raw_chars=len(raw), wall_seconds=round(time.monotonic() - started, 3)))
            return _task_result(task, status, prompt, raw, started, payload=payload, retry_reports=retry_reports)
        if attempt < attempts:
            _emit_progress(progress, "analyst_decision_model_global_task", "retry_needed", _task_progress_details(task, prompt, attempt=attempt, status=status, raw_chars=len(raw), wall_seconds=round(time.monotonic() - started, 3)))
    _emit_progress(progress, "analyst_decision_model_global_task", "failed", _task_progress_details(task, prompt, attempt=attempts, status="failed", raw_chars=len(raw), error=error, wall_seconds=round(time.monotonic() - started, 3)))
    return _task_result(task, "failed", prompt, raw, started, payload=payload if isinstance(payload, dict) else {}, issues=[error] if error else [], retry_reports=retry_reports)


def _groups_from_global_tasks(
    context: dict[str, Any],
    answer_frame: dict[str, Any],
    evidence_roles: list[dict[str, Any]],
    blueprint: dict[str, Any],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    groups.extend(_answer_frame_groups(context, answer_frame))
    groups.extend(_blueprint_groups(context, blueprint, evidence_roles))
    groups.extend(_role_groups_for_uncovered(context, evidence_roles, groups))
    return _dedupe_groups(groups)


def _answer_frame_groups(context: dict[str, Any], answer_frame: dict[str, Any]) -> list[dict[str, Any]]:
    groups = []
    for index, row in enumerate(_list(answer_frame.get("main_answer_drivers")), start=1):
        groups.append(
            _group(
                group_id=f"answer_driver_{index:03d}",
                proposition=_reason_or_claim(context, row, fallback="Primary evidence supports the bounded answer."),
                role="load_bearing_primary_support",
                relation="supports_answer",
                evidence_ids=_valid_ids(context, _string_list(_dict(row).get("evidence_item_ids"))),
                rationale=str(_dict(row).get("reason") or ""),
                rank=index,
            )
        )
    for index, row in enumerate(_list(answer_frame.get("main_counterweights")), start=1):
        groups.append(
            _group(
                group_id=f"counterweight_{index:03d}",
                proposition=_reason_or_claim(context, row, fallback="Counterweight evidence bounds or weakens the answer."),
                role="load_bearing_counterweight",
                relation="challenges_answer",
                evidence_ids=_valid_ids(context, _string_list(_dict(row).get("evidence_item_ids"))),
                rationale=str(_dict(row).get("reason") or ""),
                rank=20 + index,
            )
        )
    return [group for group in groups if group.get("covered_evidence_item_ids")]


def _blueprint_groups(context: dict[str, Any], blueprint: dict[str, Any], evidence_roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    role_by_id = {str(row.get("evidence_item_id") or ""): row for row in evidence_roles}
    groups = []
    for index, row in enumerate(_list(blueprint.get("section_plan")), start=1):
        if not isinstance(row, dict):
            continue
        evidence_ids = _valid_ids(context, _string_list(row.get("must_use_evidence_item_ids")))
        if not evidence_ids:
            continue
        role = _dominant_memo_role([role_by_id.get(evidence_id, {}) for evidence_id in evidence_ids])
        relation = _dominant_answer_relation([role_by_id.get(evidence_id, {}) for evidence_id in evidence_ids])
        groups.append(
            _group(
                group_id=f"argument_{_safe_id(row.get('section_id') or index)}",
                proposition=str(row.get("core_claim") or row.get("heading") or ""),
                role=role,
                relation=relation,
                evidence_ids=evidence_ids,
                rationale=str(row.get("section_job") or row.get("source_weighting_move") or ""),
                rank=40 + index,
                applicability_limits=[],
            )
        )
    return groups


def _role_groups_for_uncovered(context: dict[str, Any], evidence_roles: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    covered = {
        evidence_id
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    by_bucket: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    rows_by_id = {str(row.get("evidence_item_id") or ""): row for row in _rows(context)}
    for role_row in evidence_roles:
        evidence_id = str(role_row.get("evidence_item_id") or "")
        if evidence_id in covered:
            continue
        inclusion = _memo_inclusion(role_row.get("memo_inclusion"))
        if inclusion in {"exclude", "trace_only"}:
            continue
        bucket = (
            _decision_role(role_row.get("decision_role")),
            _answer_relation(role_row.get("answer_relation")),
            inclusion,
        )
        by_bucket.setdefault(bucket, []).append(role_row)
    groups_out = []
    for index, ((decision_role, relation, inclusion), rows) in enumerate(sorted(by_bucket.items()), start=1):
        evidence_ids = [str(row.get("evidence_item_id") or "") for row in rows if rows_by_id.get(str(row.get("evidence_item_id") or ""))]
        if not evidence_ids:
            continue
        claims = [str(rows_by_id[evidence_id].get("claim") or "") for evidence_id in evidence_ids[:3]]
        groups_out.append(
            _group(
                group_id=f"{decision_role}_{inclusion}_{index:03d}",
                proposition=_short_text("; ".join(claims), 620),
                role=_memo_role_from_decision_role(decision_role, inclusion),
                relation=relation,
                evidence_ids=evidence_ids,
                rationale=_short_text("; ".join(str(row.get("rationale") or "") for row in rows[:3]), 520),
                rank=60 + index,
            )
        )
    return groups_out


def _group(
    *,
    group_id: str,
    proposition: str,
    role: str,
    relation: str,
    evidence_ids: list[str],
    rationale: str,
    rank: int,
    applicability_limits: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "proposition": _short_text(proposition, 720),
        "memo_role": role,
        "answer_relation": relation,
        "target_answer_option": "",
        "effect_on_final_answer": _effect_for_relation(relation),
        "tension_type": "none",
        "importance_rank": rank,
        "covered_evidence_item_ids": _dedupe(evidence_ids),
        "rationale": _short_text(rationale, 520),
        "evidence_strength": "",
        "answer_impact": _answer_impact_for_relation(relation),
        "uncertainty_type": "none",
        "applicability_limits": applicability_limits or [],
        "conflict_note": "",
    }


def _dispositions_from_roles(
    context: dict[str, Any],
    groups: list[dict[str, Any]],
    evidence_roles: list[dict[str, Any]],
    covered: set[str],
) -> list[dict[str, Any]]:
    role_by_id = {str(row.get("evidence_item_id") or ""): row for row in evidence_roles}
    group_by_id = {
        evidence_id: str(group.get("group_id") or "")
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    rows = []
    for row in _rows(context):
        evidence_id = str(row.get("evidence_item_id") or "")
        role_row = role_by_id.get(evidence_id, {})
        inclusion = _memo_inclusion(role_row.get("memo_inclusion"))
        rows.append(
            {
                "evidence_item_id": evidence_id,
                "disposition": "foreground" if evidence_id in covered else _disposition_from_inclusion(inclusion),
                "group_id": group_by_id.get(evidence_id, ""),
                "rationale": _short_text(role_row.get("rationale") or "Global analyst task evidence disposition.", 360),
            }
        )
    return rows


def _memo_relevance_from_roles(
    context: dict[str, Any],
    groups: list[dict[str, Any]],
    evidence_roles: list[dict[str, Any]],
    dispositions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    role_by_id = {str(row.get("evidence_item_id") or ""): row for row in evidence_roles}
    group_by_id = {
        evidence_id: str(group.get("group_id") or "")
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    disposition_by_id = {str(row.get("evidence_item_id") or ""): row for row in dispositions}
    result = []
    for row in _rows(context):
        evidence_id = str(row.get("evidence_item_id") or "")
        role_row = role_by_id.get(evidence_id, {})
        result.append(
            {
                "evidence_item_id": evidence_id,
                "memo_inclusion": _memo_inclusion(role_row.get("memo_inclusion")),
                "group_id": group_by_id.get(evidence_id) or str(disposition_by_id.get(evidence_id, {}).get("group_id") or ""),
                "source_ids": _string_list(row.get("source_ids")),
                "rationale": _short_text(role_row.get("rationale") or "Global analyst task memo relevance decision.", 360),
            }
        )
    return result


def _quantity_relevance_from_decisions(
    context: dict[str, Any],
    quantity_decisions: list[dict[str, Any]],
    memo_relevance: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = {str(row.get("evidence_item_id") or ""): row for row in _rows(context)}
    valid_quantities = {evidence_id: set(_string_list(row.get("quantity_values"))) for evidence_id, row in rows.items()}
    decisions: dict[tuple[str, str], dict[str, Any]] = {}
    for row in quantity_decisions:
        evidence_id = str(row.get("evidence_item_id") or "")
        quantity = str(row.get("quantity_value") or "")
        if evidence_id not in rows or quantity not in valid_quantities.get(evidence_id, set()):
            continue
        inclusion = _quantity_inclusion(row.get("memo_inclusion"))
        decisions[(evidence_id, quantity)] = {
            "evidence_item_id": evidence_id,
            "quantity_value": quantity,
            "memo_inclusion": inclusion,
            "quantity_role": _quantity_role(row.get("quantity_role"), inclusion),
            "retention_phrase": _short_text(row.get("retention_phrase") or (quantity if inclusion in {"must_use", "supporting_context"} else ""), 220),
            "rationale": _short_text(row.get("rationale") or "Global analyst task quantity relevance decision.", 360),
        }
    memo_by_id = {str(row.get("evidence_item_id") or ""): row for row in memo_relevance}
    for evidence_id, source_row in rows.items():
        for quantity in _string_list(source_row.get("quantity_values")):
            if (evidence_id, quantity) in decisions:
                continue
            memo_inclusion = str(memo_by_id.get(evidence_id, {}).get("memo_inclusion") or "trace_only")
            inclusion = "supporting_context" if memo_inclusion == "memo_spine" and _row_is_quantity_forward(source_row) else "trace_only"
            decisions[(evidence_id, quantity)] = {
                "evidence_item_id": evidence_id,
                "quantity_value": quantity,
                "memo_inclusion": inclusion,
                "quantity_role": "supporting_detail" if inclusion == "supporting_context" else "audit_only",
                "retention_phrase": quantity if inclusion == "supporting_context" else "",
                "rationale": "Quantity retained by conservative accounting from global analyst evidence relevance.",
            }
    return list(decisions.values())


def _valid_evidence_roles(context: dict[str, Any], rows: list[Any]) -> list[dict[str, Any]]:
    known = {str(row.get("evidence_item_id") or "") for row in _rows(context)}
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or "")
        if evidence_id not in known:
            continue
        result.append(
            {
                "evidence_item_id": evidence_id,
                "memo_inclusion": _memo_inclusion(row.get("memo_inclusion")),
                "decision_role": _decision_role(row.get("decision_role")),
                "answer_relation": _answer_relation(row.get("answer_relation")),
                "priority_rank": _rank(row.get("priority_rank")),
                "rationale": _short_text(row.get("rationale"), 420),
            }
        )
    return result


def _valid_quantity_decisions(context: dict[str, Any], rows: list[Any]) -> list[dict[str, Any]]:
    known = {
        str(row.get("evidence_item_id") or ""): set(_string_list(row.get("quantity_values")))
        for row in _rows(context)
    }
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or "")
        quantity = str(row.get("quantity_value") or "")
        if quantity and quantity in known.get(evidence_id, set()):
            result.append(row)
    return result


def _context_source_ids(context: dict[str, Any]) -> list[str]:
    return _dedupe(source_id for row in _rows(context) for source_id in _string_list(row.get("source_ids")))


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}
    candidates = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {}


def _task_result(
    task: dict[str, Any],
    status: str,
    prompt: str,
    raw: str,
    started: float,
    *,
    payload: Any = None,
    issues: list[str] | None = None,
    retry_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "status": status,
        "prompt": prompt,
        "raw": raw,
        "payload": payload if isinstance(payload, dict) else {},
        "duration_seconds": round(time.monotonic() - started, 3),
        "prompt_chars": len(prompt),
        "raw_chars": len(raw),
        "issues": issues or [],
        "attempt_count": len(retry_reports or []),
        "retry_reports": retry_reports or [],
    }


def _public_task_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": row.get("task_id"),
        "status": row.get("status"),
        "duration_seconds": row.get("duration_seconds"),
        "prompt_chars": row.get("prompt_chars"),
        "raw_chars": row.get("raw_chars"),
        "issues": row.get("issues", []),
        "attempt_count": row.get("attempt_count", 0),
        "retry_reports": row.get("retry_reports", []),
    }


def _task_progress_details(
    task: dict[str, Any],
    prompt: str,
    *,
    attempt: int,
    status: str = "",
    raw_chars: int = 0,
    wall_seconds: float | None = None,
    error: str = "",
) -> dict[str, Any]:
    context = _dict(task.get("context"))
    details: dict[str, Any] = {
        "substage": "analyst_decision_model_global_task",
        "task_id": task.get("task_id"),
        "row_count": len(_list(context.get("evidence_rows") or context.get("decision_diagnostic_evidence_rows") or context.get("quantity_bearing_evidence_rows"))),
        "attempt": attempt,
        "prompt_chars": len(prompt),
    }
    if status:
        details["task_status"] = status
    if raw_chars:
        details["raw_chars"] = raw_chars
    if wall_seconds is not None:
        details["wall_seconds"] = wall_seconds
    if error:
        details["error"] = _short_text(error, 240)
    return details


def _emit_progress(
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    substage: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    if progress is None:
        return
    try:
        progress("decision_packet_substage", status, {"substage": substage, **(details or {})})
    except Exception:
        return


def _threshold() -> int:
    try:
        return max(1, int(os.environ.get("ECM_ANALYST_DECISION_MODEL_PARALLEL_THRESHOLD", "12")))
    except ValueError:
        return 12


def _task_num_predict(task_id: str) -> int:
    return {
        "answer_frame": 4096,
        "evidence_roles": 8192,
        "quantity_plan": 6144,
        "source_hierarchy": 4096,
        "argument_blueprint": 6144,
    }.get(task_id, 4096)


def _rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(context.get("evidence_rows")) if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()]


def _valid_ids(context: dict[str, Any], ids: list[str]) -> list[str]:
    known = {str(row.get("evidence_item_id") or "") for row in _rows(context)}
    return [evidence_id for evidence_id in ids if evidence_id in known]


def _dedupe_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for group in [group for group in groups if group.get("covered_evidence_item_ids")]:
        group_id = str(group.get("group_id") or "")
        if group_id in seen:
            group = dict(group)
            group["group_id"] = f"{group_id}_{len(seen) + 1:03d}"
        seen.add(str(group.get("group_id") or ""))
        deduped.append(group)
    return deduped


def _reason_or_claim(context: dict[str, Any], row: Any, *, fallback: str) -> str:
    data = _dict(row)
    reason = str(data.get("reason") or "").strip()
    if reason:
        return reason
    rows_by_id = {str(source.get("evidence_item_id") or ""): source for source in _rows(context)}
    claims = [
        str(rows_by_id[evidence_id].get("claim") or "")
        for evidence_id in _string_list(data.get("evidence_item_ids"))
        if evidence_id in rows_by_id
    ]
    return _short_text("; ".join(claims) or fallback, 620)


def _dominant_memo_role(rows: list[dict[str, Any]]) -> str:
    roles = [_decision_role(row.get("decision_role")) for row in rows if row]
    for role, memo_role in (
        ("counterweight", "load_bearing_counterweight"),
        ("crux", "decision_crux"),
        ("scope_boundary", "scope_or_applicability"),
        ("calibrator", "quantitative_anchor"),
        ("answer_driver", "load_bearing_primary_support"),
    ):
        if role in roles:
            return memo_role
    return "mechanism_or_context"


def _dominant_answer_relation(rows: list[dict[str, Any]]) -> str:
    relations = [_answer_relation(row.get("answer_relation")) for row in rows if row]
    for relation in ("challenges_answer", "identifies_crux", "bounds_scope", "supports_answer", "contextualizes_answer"):
        if relation in relations:
            return relation
    return "contextualizes_answer"


def _memo_role_from_decision_role(role: str, inclusion: str) -> str:
    if role == "answer_driver":
        return "load_bearing_primary_support"
    if role == "counterweight":
        return "load_bearing_counterweight"
    if role == "calibrator":
        return "quantitative_anchor"
    if role == "scope_boundary":
        return "scope_or_applicability"
    if role == "crux":
        return "decision_crux"
    if inclusion == "memo_spine":
        return "mechanism_or_context"
    return "background_only"


def _decision_role(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"answer_driver", "calibrator", "counterweight", "scope_boundary", "crux", "context"} else "context"


def _answer_relation(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"supports_answer", "challenges_answer", "bounds_scope", "identifies_crux", "contextualizes_answer", "not_decision_relevant", "uncertain_relation"} else "contextualizes_answer"


def _memo_inclusion(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"memo_spine", "supporting_context", "trace_only", "exclude"} else "trace_only"


def _quantity_inclusion(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"must_use", "supporting_context", "trace_only", "exclude"} else "trace_only"


def _quantity_role(value: Any, inclusion: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"decision_anchor", "supporting_detail", "study_descriptor", "statistical_detail", "audit_only"}:
        return text
    if inclusion == "must_use":
        return "decision_anchor"
    if inclusion == "supporting_context":
        return "supporting_detail"
    return "audit_only"


def _disposition_from_inclusion(inclusion: str) -> str:
    if inclusion in {"memo_spine", "supporting_context"}:
        return "foreground"
    if inclusion == "exclude":
        return "not_decision_relevant"
    return "background"


def _effect_for_relation(relation: str) -> str:
    return {
        "supports_answer": "supports current_best_answer",
        "challenges_answer": "weakens current_best_answer",
        "bounds_scope": "bounds current_best_answer",
        "identifies_crux": "distinguishes live options",
        "contextualizes_answer": "background",
    }.get(relation, "background")


def _answer_impact_for_relation(relation: str) -> str:
    return {
        "supports_answer": "Supports the current best answer.",
        "challenges_answer": "Weakens or bounds confidence in the current best answer.",
        "bounds_scope": "Defines where the answer applies.",
        "identifies_crux": "Identifies what would change the answer.",
        "contextualizes_answer": "Provides context for interpreting or applying the answer.",
    }.get(relation, "Provides context for the answer.")


def _rank(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 100


def _safe_id(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9_:-]+", "_", str(value or "")).strip("_").lower()
    return text or "section"


def _stable_answer(context: dict[str, Any]) -> str:
    return str(_dict(context.get("stable_final_answer_frame")).get("current_best_answer") or "")


def _confidence(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"low", "medium", "high", "not_specified"} else "not_specified"


def _overall_rationale(answer_frame: dict[str, Any], source_hierarchy: dict[str, Any], blueprint: dict[str, Any]) -> str:
    return _short_text(
        " ".join(
            text
            for text in (
                str(answer_frame.get("confidence_basis") or ""),
                str(source_hierarchy.get("hierarchy_thesis") or ""),
                str(blueprint.get("memo_thesis") or ""),
            )
            if text.strip()
        ),
        900,
    )


def _quantity_anchors(quantity_relevance: list[dict[str, Any]]) -> list[str]:
    return _dedupe(
        str(row.get("retention_phrase") or row.get("quantity_value") or "")
        for row in quantity_relevance
        if row.get("memo_inclusion") in {"must_use", "supporting_context"}
    )[:20]


def _what_would_change(answer_frame: dict[str, Any], evidence_roles: list[dict[str, Any]]) -> list[str]:
    values = _string_list(answer_frame.get("what_would_change_the_answer"))
    values.extend(str(row.get("rationale") or "") for row in evidence_roles if row.get("decision_role") == "crux")
    return _dedupe(_short_text(value, 320) for value in values if value)[:8]


def _decision_logic(answer_frame: dict[str, Any], groups: list[dict[str, Any]]) -> dict[str, Any]:
    support = _first_group(groups, "load_bearing_primary_support")
    counterweight = _first_group(groups, "load_bearing_counterweight")
    logic = {
        "bounded_bottom_line": _short_text(answer_frame.get("best_answer"), 700),
        "support_summary": support,
        "strongest_counterweight": counterweight,
        "counterweight_weighting": _short_text(" ".join(_string_list(answer_frame.get("scope_boundaries"))[:3]), 420),
        "reconciled_cruxes": _what_would_change(answer_frame, []),
        "scope_boundaries": _string_list(answer_frame.get("scope_boundaries"))[:6],
        "practical_implications": _string_list(answer_frame.get("practical_implication"))[:6],
        "do_not_overstate": _string_list(answer_frame.get("do_not_overstate"))[:8],
    }
    return naturalize_decision_logic_payload(logic)


def _first_group(groups: list[dict[str, Any]], role: str) -> str:
    for group in groups:
        if group.get("memo_role") == role:
            return str(group.get("proposition") or "")
    return ""


def _argument_plan_from_blueprint(blueprint: dict[str, Any], groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, row in enumerate(_list(blueprint.get("section_plan")), start=1):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "step_id": _safe_id(row.get("section_id") or f"step_{index:03d}"),
                "section": str(row.get("heading") or "Decision Brief"),
                "writing_goal": _short_text(row.get("section_job") or row.get("core_claim"), 360),
                "required_points": _dedupe(
                    [
                        str(row.get("core_claim") or ""),
                        *_string_list(row.get("must_use_quantities")),
                        str(row.get("source_weighting_move") or ""),
                    ]
                )[:8],
                "evidence_item_ids": _string_list(row.get("must_use_evidence_item_ids"))[:14],
                "transition_from_previous": _short_text(row.get("transition") or argument_plan_transition(str(row.get("section_id") or "")), 260),
            }
        )
    if rows:
        return rows[:12]
    return [
        {
            "step_id": str(group.get("group_id") or f"group_{index:03d}"),
            "section": "Decision Brief",
            "writing_goal": _short_text(group.get("rationale") or group.get("proposition"), 360),
            "required_points": [str(group.get("proposition") or "")],
            "evidence_item_ids": _string_list(group.get("covered_evidence_item_ids")),
            "transition_from_previous": argument_plan_transition(str(group.get("memo_role") or "")),
        }
        for index, group in enumerate(groups[:8], start=1)
    ]


def _row_is_quantity_forward(row: dict[str, Any]) -> bool:
    return str(row.get("current_role") or row.get("adjudicated_memo_use") or "").strip() in {
        "quantitative_anchor",
        "load_bearing_primary_support",
        "load_bearing_counterweight",
        "decision_crux",
    }


def _join(chunks: list[str], label: str) -> str:
    return "\n\n".join(f"--- {label} {index} ---\n{chunk}" for index, chunk in enumerate(chunks, start=1) if chunk)
