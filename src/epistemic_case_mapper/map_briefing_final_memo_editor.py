from __future__ import annotations

import json
import re
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_final_edit_context import (
    COHERENCE_EDIT_TYPES,
    PROSE_EDIT_TYPES,
    model_facing_pass_edit_context,
)
from epistemic_case_mapper.map_briefing_final_memo_diagnosis import (
    build_memo_final_diagnosis,
    build_memo_protected_spans,
    diagnosis_improved,
)
from epistemic_case_mapper.map_briefing_full_memo_polish import (
    build_full_memo_polish_obligation_packet,
    build_full_memo_polish_prompt,
    restore_full_memo_protected_content,
)
from epistemic_case_mapper.map_briefing_rewrite_edits import NUMBER_RE, SOURCE_LABEL_RE
from epistemic_case_mapper.map_briefing_rewrite_edits import apply_reader_memo_edit_suggestions
from epistemic_case_mapper.map_briefing_warning_repair import (
    full_memo_markdown_payload_issue,
    run_full_memo_warning_repair,
)
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.synthesis_uplift_packet import _parse_json


RepairFn = Callable[[str, dict[str, Any], dict[str, Any]], str]
ValidateFn = Callable[[str, str, str, dict[str, Any], dict[str, Any], dict[str, Any]], list[str]]


def run_two_pass_reader_memo_editor(
    memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    contract: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    repair_candidate: RepairFn,
    validate_candidate: ValidateFn,
) -> dict[str, Any]:
    initial_diagnosis = build_memo_final_diagnosis(memo, contract)
    initial_protected = build_memo_protected_spans(memo, contract)
    if backend.strip() == "prompt":
        return _skipped_result(memo, initial_diagnosis, initial_protected)
    current = memo
    pass_reports: list[dict[str, Any]] = []
    prompts: dict[str, str] = {}
    raws: dict[str, str] = {}
    accepted_count = 0
    for pass_name, allowed_types in (
        ("coherence", COHERENCE_EDIT_TYPES),
        ("prose", PROSE_EDIT_TYPES),
    ):
        result = _run_one_pass(
            current,
            evidence_appendix,
            scaffold,
            candidate_map,
            contract,
            pass_name=pass_name,
            allowed_types=allowed_types,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            repair_candidate=repair_candidate,
            validate_candidate=validate_candidate,
        )
        prompts[pass_name] = str(result.get("prompt", ""))
        raws[pass_name] = str(result.get("raw", ""))
        pass_reports.append(result["report"])
        if result["report"].get("accepted"):
            accepted_count += 1
            current = str(result["memo"])
    final_diagnosis = build_memo_final_diagnosis(current, contract)
    report = _combined_report(
        contract=contract,
        pass_reports=pass_reports,
        initial_diagnosis=initial_diagnosis,
        final_diagnosis=final_diagnosis,
        accepted_count=accepted_count,
    )
    return {
        "memo": _clean_memo_text(current) if accepted_count else memo,
        "prompt": _combined_text(prompts),
        "raw": _combined_text(raws),
        "prompts": prompts,
        "raws": raws,
        "diagnosis": {"initial": initial_diagnosis, "final": final_diagnosis},
        "protected_spans": build_memo_protected_spans(current, contract),
        "report": report,
    }


