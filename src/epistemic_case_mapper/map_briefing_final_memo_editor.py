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
from epistemic_case_mapper.map_briefing_rewrite_edits import apply_reader_memo_edit_suggestions
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


def build_final_memo_edit_prompt(memo: str, edit_context: dict[str, Any]) -> str:
    pass_name = str(edit_context.get("pass", "prose"))
    if pass_name == "coherence":
        task = "Fix decision-support coherence: BLUF/body alignment, repeated caveats, emphasis balance, and section flow."
    else:
        task = "Fix surface prose: transitions, sentence length, awkward phrasing, and reader voice."
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
