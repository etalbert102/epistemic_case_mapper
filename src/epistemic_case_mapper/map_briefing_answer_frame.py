from __future__ import annotations

import re
from typing import Any


def arbitrate_answer_frame(
    scaffold: dict[str, Any],
    *,
    bottom_line: dict[str, str],
    evidence_lines: list[dict[str, Any]],
    exceptions: list[dict[str, str]],
) -> dict[str, Any]:
    """Keep default-answer and exception-answer roles separate before prose synthesis."""
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    default_read = _default_read(decision_model, evidence_lines)
    exception_read = _exception_read(exceptions)
    current_read = str(bottom_line.get("current_read", "")).strip()
    issue = _frame_issue(current_read, default_read, exception_read)
    revised = dict(bottom_line)
    if issue:
        revised["current_read"] = _combined_read(default_read, exception_read, current_read)
        revised["why_this_frame"] = _combined_why(bottom_line, exception_read)
    return {
        "schema_id": "answer_frame_arbitration_v1",
        "method": "deterministic_default_then_exception_frame_check",
        "status": "reframed" if issue else "unchanged",
        "issue": issue,
        "default_read": default_read,
        "exception_read": exception_read,
        "original_bottom_line": bottom_line,
        "bottom_line": revised,
    }


def _default_read(decision_model: dict[str, Any], evidence_lines: list[dict[str, Any]]) -> str:
    default = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    candidates = [
        str(default.get("plain_language_instruction", "")),
        *[
            str(row.get("proposition", ""))
            for row in decision_model.get("main_reasons", [])
            if isinstance(row, dict)
        ],
        *[
            str(line.get("current_read", ""))
            for line in evidence_lines
            if isinstance(line, dict) and line.get("role") in {"direct_outcome", "guidance_or_practical_advice", "general_evidence"}
        ],
        str(default.get("why_this_frame", "")),
    ]
    for candidate in candidates:
        cleaned = _readerize(candidate)
        if cleaned and not _exception_led(cleaned) and not _gap_language(cleaned):
            return cleaned
    return ""


def _exception_read(exceptions: list[dict[str, str]]) -> str:
    for exception in exceptions:
        text = _readerize(str(exception.get("current_read", "")))
        if text and not _gap_language(text):
            condition = str(exception.get("condition", "")).strip()
            return f"{condition}: {text}" if condition else text
    return ""


def _frame_issue(current_read: str, default_read: str, exception_read: str) -> str:
    if not current_read or not default_read or not exception_read:
        return ""
    if _exception_led(current_read) or "named conditions" in current_read.lower():
        return "bottom_line_exception_led_despite_available_default_read"
    return ""


def _combined_read(default_read: str, exception_read: str, current_read: str) -> str:
    default_sentence = _sentence(default_read)
    exception_sentence = _sentence(exception_read)
    if default_sentence and exception_sentence:
        return f"{default_sentence} Treat the named exception separately: {exception_sentence}"
    return default_sentence or exception_sentence or current_read


def _combined_why(bottom_line: dict[str, str], exception_read: str) -> str:
    why = _readerize(str(bottom_line.get("why_this_frame", "")))
    if exception_read and "exception" not in why.lower():
        return _sentence(why) + " The exception evidence limits transfer rather than replacing the default answer."
    return why


def _readerize(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" .")
    cleaned = re.sub(r"^(?:state|say|phrase)\s+that\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^do not\s+", "Avoid ", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" .")


def _exception_led(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered.startswith(("caution", "warning", "avoid", "for people with", "for individuals with", "under named", "counterevidence")) or "named conditions" in lowered


def _gap_language(text: str) -> bool:
    lowered = text.lower()
    return "source packet does not establish" in lowered or "map does not cleanly establish" in lowered or "map lacks clean" in lowered


def _sentence(text: str) -> str:
    cleaned = _readerize(text)
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "?", "!")) else cleaned + "."
