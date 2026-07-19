from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_analyst_decision_model_global_task_prompts import build_global_analyst_task_prompt
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
)
from epistemic_case_mapper.model_backends import model_parallelism, run_parallel
from epistemic_case_mapper.model_stage_retry import model_stage_attempts


def run_global_analyst_task_calls(
    tasks: list[dict[str, Any]],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
    run_backend: Callable[..., Any],
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> list[dict[str, Any]]:
    return run_parallel(
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


def public_global_task_report(row: dict[str, Any]) -> dict[str, Any]:
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
        _emit_progress(progress, "analyst_decision_model_global_task", "started" if attempt == 1 else "retry_started", _task_progress_details(task, prompt, attempt=attempt))
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
        status = "parsed" if _payload_matches_task_schema(task, payload) else "parse_failed"
        retry_reports.append({"attempt": attempt, "status": status})
        if status == "parsed":
            _emit_progress(progress, "analyst_decision_model_global_task", "completed", _task_progress_details(task, prompt, attempt=attempt, status=status, raw_chars=len(raw), wall_seconds=round(time.monotonic() - started, 3)))
            return _task_result(task, status, prompt, raw, started, payload=payload, retry_reports=retry_reports)
        if attempt < attempts:
            _emit_progress(progress, "analyst_decision_model_global_task", "retry_needed", _task_progress_details(task, prompt, attempt=attempt, status=status, raw_chars=len(raw), wall_seconds=round(time.monotonic() - started, 3)))
    _emit_progress(progress, "analyst_decision_model_global_task", "failed", _task_progress_details(task, prompt, attempt=attempts, status="failed", raw_chars=len(raw), error=error, wall_seconds=round(time.monotonic() - started, 3)))
    return _task_result(task, "failed", prompt, raw, started, payload=payload if isinstance(payload, dict) else {}, issues=[error] if error else [], retry_reports=retry_reports)


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
        "row_count": _task_row_count(context),
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


def _payload_matches_task_schema(task: dict[str, Any], payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    expected = str(_dict(task.get("schema")).get("schema_id") or "").strip()
    actual = str(payload.get("schema_id") or "").strip()
    if not expected or actual != expected:
        return False
    task_id = str(task.get("task_id") or "")
    if task_id == "evidence_reconciliation":
        return isinstance(payload.get("groups"), list) or isinstance(payload.get("overrides"), list)
    if task_id == "quantity_plan":
        return isinstance(payload.get("quantity_decisions"), list)
    if task_id == "source_hierarchy":
        return isinstance(payload.get("lanes"), dict) or isinstance(payload.get("source_accounting"), list)
    if task_id == "argument_blueprint":
        return isinstance(payload.get("section_plan"), list)
    if task_id == "answer_frame":
        return bool(str(payload.get("best_answer") or "").strip())
    return True


def _task_row_count(context: dict[str, Any]) -> int:
    for key in (
        "all_evidence_roster",
        "evidence_rows",
        "decision_diagnostic_evidence_rows",
        "quantity_bearing_evidence_rows",
        "top_decision_evidence",
    ):
        rows = _list(context.get(key))
        if rows:
            return len(rows)
    return 0


def _task_num_predict(task_id: str) -> int:
    return {
        "answer_frame": 4096,
        "evidence_roles": 8192,
        "evidence_reconciliation": 6144,
        "quantity_plan": 6144,
        "source_hierarchy": 4096,
        "source_weighting_guidance": 4096,
        "argument_blueprint": 6144,
    }.get(task_id, 4096)
