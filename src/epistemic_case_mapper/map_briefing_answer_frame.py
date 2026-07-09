from __future__ import annotations

import ast
import re
from typing import Any


def arbitrate_answer_frame(
    scaffold: dict[str, Any],
    *,
    bottom_line: dict[str, Any],
    evidence_lines: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_model = _dict(scaffold.get("decision_model"))
    default = _dict(decision_model.get("default_answer"))
    current = _dict(bottom_line)
    default_read = _default_case_read(default, decision_model, evidence_lines)
    exception_text = _exception_text(exceptions)
    should_reframe = bool(default_read and exception_text and _exception_driven(current, default))
    if should_reframe:
        read = default_read
        if exception_text:
            read = f"{read} Treat the named exception separately: {exception_text}."
        return {
            "schema_id": "answer_frame_arbitration_v1",
            "status": "reframed",
            "reason": "separated_default_case_from_exception",
            "bottom_line": _drop_empty(
                {
                    **current,
                    "current_read": _short_text(read, 700),
                    "confidence": current.get("confidence") or decision_model.get("confidence"),
                }
            ),
        }
    return {
        "schema_id": "answer_frame_arbitration_v1",
        "status": "unchanged",
        "reason": "bottom_line_already_matches_default_frame",
        "bottom_line": _drop_empty(current),
    }


def normalize_answer_frame(
    *,
    canonical_decision_spine: dict[str, Any],
    argument_model: dict[str, Any],
    question: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    default = _dict(canonical_decision_spine.get("default_answer"))
    proposed = argument_model.get("proposed_answer")
    raw_current = proposed.get("current_read") or proposed.get("classification") if isinstance(proposed, dict) else proposed
    default_claim = default.get("claim") or ""
    raw_current = raw_current or default_claim or _grounded_answer_frame_fallback(
        canonical_decision_spine=canonical_decision_spine,
        argument_model=argument_model,
        question=question,
    )
    normalized, status = _clean_structured_text(raw_current)
    default_normalized, _default_status = _clean_structured_text(default_claim)
    if (
        is_weak_answer_frame(normalized, question=question)
        and default_normalized
        and not is_weak_answer_frame(default_normalized, question=question)
    ):
        normalized = default_normalized
        status = f"{status}_used_canonical_default"
    if is_weak_answer_frame(normalized, question=question):
        fallback = _grounded_answer_frame_fallback(
            canonical_decision_spine=canonical_decision_spine,
            argument_model=argument_model,
            question=question,
        )
        if fallback and fallback != normalized:
            normalized = fallback
            status = f"{status}_grounded_fallback"
    frame = _drop_empty(
        {
            "default_answer": _short_text(normalized, 420),
            "classification": _classification(proposed, raw_current),
            "confidence": str(canonical_decision_spine.get("confidence") or argument_model.get("confidence") or "medium"),
            "scope": _short_text(" ".join(_string_list(default.get("limits"))), 260),
            "main_uncertainty": _short_text(" ".join(_string_list(argument_model.get("confidence_reasons"))), 260),
        }
    )
    return frame, {
        "schema_id": "answer_frame_normalization_report_v1",
        "status": status,
        "raw_default_answer": _short_text(str(raw_current or ""), 500),
        "normalized_default_answer": frame.get("default_answer", ""),
        "changed": str(raw_current or "").strip() != frame.get("default_answer", ""),
    }


def is_weak_answer_frame(text: str, *, question: str = "") -> bool:
    lowered = " ".join(str(text or "").lower().split())
    if not lowered:
        return True
    if lowered in {"unclear", "mixed", "uncertain", "insufficient evidence"}:
        return True
    if _looks_like_structure(lowered):
        return True
    weak_phrases = (
        "neutral or low-concern default under the stated conditions",
        "neutral or low concern default under the stated conditions",
        "default answer under stated conditions",
        "bounded answer frame",
        "current answer frame",
        "the source packet supports a bounded",
        "the current map supports a",
        "current answer is bounded by the source-backed finding",
        "bounded answer to the decision question",
        "source-backed support for the decision question",
        "does not yet contain a clean source-backed answer",
        "the available evidence supports the default answer",
        "evidence supports the default answer",
    )
    if any(phrase in lowered for phrase in weak_phrases):
        return True
    artifact_terms = (
        "answer frame",
        "default answer",
        "current answer",
        "source packet",
        "evidence packet",
        "decision question",
        "stated conditions",
        "available evidence",
    )
    artifact_count = sum(1 for term in artifact_terms if term in lowered)
    if artifact_count >= 2 and len(lowered.split()) <= 28:
        return True
    question_terms = _content_terms(question)
    if question_terms and len(lowered.split()) <= 18:
        overlap = set(_content_terms(lowered)) & set(question_terms)
        if not overlap and any(term in lowered for term in ("evidence", "default", "current", "answer", "frame")):
            return True
    return False


def _default_case_read(
    default: dict[str, Any],
    decision_model: dict[str, Any],
    evidence_lines: list[dict[str, Any]],
) -> str:
    instruction = str(default.get("plain_language_instruction") or default.get("current_read") or default.get("claim") or "").strip()
    if instruction.lower().startswith("for the default case"):
        return _sentence(instruction)
    for row in _dicts(decision_model.get("main_reasons")) + _dicts(evidence_lines):
        proposition = str(row.get("proposition") or row.get("current_read") or row.get("claim") or "").strip()
        if proposition and not _artifact_language(proposition):
            return _sentence(proposition)
    return _sentence(instruction)


def _exception_text(exceptions: list[dict[str, Any]]) -> str:
    parts = []
    for row in exceptions:
        if not isinstance(row, dict):
            continue
        condition = str(row.get("condition") or row.get("scope") or "").strip()
        read = str(row.get("current_read") or row.get("claim") or "").strip()
        text = " ".join(part for part in (condition, read) if part)
        if text:
            parts.append(text)
    return _short_text("; ".join(parts), 260)


def _exception_driven(bottom_line: dict[str, Any], default: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            bottom_line.get("classification"),
            bottom_line.get("current_read"),
            bottom_line.get("why_this_frame"),
            default.get("plain_language_instruction"),
            default.get("why_this_frame"),
        )
    ).lower()
    return any(term in text for term in ("condition", "exception", "subgroup", "caution", "harm", "counterevidence"))


def _clean_structured_text(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", "missing"
    parsed = _parse_dict_like(text)
    if parsed:
        current = str(parsed.get("current_read") or parsed.get("claim") or parsed.get("classification") or "").strip()
        return current, "normalized_structured_text" if current else "normalized_empty_structured_text"
    current = _regex_field(text, "current_read") or _regex_field(text, "claim")
    if current:
        return current, "recovered_field_from_malformed_text"
    if _looks_like_structure(text):
        cleaned = re.sub(r"[{}]+", " ", text)
        cleaned = re.sub(r"['\"]?[a-zA-Z_]+['\"]?\s*:", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
        return cleaned, "stripped_malformed_structure"
    return text, "plain_text"


def _classification(proposed: Any, raw_current: Any) -> str:
    if isinstance(proposed, dict) and proposed.get("classification"):
        return str(proposed.get("classification") or "").strip()
    parsed = _parse_dict_like(str(raw_current or ""))
    return str(parsed.get("classification") or "").strip() if parsed else ""


def _grounded_answer_frame_fallback(
    *,
    canonical_decision_spine: dict[str, Any],
    argument_model: dict[str, Any],
    question: str,
) -> str:
    support = _first_statement(
        _dicts(argument_model.get("strongest_support"))
        + _dicts(argument_model.get("quantitative_anchors"))
        + _dicts(canonical_decision_spine.get("strongest_support"))
    )
    counter = _first_statement(
        _dicts(argument_model.get("strongest_counterarguments"))
        + _dicts(canonical_decision_spine.get("strongest_counterevidence"))
    )
    if support:
        return _short_text(f"The packet supports only a bounded answer to the decision question, anchored by this source-backed finding: {support}", 520)
    if counter:
        return _short_text(f"The packet does not support a clean default answer; the most decision-relevant counterweight is: {counter}", 520)
    if question:
        return f"The packet does not yet contain a clean source-backed answer to: {question}"
    return "The packet does not yet contain a clean source-backed answer."


def _first_statement(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        text = str(row.get("claim") or row.get("statement") or row.get("proposition") or "").strip()
        if text and not is_weak_answer_frame(text):
            return _sentence(text)
    return ""


def _parse_dict_like(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return {}
    try:
        parsed = ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _regex_field(text: str, field: str) -> str:
    match = re.search(rf"['\"]?{re.escape(field)}['\"]?\s*:\s*['\"]([^'\"]+)", text)
    return match.group(1).strip() if match else ""


def _looks_like_structure(text: str) -> bool:
    return text.strip().startswith("{") or any(token in text for token in ("'classification'", '"classification"', "'current_read'", '"current_read"'))


def _content_terms(text: str) -> list[str]:
    generic = {
        "about",
        "advice",
        "answer",
        "available",
        "because",
        "bounded",
        "clean",
        "conditions",
        "current",
        "decision",
        "default",
        "evidence",
        "frame",
        "generally",
        "meaningfully",
        "question",
        "source",
        "stated",
        "supports",
        "treated",
        "under",
        "with",
    }
    terms: list[str] = []
    for term in re.findall(r"[a-z][a-z0-9\-]{3,}", str(text).lower()):
        if term not in generic and term not in terms:
            terms.append(term)
    return terms


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "?", "!")) else cleaned + "."


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _sentence(text: str) -> str:
    cleaned = _short_text(text, 520).rstrip()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "?", "!")) else f"{cleaned}."


def _artifact_language(text: str) -> bool:
    lowered = text.lower()
    return "state that " in lowered or "identify the default" in lowered or "separate those conditions" in lowered
