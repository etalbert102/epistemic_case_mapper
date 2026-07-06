from __future__ import annotations

from collections.abc import Callable
from typing import Any

from epistemic_case_mapper.map_briefing_section_parse import parse_section_payload
from epistemic_case_mapper.map_briefing_section_retry import SECTION_MODEL_ATTEMPTS, retry_section_prompt
from epistemic_case_mapper.model_backends import run_model_backend


def run_section_model_attempts(
    *,
    prompt: str,
    expected_title: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    validate: Callable[[str], tuple[str, list[str]]],
    run_backend: Callable[..., Any] = run_model_backend,
) -> dict[str, Any]:
    active_prompt = prompt
    raw = ""
    attempts: list[dict[str, Any]] = []
    issues: list[str] = []
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
            attempts.append({"attempt": attempt, "status": "parse_failed", "issues": issues})
        else:
            rewritten = str(payload.get("section_markdown") or payload.get("memo_markdown") or "").strip()
            repaired, issues = validate(rewritten)
            attempts.append({"attempt": attempt, "status": "rejected" if issues else "accepted", "issues": issues})
            if not issues:
                return _result(True, active_prompt, raw, [], attempts, attempt, section=repaired, rewritten=rewritten)
        if attempt < SECTION_MODEL_ATTEMPTS:
            active_prompt = retry_section_prompt(prompt, issues, attempt=attempt + 1)
    return _result(False, active_prompt, raw, issues, attempts, len(attempts), status="rejected")


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
