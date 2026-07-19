from __future__ import annotations

from collections.abc import Callable
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_section_parse import parse_section_payload
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_retry import SECTION_MODEL_ATTEMPTS, retry_section_prompt
from epistemic_case_mapper.model_backends import run_model_backend


def run_section_model_attempts(
    *,
    prompt: str,
    expected_title: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    validate: Callable[[str], tuple[str, list[str]]],
    adjudicate: Callable[[str, list[str]], dict[str, Any]] | None = None,
    run_backend: Callable[..., Any] = run_model_backend,
) -> dict[str, Any]:
    active_prompt = prompt
    raw = ""
    attempts: list[dict[str, Any]] = []
    issues: list[str] = []
    last_rewritten = ""
    for attempt in range(1, SECTION_MODEL_ATTEMPTS + 1):
        try:
            result = run_backend(active_prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
        except RuntimeError as exc:
            return _result(False, active_prompt, raw, [str(exc)], attempts, attempt, status="backend_error")
        raw = result.text
        if result.prompt_only:
            return _result(False, active_prompt, raw, ["backend returned prompt only"], attempts, attempt, status="prompt_only")
        payload = parse_section_payload(raw, expected_title=expected_title)
        if not isinstance(payload, dict):
            issues = ["section response was not one Markdown section with the expected heading"]
            attempts.append({"attempt": attempt, "status": "parse_failed", "issues": issues, "raw": raw})
        else:
            rewritten = str(payload.get("section_markdown") or payload.get("memo_markdown") or "").strip()
            last_rewritten = rewritten
            repaired, issues = validate(rewritten)
            deterministic_issues = issues
            adjudication = _adjudicate_if_needed(adjudicate, repaired, deterministic_issues)
            if adjudication:
                issues = [str(issue) for issue in adjudication.get("confirmed_issues", [])]
            attempt_record = {
                "attempt": attempt,
                "status": _attempt_status(issues, deterministic_issues, adjudication),
                "issues": issues,
                "raw": raw,
            }
            if adjudication:
                attempt_record["deterministic_issues"] = deterministic_issues
                attempt_record["validator_warnings"] = adjudication.get("unconfirmed_issues", [])
                attempt_record["adjudication"] = _compact_adjudication(adjudication)
            attempts.append(attempt_record)
            if not issues:
                return _result(
                    True,
                    active_prompt,
                    raw,
                    [],
                    attempts,
                    attempt,
                    section=repaired,
                    rewritten=rewritten,
                    status="accepted_after_adjudication" if adjudication and deterministic_issues else "",
                )
        if attempt < SECTION_MODEL_ATTEMPTS:
            active_prompt = retry_section_prompt(prompt, issues, attempt=attempt + 1, rejected_section=_retry_section_text(payload, raw))
    return _result(False, active_prompt, raw, issues, attempts, len(attempts), status="rejected", rewritten=last_rewritten)


def _adjudicate_if_needed(
    adjudicate: Callable[[str, list[str]], dict[str, Any]] | None,
    repaired: str,
    issues: list[str],
) -> dict[str, Any]:
    if not adjudicate or not issues:
        return {}
    try:
        result = adjudicate(repaired, issues)
    except Exception as exc:
        return {
            "schema_id": "section_validation_adjudication_v1",
            "status": "adjudication_unavailable_exception",
            "confirmed_issues": [],
            "unconfirmed_issues": issues,
            "repair_instructions": [],
            "issue_assessments": [{"issue": issue, "blocking": False, "reason": str(exc)} for issue in issues],
        }
    return result if isinstance(result, dict) else {}


def _attempt_status(
    issues: list[str],
    deterministic_issues: list[str],
    adjudication: dict[str, Any],
) -> str:
    if not deterministic_issues:
        return "accepted"
    if adjudication and not issues:
        return "accepted_after_adjudication"
    return "rejected"


def _compact_adjudication(adjudication: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": adjudication.get("schema_id"),
        "status": adjudication.get("status"),
        "confirmed_issues": adjudication.get("confirmed_issues", []),
        "unconfirmed_issues": adjudication.get("unconfirmed_issues", []),
        "repair_instructions": adjudication.get("repair_instructions", []),
        "issue_assessments": adjudication.get("issue_assessments", []),
    }


def _retry_section_text(payload: Any, raw: str) -> str:
    if isinstance(payload, dict):
        return str(payload.get("section_markdown") or payload.get("memo_markdown") or "").strip()
    return raw if str(raw).lstrip().startswith("## ") else ""


def _result(
    accepted: bool,
    prompt: str,
    raw: str,
    issues: list[str],
    attempts: list[dict[str, Any]],
    attempt_count: int,
    *,
    section: str = "",
    rewritten: str = "",
    status: str = "",
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "status": status or ("accepted_after_repair" if section != rewritten else "accepted"),
        "section": section,
        "rewritten": rewritten,
        "prompt": prompt,
        "raw": raw,
        "issues": issues,
        "attempts": attempts,
        "attempt_count": attempt_count,
    }
