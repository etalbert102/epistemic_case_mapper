from __future__ import annotations

import re
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_full_memo_polish import (
    build_full_memo_warning_repair_prompt,
    restore_full_memo_protected_content,
)
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.synthesis_uplift_packet import _parse_json

RepairFn = Callable[[str, dict[str, Any], dict[str, Any]], str]
ValidateFn = Callable[[str, str, str, dict[str, Any], dict[str, Any], dict[str, Any]], list[str]]
PreservationFn = Callable[..., list[str]]
JudgeFn = Callable[..., dict[str, Any]]
JudgeIssuesFn = Callable[[Any], list[str]]


def run_full_memo_warning_repair(
    memo: str,
    warnings: list[str],
    *,
    original_memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    contract: dict[str, Any],
    obligation_packet: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    repair_candidate: RepairFn,
    validate_candidate: ValidateFn,
    preservation_issues_fn: PreservationFn,
    judge_fn: JudgeFn,
    judge_issues_fn: JudgeIssuesFn,
) -> dict[str, Any]:
    repair_packet = build_warning_repair_packet(original_memo, warnings, obligation_packet)
    prompt = build_full_memo_warning_repair_prompt(memo, warnings, repair_packet)
    report: dict[str, Any] = {
        "schema_id": "reader_memo_warning_repair_report_v1",
        "status": "not_run",
        "accepted": False,
        "initial_warnings": warnings,
        "repair_packet": repair_packet,
        "issues": [],
    }
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "accepted": False, "report": report}
    raw = result.text
    if result.prompt_only:
        report.update({"status": "prompt_backend_kept_original", "issues": ["warning repair backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "accepted": False, "report": report}
    parse_issue = full_memo_markdown_payload_issue(raw)
    if parse_issue:
        report.update({"status": "format_error_kept_original", "issues": [parse_issue]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "accepted": False, "report": report}
    repaired = repair_candidate(
        restore_full_memo_protected_content(_extract_polished_memo(raw), original_memo=original_memo, contract=contract),
        scaffold,
        contract,
    )
    repaired = restore_full_memo_protected_content(repaired, original_memo=original_memo, contract=contract)
    deterministic_warnings = preservation_issues_fn(
        repaired,
        original_memo=original_memo,
        evidence_appendix=evidence_appendix,
        scaffold=scaffold,
        candidate_map=candidate_map,
        contract=contract,
        obligation_packet=obligation_packet,
        validate_candidate=validate_candidate,
    )
    judge_result = judge_fn(
        original_memo=original_memo,
        polished_memo=repaired,
        obligation_packet=obligation_packet,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    judge_warnings = judge_issues_fn(judge_result.get("payload"))
    remaining_warnings = deterministic_warnings + judge_warnings
    report.update(
        {
            "status": "accepted" if len(remaining_warnings) < len(warnings) else "no_warning_reduction_kept_original",
            "accepted": len(remaining_warnings) < len(warnings),
            "warnings": remaining_warnings,
            "deterministic_warnings": deterministic_warnings,
            "judge_warnings": judge_warnings,
            "judge": judge_result.get("payload", {}),
            "word_count": len(repaired.split()),
        }
    )
    return {"memo": repaired if report["accepted"] else memo, "prompt": prompt, "raw": raw, "accepted": report["accepted"], "report": report}


def build_warning_repair_packet(original_memo: str, warnings: list[str], obligation_packet: dict[str, Any]) -> dict[str, Any]:
    number_contexts = _missing_number_contexts(original_memo, warnings, obligation_packet)
    source_label_contexts = _missing_source_label_contexts(original_memo, warnings, obligation_packet)
    judge_dropped = _warning_payloads(warnings, "judge dropped_information:")
    return {
        "schema_id": "reader_memo_warning_repair_packet_v1",
        "final_source_list": _string_list(obligation_packet.get("required_sources")),
        "required_source_labels": _string_list(obligation_packet.get("required_source_labels")),
        "missing_number_contexts": number_contexts,
        "missing_source_label_contexts": source_label_contexts,
        "judge_dropped_information": judge_dropped,
        "unsupported_addition_warnings": _warning_payloads(warnings, "judge unsupported_additions:"),
        "dropped_obligations": _dropped_obligation_payloads(warnings),
        "suggested_insertions": _suggested_insertions(number_contexts, source_label_contexts, judge_dropped),
        "required_evidence": _compact_rows(obligation_packet.get("required_evidence"), limit=10),
        "required_gaps": _string_list(obligation_packet.get("required_gaps"))[:8],
    }


def _missing_number_contexts(original_memo: str, warnings: list[str], obligation_packet: dict[str, Any]) -> list[dict[str, str]]:
    required = set(_string_list(obligation_packet.get("required_numbers")))
    numbers = []
    for warning in warnings:
        prefix = "polish dropped required number:"
        text = str(warning).strip()
        if text.startswith(prefix):
            number = text.removeprefix(prefix).strip()
            if number in required:
                numbers.append(number)
    contexts = []
    for number in numbers[:12]:
        context = _local_context_for_token(original_memo, number)
        if context:
            contexts.append({"number": number, "original_context": context})
    return contexts


def _missing_source_label_contexts(original_memo: str, warnings: list[str], obligation_packet: dict[str, Any]) -> list[dict[str, str]]:
    required = set(_string_list(obligation_packet.get("required_source_labels")))
    labels = []
    for warning in warnings:
        prefix = "polish dropped required source label:"
        text = str(warning).strip()
        if text.startswith(prefix):
            label = text.removeprefix(prefix).strip()
            if label in required:
                labels.append(label)
    contexts = []
    for label in labels[:12]:
        context = _local_context_for_token(original_memo, label)
        if context:
            contexts.append({"source_label": label, "original_context": context})
    return contexts


def _suggested_insertions(
    number_contexts: list[dict[str, str]],
    source_label_contexts: list[dict[str, str]],
    judge_dropped: list[str],
) -> list[str]:
    insertions = [row["original_context"] for row in number_contexts if row.get("original_context")]
    insertions.extend(row["original_context"] for row in source_label_contexts if row.get("original_context"))
    insertions.extend(judge_dropped)
    return _dedupe([re.sub(r"\s+", " ", insertion).strip() for insertion in insertions])[:10]


def _local_context_for_token(text: str, token: str) -> str:
    index = text.find(token)
    if index < 0:
        return ""
    start = max(text.rfind("\n\n", 0, index), text.rfind(". ", 0, index))
    end_candidates = [pos for pos in (text.find("\n\n", index), text.find(". ", index + len(token))) if pos >= 0]
    start = 0 if start < 0 else start + (2 if text[start : start + 2] == ". " else 2)
    end = min(end_candidates) + 1 if end_candidates else min(len(text), index + 220)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _warning_payloads(warnings: list[str], prefix: str) -> list[str]:
    payloads = []
    for warning in warnings:
        text = str(warning).strip()
        if text.startswith(prefix):
            payloads.append(text.removeprefix(prefix).strip())
    return _dedupe(payloads)[:8]


def _dropped_obligation_payloads(warnings: list[str]) -> list[str]:
    prefixes = (
        "rewrite dropped required evidence:",
        "rewrite dropped required gap:",
        "polish dropped practical obligation:",
        "polish dropped answer-frame obligation:",
    )
    values = []
    for warning in warnings:
        text = str(warning).strip()
        for prefix in prefixes:
            if text.startswith(prefix):
                values.append(text.removeprefix(prefix).strip())
    return _dedupe(values)[:10]


def _compact_rows(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for row in value:
        if isinstance(row, dict):
            rows.append({key: row.get(key) for key in ("slot", "claim", "source", "anchor_terms") if row.get(key)})
        if len(rows) >= limit:
            break
    return rows


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def full_memo_markdown_payload_issue(raw: str) -> str:
    payload = _parse_json(raw)
    if isinstance(payload, dict) and isinstance(payload.get("memo_markdown"), str):
        return "rewrite returned legacy JSON payload instead of Markdown"
    if isinstance(payload, (dict, list)):
        return "rewrite returned JSON instead of Markdown"
    return ""


def _extract_polished_memo(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("## Decision Brief")
    return _clean_memo_text(cleaned[start:] if start > 0 else cleaned)


def _clean_memo_text(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    collapsed: list[str] = []
    blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and blank:
            continue
        collapsed.append(line)
        blank = is_blank
    return "\n".join(collapsed).strip() + "\n"