def run_full_memo_polish_editor(
    memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    contract: dict[str, Any],
    *,
    backend: str, backend_timeout: int | None, backend_retries: int,
    repair_candidate: RepairFn,
    validate_candidate: ValidateFn,
    fallback_to_two_pass: bool = True, max_polish_attempts: int = 2,
) -> dict[str, Any]:
    """Rewrite the whole memo for readability, recording validation failures as warnings."""
    initial_diagnosis = build_memo_final_diagnosis(memo, contract)
    protected_spans = build_memo_protected_spans(memo, contract)
    if backend.strip() == "prompt":
        return _skipped_result(memo, initial_diagnosis, protected_spans)
    obligation_packet = build_full_memo_polish_obligation_packet(memo, scaffold, contract, protected_spans)
    current_issues: list[str] = []
    attempts: list[dict[str, Any]] = []
    prompts: dict[str, str] = {}
    raws: dict[str, str] = {}
    for attempt_index in range(max(1, max_polish_attempts)):
        generated = generate_full_memo_polish_candidate(
            memo,
            obligation_packet,
            current_issues=current_issues,
            attempt_index=attempt_index,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            repair_candidate=repair_candidate,
            scaffold=scaffold,
            contract=contract,
        )
        pass_name = generated["pass_name"]
        prompts[pass_name] = generated["prompt"]
        raws[pass_name] = generated["raw"]
        report = generated["report"]
        if not generated["accepted"]:
            attempts.append(report)
            break
        settled = evaluate_full_memo_polish_candidate(
            generated["candidate"],
            attempt_index=attempt_index,
            original_memo=memo,
            evidence_appendix=evidence_appendix,
            scaffold=scaffold,
            candidate_map=candidate_map,
            contract=contract,
            obligation_packet=obligation_packet,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            repair_candidate=repair_candidate,
            validate_candidate=validate_candidate,
        )
        prompts.update(settled.get("prompts", {}))
        raws.update(settled.get("raws", {}))
        candidate = str(settled["memo"])
        after_diagnosis = build_memo_final_diagnosis(candidate, contract)
        report.update(settled["report_update"])
        report["diagnosis_after"] = after_diagnosis
        report["diagnosis_improved"] = diagnosis_improved(initial_diagnosis, after_diagnosis, pass_name="all")
        report["word_count"] = len(candidate.split())
        attempts.append(report)
        return _accepted_full_polish_result(
            candidate,
            prompts=prompts,
            raws=raws,
            attempts=attempts,
            contract=contract,
            initial_diagnosis=initial_diagnosis,
            final_diagnosis=after_diagnosis,
            protected_spans=build_memo_protected_spans(candidate, contract),
            obligation_packet=obligation_packet,
        )
    if fallback_to_two_pass:
        return run_full_polish_two_pass_fallback(
            memo=memo,
            evidence_appendix=evidence_appendix,
            scaffold=scaffold,
            candidate_map=candidate_map,
            contract=contract,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            repair_candidate=repair_candidate,
            validate_candidate=validate_candidate,
            attempts=attempts,
            prompts=prompts,
            raws=raws,
        )
    return {
        "memo": memo,
        "prompt": _combined_text(prompts),
        "raw": _combined_text(raws),
        "prompts": prompts,
        "raws": raws,
        "diagnosis": {"initial": initial_diagnosis, "final": initial_diagnosis},
        "protected_spans": protected_spans,
        "report": {
            "schema_id": "reader_memo_rewrite_report_v3",
            "status": "full_polish_rejected_fallback",
            "accepted": False,
            "issues": [issue for attempt in attempts for issue in attempt.get("issues", [])],
            "pass_count": len(attempts),
            "accepted_pass_count": 0,
            "passes": attempts,
            "full_polish_attempts": attempts,
            "obligation_packet": obligation_packet,
        },
    }


def full_memo_polish_preservation_issues(
    polished: str,
    *,
    original_memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    contract: dict[str, Any],
    obligation_packet: dict[str, Any],
    validate_candidate: ValidateFn,
) -> list[str]:
    issues = validate_candidate(polished, original_memo, evidence_appendix, scaffold, candidate_map, contract)
    question = str(obligation_packet.get("question", "")).strip()
    if question and question not in polished:
        issues.append("polish dropped or changed the exact decision question")
    confidence = str(obligation_packet.get("confidence", "")).strip()
    if confidence and f"**Confidence:** {confidence}" not in polished:
        issues.append("polish dropped or changed the exact confidence line")
    for source in _string_list(obligation_packet.get("required_sources")):
        if source not in polished:
            issues.append(f"polish dropped required source: {source}")
    for number in _string_list(obligation_packet.get("required_numbers")):
        if number not in polished:
            issues.append(f"polish dropped required number: {number}")
    allowed_numbers = set(_string_list(obligation_packet.get("required_numbers"))) | set(_string_list(obligation_packet.get("optional_numbers")))
    introduced_numbers = sorted(_regex_tokens(polished, NUMBER_RE) - allowed_numbers)
    for number in introduced_numbers[:6]:
        issues.append(f"polish introduced unsupported number: {number}")
    for label in _string_list(obligation_packet.get("required_source_labels")):
        if label not in polished:
            issues.append(f"polish dropped required source label: {label}")
    for action in _string_list(obligation_packet.get("practical_actions")):
        if not _mentions_enough_content_terms(polished, action, minimum=2):
            issues.append(f"polish dropped practical obligation: {action[:100]}")
    answer_frame = obligation_packet.get("answer_frame", {}) if isinstance(obligation_packet.get("answer_frame"), dict) else {}
    for key in ("default_read", "primary_answer", "answer_stance"):
        value = str(answer_frame.get(key, "")).strip()
        if value and not _mentions_enough_content_terms(polished, value, minimum=2):
            issues.append(f"polish dropped answer-frame obligation: {value[:100]}")
    return _dedupe_issues(issues)


def evaluate_full_memo_polish_candidate(
    candidate: str,
    *,
    attempt_index: int,
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
) -> dict[str, Any]:
    deterministic_warnings = full_memo_polish_preservation_issues(
        candidate,
        original_memo=original_memo,
        evidence_appendix=evidence_appendix,
        scaffold=scaffold,
        candidate_map=candidate_map,
        contract=contract,
        obligation_packet=obligation_packet,
        validate_candidate=validate_candidate,
    )
    judge_result = run_full_memo_polish_judge(
        original_memo=original_memo,
        polished_memo=candidate,
        obligation_packet=obligation_packet,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    judge_warnings = full_memo_polish_judge_issues(judge_result.get("payload"))
    warnings = deterministic_warnings + judge_warnings
    repair_report: dict[str, Any] = {}
    prompts = {f"judge_attempt_{attempt_index + 1}": judge_result.get("prompt", "")}
    raws = {f"judge_attempt_{attempt_index + 1}": judge_result.get("raw", "")}
    if warnings:
        repair_result = run_full_memo_warning_repair(
            candidate,
            warnings,
            original_memo=original_memo,
            evidence_appendix=evidence_appendix,
            scaffold=scaffold,
            candidate_map=candidate_map,
            contract=contract,
            obligation_packet=obligation_packet,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            repair_candidate=repair_candidate,
            validate_candidate=validate_candidate,
            preservation_issues_fn=full_memo_polish_preservation_issues,
            judge_fn=run_full_memo_polish_judge,
            judge_issues_fn=full_memo_polish_judge_issues,
        )
        prompts[f"warning_repair_attempt_{attempt_index + 1}"] = repair_result.get("prompt", "")
        raws[f"warning_repair_attempt_{attempt_index + 1}"] = repair_result.get("raw", "")
        repair_report = repair_result.get("report", {})
        if repair_result.get("accepted"):
            candidate = str(repair_result.get("memo", candidate))
            deterministic_warnings = repair_report.get("deterministic_warnings", [])
            judge_warnings = repair_report.get("judge_warnings", [])
            warnings = deterministic_warnings + judge_warnings
    return {
        "memo": candidate,
        "prompts": prompts,
        "raws": raws,
        "report_update": {
            "status": "accepted" if not warnings else "accepted_with_warnings",
            "accepted": True,
            "issues": [],
            "warnings": warnings,
            "deterministic_warnings": deterministic_warnings,
            "judge_warnings": judge_warnings,
            "deterministic_issues": deterministic_warnings,
            "judge_issues": judge_warnings,
            "judge": judge_result.get("payload", {}),
            "patches": [],
            "warning_repair": repair_report,
        },
    }


def generate_full_memo_polish_candidate(
    memo: str,
    obligation_packet: dict[str, Any],
    *,
    current_issues: list[str],
    attempt_index: int,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    repair_candidate: RepairFn,
    scaffold: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    pass_name = f"full_polish_attempt_{attempt_index + 1}"
    prompt = build_full_memo_polish_prompt(memo, obligation_packet, previous_issues=current_issues)
    report: dict[str, Any] = {
        "schema_id": "reader_memo_full_polish_attempt_v1",
        "pass": pass_name,
        "accepted": False,
        "status": "not_run",
        "issues": [],
    }
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_fallback", "issues": [str(exc)]})
        return {"accepted": False, "pass_name": pass_name, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    if result.prompt_only:
        report.update({"status": "prompt_backend_fallback", "issues": ["rewrite backend returned prompt only"]})
        return {"accepted": False, "pass_name": pass_name, "prompt": prompt, "raw": raw, "report": report}
    parse_issue = full_memo_markdown_payload_issue(raw)
    if parse_issue:
        status = "legacy_json_payload_fallback" if "legacy" in parse_issue else "json_payload_fallback"
        report.update({"status": status, "issues": [parse_issue]})
        return {"accepted": False, "pass_name": pass_name, "prompt": prompt, "raw": raw, "report": report}
    candidate = repair_candidate(
        restore_full_memo_protected_content(_extract_polished_memo(raw), original_memo=memo, contract=contract),
        scaffold,
        contract,
    )
    candidate = restore_full_memo_protected_content(candidate, original_memo=memo, contract=contract)
    return {"accepted": True, "pass_name": pass_name, "prompt": prompt, "raw": raw, "report": report, "candidate": candidate}


def run_full_polish_two_pass_fallback(
    *,
    memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    contract: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    repair_candidate: RepairFn,
    validate_candidate: ValidateFn,
    attempts: list[dict[str, Any]],
    prompts: dict[str, str],
    raws: dict[str, str],
) -> dict[str, Any]:
    fallback = run_two_pass_reader_memo_editor(
        memo,
        evidence_appendix,
        scaffold,
        candidate_map,
        contract,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        repair_candidate=repair_candidate,
        validate_candidate=validate_candidate,
    )
    fallback_report = fallback.setdefault("report", {})
    fallback_report["full_polish_attempts"] = attempts
    fallback_report["full_polish_status"] = "fallback_to_two_pass"
    fallback["prompts"] = {**prompts, **(fallback.get("prompts", {}) if isinstance(fallback.get("prompts"), dict) else {})}
    fallback["raws"] = {**raws, **(fallback.get("raws", {}) if isinstance(fallback.get("raws"), dict) else {})}
    fallback["prompt"] = _combined_text(fallback["prompts"])
    fallback["raw"] = _combined_text(fallback["raws"])
    return fallback


def run_full_memo_polish_judge(
    *,
    original_memo: str,
    polished_memo: str,
    obligation_packet: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_full_memo_polish_judge_prompt(original_memo, polished_memo, obligation_packet)
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        return {"prompt": prompt, "raw": "", "payload": {"accepted": False, "issues": [str(exc)]}}
    payload = parse_full_memo_polish_judge_payload(result.text)
    if payload is None:
        payload = {"accepted": False, "issues": ["judge response was not valid JSON"]}
    return {"prompt": prompt, "raw": result.text, "payload": payload}


def build_full_memo_polish_judge_prompt(original_memo: str, polished_memo: str, obligation_packet: dict[str, Any]) -> str:
    return (
        "You are a strict preservation judge for a source-grounded decision memo rewrite.\n"
        "Compare the original memo and polished memo. Judge only preservation and unsupported additions, not style.\n\n"
        "Return only valid JSON with this schema:\n"
        "{\n"
        '  "accepted": true,\n'
        '  "dropped_information": ["..."],\n'
        '  "unsupported_additions": ["..."],\n'
        '  "changed_stance": false,\n'
        '  "limits_preserved": true,\n'
        '  "reason": "brief explanation"\n'
        "}\n\n"
        "Accept only if the polished memo preserves required obligations, keeps uncertainty/limits visible, and adds no new facts.\n"
        "Do not reject merely because optional_numbers from the obligation packet are omitted, unless the omission changes the stance or removes a required evidence item.\n\n"
        "Obligation packet:\n"
        f"{json.dumps(obligation_packet, indent=2, ensure_ascii=False)}\n\n"
        "Original memo:\n"
        f"{original_memo.strip()}\n\n"
        "Polished memo:\n"
        f"{polished_memo.strip()}\n"
    )


def parse_full_memo_polish_judge_payload(raw: str) -> dict[str, Any] | None:
    payload = _parse_json(raw)
    return payload if isinstance(payload, dict) else None


def full_memo_polish_judge_issues(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["judge response was not a JSON object"]
    issues: list[str] = []
    if payload.get("accepted") is not True:
        issues.append("judge did not accept polished memo")
    for key in ("dropped_information", "unsupported_additions"):
        values = payload.get(key, [])
        if isinstance(values, list):
            issues.extend(f"judge {key}: {str(value)[:160]}" for value in values if str(value).strip())
    if payload.get("changed_stance") is True:
        issues.append("judge found changed stance")
    if payload.get("limits_preserved") is False:
        issues.append("judge found limits were not preserved")
    return _dedupe_issues(issues)


def build_final_memo_edit_prompt(memo: str, edit_context: dict[str, Any]) -> str:
    pass_name = str(edit_context.get("pass", "prose"))
    if pass_name == "coherence":
        task = "Fix decision-support coherence: BLUF/body alignment, repeated caveats, emphasis balance, and section flow."
    else:
        task = (
            "Fix surface prose: transitions, sentence length, awkward phrasing, reader voice, raw diagnostic/status leakage, "
            "and dense paragraphs."
        )
    return (
        "You are a constrained final editor for a source-grounded decision memo.\n"
        f"Pass: {pass_name}\n"
        f"Task: {task}\n"
        "Do not rewrite the memo. Suggest only local exact replacements.\n"
        "Do not add facts, claims, sources, numbers, recommendations, or new caveats.\n"
        "Use only the supplied memo and final edit context.\n\n"
        "Return only valid JSON with this schema:\n"
        "{\n"
        '  "edits": [\n'
        '    {"target": "exact original text to replace", "replacement": "replacement text", "target_section": "section heading", "edit_type": "one allowed edit type", "reason": "brief reason"}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Each target must appear exactly once in the memo.\n"
        "- Keep edits local: one sentence, bullet, table cell, or short paragraph.\n"
        "- Use only allowed_edit_types from the context.\n"
        "- In the coherence pass, do not propose prose-only edit types. If diagnosis includes weak_opening_answer, the first edit should use edit_type `tighten_bluf` on the opening answer.\n"
        "- If the diagnosis flags raw diagnostics, replace machine-style status text with plain-language limits while preserving the gap.\n"
        "- If the diagnosis flags dense paragraphs, split or compress them locally without adding evidence.\n"
        "- Do not edit protected spans or text that contains protected spans.\n"
        "- Prefer 3-8 high-value edits; return {\"edits\": []} if no safe edit helps this pass.\n\n"
        "Final edit context:\n"
        f"{json.dumps(edit_context, indent=2, ensure_ascii=False)}\n\n"
        "Memo:\n"
        f"{memo.strip()}\n"
    )


def _run_one_pass(
    memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    contract: dict[str, Any],
    *,
    pass_name: str,
    allowed_types: set[str],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    repair_candidate: RepairFn,
    validate_candidate: ValidateFn,
) -> dict[str, Any]:
    before_diagnosis = build_memo_final_diagnosis(memo, contract)
    protected_spans = build_memo_protected_spans(memo, contract)
    edit_context = model_facing_pass_edit_context(
        contract=contract,
        diagnosis=before_diagnosis,
        protected_spans=protected_spans,
        pass_name=pass_name,
    )
    prompt = build_final_memo_edit_prompt(memo, edit_context)
    report: dict[str, Any] = {
        "schema_id": "reader_memo_edit_pass_report_v1",
        "pass": pass_name,
        "status": "not_run",
        "accepted": False,
        "issues": [],
        "diagnosis_before": before_diagnosis,
        "protected_span_count": protected_spans.get("span_count", 0),
    }
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_fallback", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    if result.prompt_only:
        report.update({"status": "prompt_backend_fallback", "issues": ["rewrite backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    payload = parse_reader_memo_edit_payload(raw)
    if not isinstance(payload, dict):
        report.update({"status": "parse_failed_fallback", "issues": ["rewrite response was not a JSON object"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    edit_result = apply_reader_memo_edit_suggestions(
        memo,
        payload,
        protected_spans=protected_spans,
        max_edits=12,
        allowed_edit_types=allowed_types,
        pass_name=pass_name,
    )
    report["raw_edit_count"] = edit_result["raw_edit_count"]
    report["applied_edit_count"] = len(edit_result["applied_edits"])
    report["applied_edits"] = edit_result["applied_edits"]
    report["skipped_edits"] = edit_result["skipped_edits"]
    report["changed_char_count"] = edit_result["changed_char_count"]
    if not edit_result["applied_edits"]:
        report.update({"status": "no_safe_edits_fallback", "issues": edit_result["issues"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    edited = str(edit_result["memo"])
    repaired = repair_candidate(edited, scaffold, contract)
    candidate = repaired if repaired != edited else edited
    validation_issues = validate_candidate(candidate, memo, evidence_appendix, scaffold, candidate_map, contract)
    after_diagnosis = build_memo_final_diagnosis(candidate, contract)
    report["diagnosis_after"] = after_diagnosis
    report["diagnosis_improved"] = diagnosis_improved(before_diagnosis, after_diagnosis, pass_name=pass_name)
    if repaired != edited:
        report["repaired_word_count"] = len(repaired.split())
    if validation_issues:
        report.update({"status": "rejected_fallback", "issues": validation_issues})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    if not report["diagnosis_improved"]:
        report.update({"status": "no_metric_improvement_fallback", "issues": ["pass did not improve deterministic final-memo diagnosis"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    report.update({"status": "accepted_after_repair" if repaired != edited else "accepted", "accepted": True, "issues": []})
    return {"memo": _clean_memo_text(candidate), "prompt": prompt, "raw": raw, "report": report}


def parse_reader_memo_edit_payload(raw: str) -> dict[str, Any] | None:
    payload = _parse_json(raw)
    if isinstance(payload, dict) and isinstance(payload.get("edits"), list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("memo_markdown"), str):
        return {"edits": [{"target": "", "replacement": "", "reason": "legacy full rewrite payload rejected"}]}
    match = re.search(r'"memo_markdown"\s*:\s*"(?P<value>.*)"\s*}\s*(?:```)?\s*$', raw.strip(), flags=re.DOTALL)
    if not match:
        return None
    return {"edits": [{"target": "", "replacement": "", "reason": "legacy full rewrite payload rejected"}]}


def _combined_report(
    *,
    contract: dict[str, Any],
    pass_reports: list[dict[str, Any]],
    initial_diagnosis: dict[str, Any],
    final_diagnosis: dict[str, Any],
    accepted_count: int,
) -> dict[str, Any]:
    raw_edit_count = sum(int(report.get("raw_edit_count", 0) or 0) for report in pass_reports)
    applied_edits = [
        edit
        for report in pass_reports
        if report.get("accepted")
        for edit in report.get("applied_edits", [])
        if isinstance(edit, dict)
    ]
    skipped_edits = [edit for report in pass_reports for edit in report.get("skipped_edits", []) if isinstance(edit, dict)]
    status = "accepted" if accepted_count else "no_safe_edits_fallback"
    if accepted_count and any(report.get("status") == "accepted_after_repair" for report in pass_reports):
        status = "accepted_after_repair"
    return {
        "schema_id": "reader_memo_rewrite_report_v2",
        "status": status,
        "accepted": bool(accepted_count),
        "issues": [issue for report in pass_reports for issue in report.get("issues", []) if isinstance(issue, str)],
        "contract": {
            "schema_id": contract.get("schema_id"),
            "confidence": contract.get("confidence"),
        },
        "pass_count": len(pass_reports),
        "accepted_pass_count": accepted_count,
        "passes": pass_reports,
        "raw_edit_count": raw_edit_count,
        "applied_edit_count": len(applied_edits),
        "applied_edits": applied_edits,
        "skipped_edits": skipped_edits,
        "diagnosis_initial": initial_diagnosis,
        "diagnosis_final": final_diagnosis,
        "diagnosis_improved": diagnosis_improved(initial_diagnosis, final_diagnosis, pass_name="all"),
    }


def _skipped_result(memo: str, diagnosis: dict[str, Any], protected_spans: dict[str, Any]) -> dict[str, Any]:
    return {
        "memo": memo,
        "prompt": "",
        "raw": "",
        "prompts": {},
        "raws": {},
        "diagnosis": {"initial": diagnosis, "final": diagnosis},
        "protected_spans": protected_spans,
        "report": {
            "schema_id": "reader_memo_rewrite_report_v2",
            "status": "skipped_prompt_backend",
            "accepted": False,
            "issues": [],
            "pass_count": 0,
            "accepted_pass_count": 0,
        },
    }


def _accepted_full_polish_result(
    memo: str,
    *,
    prompts: dict[str, str],
    raws: dict[str, str],
    attempts: list[dict[str, Any]],
    contract: dict[str, Any],
    initial_diagnosis: dict[str, Any],
    final_diagnosis: dict[str, Any],
    protected_spans: dict[str, Any],
    obligation_packet: dict[str, Any],
) -> dict[str, Any]:
    warnings = _full_polish_attempt_warnings(attempts)
    status = "full_polish_accepted_with_warnings" if warnings else "full_polish_accepted"
    full_polish_status = "accepted_with_warnings" if warnings else "accepted"
    return {
        "memo": _clean_memo_text(memo),
        "prompt": _combined_text(prompts),
        "raw": _combined_text(raws),
        "prompts": prompts,
        "raws": raws,
        "diagnosis": {"initial": initial_diagnosis, "final": final_diagnosis},
        "protected_spans": protected_spans,
        "report": {
            "schema_id": "reader_memo_rewrite_report_v3",
            "status": status,
            "accepted": True,
            "issues": [],
            "warnings": warnings,
            "contract": {
                "schema_id": contract.get("schema_id"),
                "confidence": contract.get("confidence"),
            },
            "pass_count": len(attempts),
            "accepted_pass_count": 1,
            "passes": attempts,
            "full_polish_attempts": attempts,
            "full_polish_status": full_polish_status,
            "obligation_packet": obligation_packet,
            "diagnosis_initial": initial_diagnosis,
            "diagnosis_final": final_diagnosis,
            "diagnosis_improved": diagnosis_improved(initial_diagnosis, final_diagnosis, pass_name="all"),
        },
    }


def _full_polish_attempt_warnings(attempts: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for attempt in attempts:
        for warning in attempt.get("warnings", []) if isinstance(attempt.get("warnings"), list) else []:
            text = str(warning).strip()
            if text and text not in warnings:
                warnings.append(text)
    return warnings


def _combined_text(parts: dict[str, str]) -> str:
    blocks = []
    for key, value in parts.items():
        if value.strip():
            blocks.append(f"--- {key} ---\n{value.strip()}")
    return "\n\n".join(blocks)


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


def _extract_polished_memo(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("## Decision Brief")
    if start > 0:
        cleaned = cleaned[start:]
    return _clean_memo_text(cleaned)


def _regex_tokens(text: str, pattern: re.Pattern[str]) -> set[str]:
    tokens: set[str] = set()
    for match in pattern.findall(text):
        if isinstance(match, tuple):
            value = " ".join(str(part) for part in match if str(part).strip())
        else:
            value = str(match)
        value = value.strip()
        if value:
            tokens.add(value)
    return tokens


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _mentions_enough_content_terms(text: str, obligation: str, *, minimum: int) -> bool:
    terms = _content_terms(obligation)
    if not terms:
        return True
    lowered = text.lower()
    required = min(minimum, len(terms))
    return sum(1 for term in terms if term in lowered) >= required


def _content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "after",
        "again",
        "also",
        "because",
        "before",
        "between",
        "could",
        "current",
        "decision",
        "does",
        "from",
        "have",
        "into",
        "more",
        "should",
        "source",
        "that",
        "their",
        "there",
        "this",
        "those",
        "under",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
    }
    terms = []
    for term in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower()):
        if term not in stop and term not in terms:
            terms.append(term)
    return terms


def _dedupe_issues(issues: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        text = str(issue).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped
