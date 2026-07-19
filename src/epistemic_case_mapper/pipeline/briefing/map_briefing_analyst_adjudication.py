from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_schemas import (
    AnalystAdjudication,
    EvidenceAdjudicationRow,
    build_analyst_adjudication_parse_report,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.model_stage_retry import model_stage_attempts
from epistemic_case_mapper.model_backends import model_parallelism, run_model_backend, run_parallel
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_faithfulness import repair_adjudication_source_faithfulness

DEFAULT_CHUNK_SIZE = 8


def run_analyst_adjudication(
    ledger: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    schema_version = os.environ.get("ECM_ANALYST_ADJUDICATION_SCHEMA", "v1").strip().lower()
    if schema_version not in {"v1", "v2"}:
        raise ValueError("ECM_ANALYST_ADJUDICATION_SCHEMA must be v1 or v2")
    if schema_version == "v2":
        from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2 import (
            run_analyst_adjudication_v2,
        )

        return run_analyst_adjudication_v2(
            ledger,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            chunk_size=_chunk_size(),
            scaffold_builder=deterministic_adjudication_scaffold,
            progress=progress,
        )
    prompt = build_analyst_adjudication_prompt(ledger)
    scaffold = deterministic_adjudication_scaffold(ledger)
    if backend.strip() == "prompt":
        scaffold, repair_report = repair_adjudication_source_faithfulness(ledger, scaffold)
        parse_report = build_analyst_adjudication_parse_report(scaffold, ledger)
        report = _report("prompt_backend_scaffold", parse_report)
        report["source_faithfulness_repair"] = repair_report
        return {
            "analyst_adjudication": scaffold,
            "analyst_adjudication_prompt": prompt,
            "analyst_adjudication_raw": "",
            "analyst_adjudication_parse_report": parse_report,
            "analyst_adjudication_chunk_reports": _chunk_report_bundle(
                [_chunk_report(1, 1, "prompt_backend_scaffold", parse_report)],
                scaffold_chunk_count=1,
            ),
            "analyst_source_faithfulness_repair_report": repair_report,
            "analyst_adjudication_report": report,
        }
    return _run_live_adjudication(
        ledger,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        progress=progress,
    )


def _run_live_adjudication(
    ledger: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
) -> dict[str, Any]:
    stage_started = time.monotonic()
    ledger_rows = [row for row in _list(ledger.get("rows")) if isinstance(row, dict)]
    all_ids = [str(row.get("evidence_item_id")) for row in ledger_rows if str(row.get("evidence_item_id") or "")]
    chunks = _chunks(ledger_rows, _chunk_size())
    _emit_progress(
        progress,
        "analyst_adjudication_chunks",
        "started",
        {
            "chunk_count": len(chunks),
            "row_count": len(ledger_rows),
            "chunk_size": _chunk_size(),
            "parallelism": model_parallelism(backend),
        },
    )
    chunk_results = run_parallel(
        list(enumerate(chunks, start=1)),
        lambda item: _run_adjudication_chunk(
            item,
            ledger=ledger,
            total=len(chunks),
            all_ids=all_ids,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            progress=progress,
            phase="initial",
        ),
        max_workers=model_parallelism(backend),
    )
    _emit_progress(
        progress,
        "analyst_adjudication_chunks",
        "completed",
        {
            "chunk_count": len(chunks),
            "failed_chunk_count": sum(1 for row in chunk_results if row.get("chunk_failed")),
            "wall_seconds": round(time.monotonic() - stage_started, 3),
        },
    )
    prompts = [str(row.get("prompt") or "") for row in chunk_results]
    raws = [str(row.get("raw_block") or "") for row in chunk_results]
    merged_rows = [
        merged_row
        for row in chunk_results
        for merged_row in _list(row.get("rows"))
        if isinstance(merged_row, dict)
    ]
    chunk_reports = [
        row.get("chunk_report")
        for row in chunk_results
        if isinstance(row.get("chunk_report"), dict)
    ]
    initial_failed_chunk_count = sum(1 for row in chunk_results if row.get("chunk_failed"))
    merged = {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": ledger.get("decision_question", ""),
        "rows": _order_rows_by_ledger(_dedupe_adjudication_rows(merged_rows), all_ids),
        "overall_rationale": _merged_rationale(chunk_reports),
    }
    parse_report = build_analyst_adjudication_parse_report(merged, ledger)
    recovery_results: list[dict[str, Any]] = []
    recovery_rounds = 0
    max_recovery_rounds = model_stage_attempts()
    while (
        recovery_rounds < max_recovery_rounds
        and not parse_report.get("valid")
        and merged_rows
        and parse_report.get("missing_evidence_item_ids")
    ):
        missing_ids = _string_list(parse_report.get("missing_evidence_item_ids"))
        round_results = _run_missing_adjudication_chunks(
            ledger,
            missing_ids=missing_ids,
            start_index=len(chunks) + len(recovery_results) + 1,
            all_ids=all_ids,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            progress=progress,
            recovery_round=recovery_rounds + 1,
        )
        recovery_rounds += 1
        recovery_results.extend(round_results)
        prompts.extend(str(row.get("prompt") or "") for row in round_results)
        raws.extend(str(row.get("raw_block") or "") for row in round_results)
        merged_rows.extend(
            merged_row
            for row in round_results
            for merged_row in _list(row.get("rows"))
            if isinstance(merged_row, dict)
        )
        chunk_reports.extend(
            row.get("chunk_report")
            for row in round_results
            if isinstance(row.get("chunk_report"), dict)
        )
        merged["rows"] = _order_rows_by_ledger(_dedupe_adjudication_rows(merged_rows), all_ids)
        merged["overall_rationale"] = _merged_rationale(chunk_reports)
        parse_report = build_analyst_adjudication_parse_report(merged, ledger)
    failed_chunk_count = sum(1 for row in [*chunk_results, *recovery_results] if row.get("chunk_failed"))
    merged, repair_report = repair_adjudication_source_faithfulness(ledger, merged)
    parse_report = build_analyst_adjudication_parse_report(merged, ledger)
    report = _live_adjudication_report(
        parse_report,
        recovered_missing_rows=bool(recovery_results) and parse_report.get("valid"),
        failed_chunk_count=failed_chunk_count,
    )
    report["source_faithfulness_repair"] = repair_report
    chunk_bundle = _live_adjudication_chunk_bundle(
        chunks=chunks,
        recovery_results=recovery_results,
        chunk_reports=chunk_reports,
        failed_chunk_count=failed_chunk_count,
        initial_failed_chunk_count=initial_failed_chunk_count,
        recovery_rounds=recovery_rounds,
        backend=backend,
    )
    return _live_adjudication_result(
        merged=merged,
        prompts=prompts,
        raws=raws,
        parse_report=parse_report,
        chunk_bundle=chunk_bundle,
        repair_report=repair_report,
        report=report,
    )


def _live_adjudication_report(
    parse_report: dict[str, Any],
    *,
    recovered_missing_rows: bool,
    failed_chunk_count: int,
) -> dict[str, Any]:
    status = (
        "accepted_after_missing_row_repair"
        if recovered_missing_rows
        else "accepted"
        if parse_report.get("valid") and failed_chunk_count == 0
        else "accepted_with_chunk_warnings"
        if parse_report.get("valid")
        else "model_output_invalid"
    )
    return _report(
        status,
        parse_report,
        issues=["one_or_more_chunks_failed_without_fallback"] if failed_chunk_count else [],
    )


def _live_adjudication_chunk_bundle(
    *,
    chunks: list[list[dict[str, Any]]],
    recovery_results: list[dict[str, Any]],
    chunk_reports: list[dict[str, Any]],
    failed_chunk_count: int,
    initial_failed_chunk_count: int,
    recovery_rounds: int,
    backend: str,
) -> dict[str, Any]:
    return {
        "schema_id": "analyst_adjudication_chunk_reports_v1",
        "chunk_count": len(chunks) + len(recovery_results),
        "scaffold_chunk_count": 0,
        "failed_chunk_count": failed_chunk_count,
        "initial_failed_chunk_count": initial_failed_chunk_count,
        "missing_row_repair_chunk_count": len(recovery_results),
        "missing_row_repair_round_count": recovery_rounds,
        "parallelism": model_parallelism(backend),
        "chunks": chunk_reports,
    }


def _live_adjudication_result(
    *,
    merged: dict[str, Any],
    prompts: list[str],
    raws: list[str],
    parse_report: dict[str, Any],
    chunk_bundle: dict[str, Any],
    repair_report: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "analyst_adjudication": merged,
        "analyst_adjudication_prompt": "\n\n".join(prompts),
        "analyst_adjudication_raw": "\n\n".join(raws),
        "analyst_adjudication_parse_report": parse_report,
        "analyst_adjudication_chunk_reports": chunk_bundle,
        "analyst_source_faithfulness_repair_report": repair_report,
        "analyst_adjudication_report": report,
    }


def _run_missing_adjudication_chunks(
    ledger: dict[str, Any],
    *,
    missing_ids: list[str],
    start_index: int,
    all_ids: list[str],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    recovery_round: int,
) -> list[dict[str, Any]]:
    rows_by_id = {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    missing_rows = [rows_by_id[evidence_id] for evidence_id in missing_ids if evidence_id in rows_by_id]
    chunks = _chunks(missing_rows, _chunk_size())
    if not chunks:
        return []
    total = start_index + len(chunks) - 1
    _emit_progress(
        progress,
        "analyst_adjudication_missing_row_repair",
        "started",
        {
            "recovery_round": recovery_round,
            "missing_row_count": len(missing_rows),
            "chunk_count": len(chunks),
            "start_index": start_index,
            "total": total,
        },
    )
    started = time.monotonic()
    results = run_parallel(
        list(enumerate(chunks, start=start_index)),
        lambda item: _run_adjudication_chunk(
            item,
            ledger=ledger,
            total=total,
            all_ids=all_ids,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            progress=progress,
            phase="missing_row_repair",
        ),
        max_workers=model_parallelism(backend),
    )
    _emit_progress(
        progress,
        "analyst_adjudication_missing_row_repair",
        "completed",
        {
            "recovery_round": recovery_round,
            "chunk_count": len(chunks),
            "failed_chunk_count": sum(1 for row in results if row.get("chunk_failed")),
            "wall_seconds": round(time.monotonic() - started, 3),
        },
    )
    return results


def _run_adjudication_chunk(
    item: tuple[int, list[dict[str, Any]]],
    *,
    ledger: dict[str, Any],
    total: int,
    all_ids: list[str],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    phase: str,
) -> dict[str, Any]:
    started = time.monotonic()
    index, rows = item
    chunk_ledger = _chunk_ledger(ledger, rows, index=index, total=total)
    chunk_prompt = (
        build_missing_row_adjudication_prompt(chunk_ledger)
        if phase == "missing_row_repair"
        else build_analyst_adjudication_prompt(chunk_ledger)
    )
    prompt_block = f"<!-- analyst adjudication chunk {index}/{total} -->\n{chunk_prompt}"
    expected_ids = [str(row.get("evidence_item_id")) for row in rows if str(row.get("evidence_item_id") or "")]
    attempts = model_stage_attempts()
    retry_reports: list[dict[str, Any]] = []
    raw = ""
    payload: Any = {}
    parse_report: dict[str, Any] = {}
    _emit_progress(
        progress,
        "analyst_adjudication_chunk",
        "started",
        _chunk_progress_details(index, total, rows, phase, prompt_chars=len(chunk_prompt), attempt=1),
    )
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            _emit_progress(
                progress,
                "analyst_adjudication_chunk",
                "retry_started",
                _chunk_progress_details(index, total, rows, phase, prompt_chars=len(chunk_prompt), attempt=attempt),
            )
        try:
            result = run_model_backend(chunk_prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
            raw = result.text
        except RuntimeError as exc:
            parse_report = build_analyst_adjudication_parse_report({}, chunk_ledger)
            retry_reports.append(_retry_report(attempt, "backend_error", parse_report, str(exc)))
            if attempt < attempts:
                _emit_chunk_retry_needed(
                    progress,
                    index=index,
                    total=total,
                    rows=rows,
                    phase=phase,
                    prompt_chars=len(chunk_prompt),
                    raw_chars=0,
                    attempt=attempt,
                    status="backend_error",
                    started=started,
                )
                continue
            return _backend_error_chunk_result(
                exc,
                index=index,
                total=total,
                rows=rows,
                phase=phase,
                prompt_block=prompt_block,
                prompt_chars=len(chunk_prompt),
                attempts=attempts,
                parse_report=parse_report,
                retry_reports=retry_reports,
                progress=progress,
                started=started,
            )
        payload = _repair_covered_by_aliases(_extract_json(raw), all_ids)
        parse_report = build_analyst_adjudication_parse_report(
            payload,
            chunk_ledger,
            expected_evidence_item_ids=expected_ids,
            known_evidence_item_ids=all_ids,
        )
        retry_reports.append(_retry_report(attempt, "accepted" if parse_report.get("valid") else "invalid", parse_report))
        if parse_report.get("valid"):
            parsed = AnalystAdjudication.model_validate(payload).model_dump()
            return _accepted_chunk_result(
                parsed,
                raw=raw,
                index=index,
                total=total,
                rows=rows,
                phase=phase,
                prompt_block=prompt_block,
                prompt_chars=len(chunk_prompt),
                attempt=attempt,
                parse_report=parse_report,
                retry_reports=retry_reports,
                progress=progress,
                started=started,
            )
        if attempt < attempts:
            _emit_chunk_retry_needed(
                progress,
                index=index,
                total=total,
                rows=rows,
                phase=phase,
                prompt_chars=len(chunk_prompt),
                raw_chars=len(raw),
                attempt=attempt,
                status="invalid",
                started=started,
                issue_count=len(_list(parse_report.get("issues"))),
            )
            continue
    return _salvage_or_failed_chunk_result(
        payload,
        chunk_ledger=chunk_ledger,
        expected_ids=expected_ids,
        all_ids=all_ids,
        raw=raw,
        index=index,
        total=total,
        rows=rows,
        phase=phase,
        prompt_block=prompt_block,
        prompt_chars=len(chunk_prompt),
        attempts=attempts,
        parse_report=parse_report,
        retry_reports=retry_reports,
        progress=progress,
        started=started,
    )


def _emit_chunk_retry_needed(
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    *,
    index: int,
    total: int,
    rows: list[dict[str, Any]],
    phase: str,
    prompt_chars: int,
    raw_chars: int,
    attempt: int,
    status: str,
    started: float,
    issue_count: int | None = None,
) -> None:
    details = _chunk_progress_details(
        index,
        total,
        rows,
        phase,
        prompt_chars=prompt_chars,
        raw_chars=raw_chars,
        attempt=attempt,
        status=status,
        wall_seconds=round(time.monotonic() - started, 3),
    )
    if issue_count is not None:
        details["issue_count"] = issue_count
    _emit_progress(progress, "analyst_adjudication_chunk", "retry_needed", details)


def _backend_error_chunk_result(
    exc: RuntimeError,
    *,
    index: int,
    total: int,
    rows: list[dict[str, Any]],
    phase: str,
    prompt_block: str,
    prompt_chars: int,
    attempts: int,
    parse_report: dict[str, Any],
    retry_reports: list[dict[str, Any]],
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    started: float,
) -> dict[str, Any]:
    _emit_progress(
        progress,
        "analyst_adjudication_chunk",
        "failed",
        _chunk_progress_details(
            index,
            total,
            rows,
            phase,
            prompt_chars=prompt_chars,
            raw_chars=0,
            attempt=attempts,
            status="backend_error",
            wall_seconds=round(time.monotonic() - started, 3),
        ),
    )
    return {
        "prompt": prompt_block,
        "raw_block": f"<!-- chunk {index} backend error after {attempts} attempt(s): {exc} -->",
        "rows": [],
        "chunk_failed": True,
        "chunk_report": _with_retry_report(
            _chunk_report(index, total, "backend_error", parse_report, issues=[str(exc)]),
            retry_reports,
        ),
    }


def _accepted_chunk_result(
    parsed: dict[str, Any],
    *,
    raw: str,
    index: int,
    total: int,
    rows: list[dict[str, Any]],
    phase: str,
    prompt_block: str,
    prompt_chars: int,
    attempt: int,
    parse_report: dict[str, Any],
    retry_reports: list[dict[str, Any]],
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    started: float,
) -> dict[str, Any]:
    _emit_progress(
        progress,
        "analyst_adjudication_chunk",
        "completed",
        _chunk_progress_details(
            index,
            total,
            rows,
            phase,
            prompt_chars=prompt_chars,
            raw_chars=len(raw),
            attempt=attempt,
            status="accepted",
            wall_seconds=round(time.monotonic() - started, 3),
            parsed_row_count=len(parsed.get("rows", [])),
        ),
    )
    return {
        "prompt": prompt_block,
        "raw_block": f"<!-- analyst adjudication chunk {index}/{total} -->\n{raw}",
        "rows": parsed.get("rows", []),
        "used_scaffold": False,
        "chunk_report": _with_retry_report(_chunk_report(index, total, "accepted", parse_report), retry_reports),
    }


def _salvage_or_failed_chunk_result(
    payload: Any,
    *,
    chunk_ledger: dict[str, Any],
    expected_ids: list[str],
    all_ids: list[str],
    raw: str,
    index: int,
    total: int,
    rows: list[dict[str, Any]],
    phase: str,
    prompt_block: str,
    prompt_chars: int,
    attempts: int,
    parse_report: dict[str, Any],
    retry_reports: list[dict[str, Any]],
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    started: float,
) -> dict[str, Any]:
    salvaged_rows, salvage_report = _salvage_adjudication_chunk_rows(
        payload,
        chunk_ledger=chunk_ledger,
        expected_ids=expected_ids,
        all_ids=all_ids,
    )
    if salvage_report["salvaged_model_row_count"]:
        chunk_parse_report = build_analyst_adjudication_parse_report(
            {
                "schema_id": "analyst_adjudication_v1",
                "decision_question": chunk_ledger.get("decision_question", ""),
                "rows": salvaged_rows,
                "overall_rationale": "Invalid chunk payload was salvaged row by row; missing or invalid rows were not replaced.",
            },
            chunk_ledger,
            expected_evidence_item_ids=expected_ids,
            known_evidence_item_ids=all_ids,
        )
        report = _chunk_report(
            index,
            total,
            "model_output_invalid_salvaged_model_rows",
            chunk_parse_report,
            issues=["chunk failed whole-payload validation; valid model rows were salvaged"],
        )
        report.update(salvage_report)
        report["original_parse_report"] = parse_report
        report = _with_retry_report(report, retry_reports)
        _emit_progress(
            progress,
            "analyst_adjudication_chunk",
            "completed",
            _chunk_progress_details(
                index,
                total,
                rows,
                phase,
                prompt_chars=prompt_chars,
                raw_chars=len(raw),
                attempt=attempts,
                status="salvaged" if chunk_parse_report.get("valid") else "salvaged_with_warnings",
                wall_seconds=round(time.monotonic() - started, 3),
                parsed_row_count=len(salvaged_rows),
            ),
        )
        return {
            "prompt": prompt_block,
            "raw_block": f"<!-- analyst adjudication chunk {index}/{total} -->\n{raw}",
            "rows": salvaged_rows,
            "chunk_failed": not chunk_parse_report.get("valid"),
            "chunk_report": report,
        }
    _emit_progress(
        progress,
        "analyst_adjudication_chunk",
        "failed",
        _chunk_progress_details(
            index,
            total,
            rows,
            phase,
            prompt_chars=prompt_chars,
            raw_chars=len(raw),
            attempt=attempts,
            status="model_output_invalid",
            wall_seconds=round(time.monotonic() - started, 3),
            issue_count=len(_list(parse_report.get("issues"))),
        ),
    )
    return {
        "prompt": prompt_block,
        "raw_block": f"<!-- analyst adjudication chunk {index}/{total} -->\n{raw}",
        "rows": [],
        "chunk_failed": True,
        "chunk_report": _with_retry_report(
            _chunk_report(
                index,
                total,
                "model_output_invalid",
                parse_report,
                issues=["chunk failed schema or ledger accounting checks"],
            ),
            retry_reports,
        ),
    }


def _salvage_adjudication_chunk_rows(
    payload: Any,
    *,
    chunk_ledger: dict[str, Any],
    expected_ids: list[str],
    all_ids: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scaffold_by_id: dict[str, dict[str, Any]] = {}
    accepted: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    known_ids = set(all_ids) | set(expected_ids)
    for index, row in enumerate(_list(payload.get("rows") if isinstance(payload, dict) else None)):
        if not isinstance(row, dict):
            rejected.append({"row_index": index, "reason": "row_not_object"})
            continue
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        if not evidence_id:
            rejected.append({"row_index": index, "reason": "missing_evidence_item_id"})
            continue
        if evidence_id not in expected_ids:
            rejected.append({"row_index": index, "evidence_item_id": evidence_id, "reason": "unexpected_evidence_item_id"})
            continue
        if evidence_id in accepted:
            rejected.append({"row_index": index, "evidence_item_id": evidence_id, "reason": "duplicate_evidence_item_id"})
            continue
        candidate = _adjudication_row_candidate(row, scaffold_by_id.get(evidence_id, {}), known_ids=known_ids)
        try:
            accepted[evidence_id] = EvidenceAdjudicationRow.model_validate(candidate).model_dump()
        except ValueError as exc:
            rejected.append({"row_index": index, "evidence_item_id": evidence_id, "reason": type(exc).__name__})
    ordered = [accepted[row_id] for row_id in expected_ids if row_id in accepted]
    scaffolded = [row_id for row_id in expected_ids if row_id not in accepted]
    return ordered, {
        "salvaged_model_row_count": len(accepted),
        "missing_unsalvaged_row_count": len(scaffolded),
        "invalid_model_row_count": len(rejected),
        "missing_unsalvaged_evidence_item_ids": scaffolded,
        "invalid_model_rows": rejected[:20],
    }


def _adjudication_row_candidate(row: dict[str, Any], scaffold: dict[str, Any], *, known_ids: set[str]) -> dict[str, Any]:
    allowed_keys = {
        "evidence_item_id",
        "memo_use",
        "importance_rank",
        "rationale",
        "answer_relation",
        "covered_by",
        "source_ids",
        "quantity_values",
        "target_answer_option",
        "effect_on_final_answer",
        "tension_type",
        "downgrade_reason",
        "decision_contribution",
        "use_in_reasoning",
        "key_qualifier",
        "quantity_takeaway",
        "source_weight_note",
        "misuse_warning",
        "if_omitted",
    }
    candidate = {key: scaffold.get(key) for key in allowed_keys if key in scaffold}
    candidate.update({key: row.get(key) for key in allowed_keys if key in row})
    candidate["covered_by"] = [target for target in _string_list(candidate.get("covered_by")) if target in known_ids]
    return candidate


def run_analyst_adjudication_single_call_for_test(
    ledger: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_analyst_adjudication_prompt(ledger)
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        parse_report = build_analyst_adjudication_parse_report({}, ledger)
        invalid = _invalid_adjudication(ledger)
        return {
            "analyst_adjudication": invalid,
            "analyst_adjudication_prompt": prompt,
            "analyst_adjudication_raw": "",
            "analyst_adjudication_parse_report": parse_report,
            "analyst_adjudication_chunk_reports": _chunk_report_bundle(
                [_chunk_report(1, 1, "backend_error", parse_report, issues=[str(exc)])],
                scaffold_chunk_count=0,
            ),
            "analyst_adjudication_report": _report("backend_error", parse_report, issues=[str(exc)]),
        }
    raw = result.text
    payload = _repair_covered_by_aliases(_extract_json(raw), _ledger_ids(ledger))
    parse_report = build_analyst_adjudication_parse_report(payload, ledger)
    if not parse_report.get("valid"):
        return {
            "analyst_adjudication": payload if isinstance(payload, dict) else _invalid_adjudication(ledger),
            "analyst_adjudication_prompt": prompt,
            "analyst_adjudication_raw": raw,
            "analyst_adjudication_parse_report": parse_report,
            "analyst_adjudication_chunk_reports": _chunk_report_bundle(
                [_chunk_report(1, 1, "model_output_invalid", parse_report)],
                scaffold_chunk_count=0,
            ),
            "analyst_adjudication_report": _report(
                "model_output_invalid",
                parse_report,
                issues=["model adjudication failed schema or ledger accounting checks"],
            ),
        }
    parsed = AnalystAdjudication.model_validate(payload).model_dump()
    parsed, repair_report = repair_adjudication_source_faithfulness(ledger, parsed)
    parse_report = build_analyst_adjudication_parse_report(parsed, ledger)
    report = _report("accepted", parse_report)
    report["source_faithfulness_repair"] = repair_report
    return {
        "analyst_adjudication": parsed,
        "analyst_adjudication_prompt": prompt,
        "analyst_adjudication_raw": raw,
        "analyst_adjudication_parse_report": parse_report,
        "analyst_adjudication_chunk_reports": _chunk_report_bundle(
            [_chunk_report(1, 1, "accepted", parse_report)],
            scaffold_chunk_count=0,
        ),
        "analyst_source_faithfulness_repair_report": repair_report,
        "analyst_adjudication_report": report,
    }


def build_analyst_adjudication_prompt(ledger: dict[str, Any]) -> str:
    prompt_rows = [_prompt_row(row) for row in _list(ledger.get("rows")) if isinstance(row, dict)]
    packet = {
        "task": "Adjudicate each row's decision role for the memo.",
        "decision": {
            "question": ledger.get("decision_question"),
            "answer_frame": _compact_answer_frame(ledger.get("stable_final_answer_frame")),
            "effect_rule": "Use challenges_answer only when the row weakens, overturns, or materially lowers confidence in the selected/provisional current_best_answer or the named target_answer_option.",
        },
        "instructions": [
            "Classify every evidence row for its actual use in a decision memo.",
            "Use answer_frame.classification_target_policy to decide answer_relation and effect_on_final_answer.",
            "When answer_status is multi_option or unresolved, classify relative to the live answer option, condition, or crux the row bears on.",
            "When a row rebuts an alternative answer but supports the selected/provisional current_best_answer, use supports_answer or contextualizes_answer and explain that in effect_on_final_answer.",
            "Create compact decision contribution cards: decision_contribution, use_in_reasoning, key_qualifier, quantity_takeaway, source_weight_note, misuse_warning, and if_omitted.",
            "Use source_cards and source_bottom_line_signals as source-level polarity context when assigning memo_use, answer_relation, source_weight_note, and misuse_warning.",
            "When a row's claim wording and source_bottom_lines point in different directions, preserve the tension in key_qualifier or misuse_warning and choose the row's memo role from the source-level bottom line.",
            "For candidate_decision_edge rows, treat relation labels as provisional model proposals; classify endpoint source bottom lines first, then classify the relation as a reasoning move.",
            "Downgrade, background, or mark a candidate_decision_edge for review when its relation label, rationale, anchors, or endpoint claims undercut its proposed decision use.",
            "Return one row for every evidence_item_id.",
            "Use only the enum values in field_axes; memo_use is the memo role, answer_relation is the relation to the answer.",
            "Return strict JSON only.",
        ],
        "chunk": ledger.get("adjudication_chunk", {}),
        "field_axes": _adjudication_field_axes(),
        "required_output_schema": {
            "schema_id": "analyst_adjudication_v1",
            "decision_question": ledger.get("decision_question"),
            "rows": [
                {
                    "evidence_item_id": "stable ID from the ledger",
                    "memo_use": "one allowed_memo_use value",
                    "answer_relation": "one allowed_answer_relation value",
                    "importance_rank": "integer 1-100, where 1 is most important",
                    "rationale": "short source-grounded reason",
                    "target_answer_option": "the answer option or stance this row most directly bears on",
                    "effect_on_final_answer": "supports current_best_answer | weakens current_best_answer | bounds current_best_answer | supports target answer | weakens target answer | bounds target answer | rebuts alternative | distinguishes live options | explains tension | background",
                    "tension_type": "none | clinical_outcome_vs_biomarker | subgroup_scope | dose_scope | study_conflict | mechanism | other",
                    "decision_contribution": "one sentence: what this row changes, supports, weakens, bounds, or clarifies for the decision question",
                    "use_in_reasoning": "answer anchor | counterweight | scope limiter | quantity calibrator | mechanism/context | trace only | other concise natural-language role",
                    "key_qualifier": "caveat that must travel with this evidence if used",
                    "quantity_takeaway": "reader-safe interpretation of decision-facing quantities, or empty string",
                    "source_weight_note": "how strongly this source should move the answer and why",
                    "misuse_warning": "unsafe inference this row should prevent in downstream synthesis",
                    "if_omitted": "what analytical loss occurs if this row is omitted",
                    "covered_by": ["optional evidence_item_id or group_id"],
                    "source_ids": ["optional source IDs copied from ledger"],
                    "quantity_values": ["optional quantities copied from ledger"],
                    "downgrade_reason": "required when memo_use is background_only or not_decision_relevant",
                }
            ],
            "overall_rationale": "one sentence",
        },
        "source_cards": _source_cards_for_prompt([row for row in _list(ledger.get("rows")) if isinstance(row, dict)]),
        "evidence_ledger_rows": prompt_rows,
    }
    return (
        "You are an analyst adjudicating evidence for a decision-support memo.\n"
        "Return a strict JSON object only.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def build_missing_row_adjudication_prompt(ledger: dict[str, Any]) -> str:
    rows = [_prompt_row(row) for row in _list(ledger.get("rows")) if isinstance(row, dict)]
    expected_ids = [str(row.get("evidence_item_id") or "") for row in rows if str(row.get("evidence_item_id") or "").strip()]
    packet = {
        "task": "Repair missing analyst adjudication rows.",
        "decision_question": ledger.get("decision_question"),
        "instructions": [
            "Return exactly one JSON object.",
            "Return exactly one row for each expected_evidence_item_id.",
            "Use each expected_evidence_item_id exactly as provided.",
            "Use only the allowed enum values.",
            "Use only source_ids and quantity_values supplied in each evidence row.",
        ],
        "expected_evidence_item_ids": expected_ids,
        "field_axes": _adjudication_field_axes(),
        "required_output_schema": {
            "schema_id": "analyst_adjudication_v1",
            "decision_question": ledger.get("decision_question"),
            "rows": [
                {
                    "evidence_item_id": "must equal an expected_evidence_item_id",
                    "memo_use": "one allowed_memo_use value",
                    "answer_relation": "one allowed_answer_relation value",
                    "importance_rank": "integer 1-100",
                    "rationale": "short reason grounded in the evidence row",
                    "target_answer_option": "answer option or stance this row bears on, or empty string",
                    "effect_on_final_answer": "brief natural-language effect on the answer",
                    "tension_type": "none | clinical_outcome_vs_biomarker | subgroup_scope | dose_scope | study_conflict | mechanism | other",
                    "decision_contribution": "what this row contributes to the decision",
                    "use_in_reasoning": "answer anchor | counterweight | scope limiter | quantity calibrator | mechanism/context | trace only | other concise natural-language role",
                    "key_qualifier": "caveat that must travel with this evidence if used",
                    "quantity_takeaway": "reader-safe interpretation of supplied quantities, or empty string",
                    "source_weight_note": "how strongly this source should move the answer and why",
                    "misuse_warning": "unsafe inference this row should prevent",
                    "if_omitted": "analytical loss if this row is omitted",
                    "covered_by": [],
                    "source_ids": ["source IDs copied from the evidence row"],
                    "quantity_values": ["quantities copied from the evidence row"],
                    "downgrade_reason": "required if memo_use is background_only or not_decision_relevant, else empty string",
                }
            ],
            "overall_rationale": "one sentence",
        },
        "evidence_rows_to_repair": rows,
    }
    return (
        "You are repairing missing rows from an analyst adjudication JSON artifact.\n"
        "Return strict JSON only.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def deterministic_adjudication_scaffold(ledger: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for index, row in enumerate(_list(ledger.get("rows"))):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "evidence_item_id": str(row.get("evidence_item_id") or ""),
                "memo_use": _memo_use_for_row(row),
                "answer_relation": _answer_relation_for_row(row),
                "importance_rank": min(100, index + 1),
                "rationale": _scaffold_rationale(row),
                "target_answer_option": "",
                "effect_on_final_answer": _effect_for_relation(_answer_relation_for_row(row)),
                "tension_type": "",
                "decision_contribution": _decision_contribution_for_row(row),
                "use_in_reasoning": _use_in_reasoning_for_row(row),
                "key_qualifier": "",
                "quantity_takeaway": _quantity_takeaway_for_row(row),
                "source_weight_note": "",
                "misuse_warning": "",
                "if_omitted": _if_omitted_for_row(row),
                "covered_by": [],
                "source_ids": _string_list(row.get("source_ids")),
                "quantity_values": _string_list(row.get("quantity_values")),
                "downgrade_reason": "scaffold only; live model adjudication not run" if _memo_use_for_row(row) == "background_only" else "",
            }
        )
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": ledger.get("decision_question", ""),
        "rows": rows,
        "overall_rationale": "Prompt-backend scaffold preserves one adjudication row per ledger item; it is not a semantic substitute for live model adjudication.",
    }


def _invalid_adjudication(ledger: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": ledger.get("decision_question", ""),
        "rows": [],
        "overall_rationale": "",
    }


def _prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    prompt = {
        "evidence_item_id": row.get("evidence_item_id"),
        "input_kind": row.get("input_kind"),
        "current_role": row.get("current_role"),
        "current_priority": row.get("current_priority"),
        "current_weight": row.get("current_weight"),
        "directionality": row.get("directionality"),
        "relation_semantic_role": row.get("relation_semantic_role"),
        "source_ids": _string_list(row.get("source_ids"))[:6],
        "source_quality": _source_quality_summary(row),
        "quantity_values": row.get("quantity_values", []),
        "claim": _short_text(str(row.get("claim") or ""), 360),
        "source_bottom_line_signals": _string_list(row.get("source_bottom_line_signals"))[:4],
        "why_it_matters": _short_text(str(row.get("why_it_matters") or ""), 180),
        "failure_condition": _short_text(str(row.get("failure_condition") or ""), 180),
        "claim_ids": row.get("claim_ids") or _string_list(row.get("claim_id")),
        "relation_ids": row.get("relation_ids", []),
        "existing_warning_codes": row.get("existing_warning_codes", []),
    }
    if str(row.get("input_kind") or "") == "candidate_decision_edge":
        prompt.update(
            {
                "relation_contract": _relation_contract_for_prompt(row.get("relation_contract", {})),
                "candidate_pair": _candidate_pair_for_prompt(row.get("candidate_pair", {})),
                "endpoint_claims": _endpoint_claims_for_prompt(row.get("endpoint_claims", [])),
                "relation_endpoint_answer_matrix": _relation_endpoint_answer_matrix_for_prompt(
                    row.get("relation_endpoint_answer_matrix", {})
                ),
            }
        )
    return {key: value for key, value in prompt.items() if value not in (None, "", [], {})}


def _adjudication_field_axes() -> dict[str, list[str]]:
    return {
        "allowed_memo_use": [
            "load_bearing_primary_support",
            "load_bearing_counterweight",
            "quantitative_anchor",
            "scope_or_applicability",
            "decision_crux",
            "mechanism_or_context",
            "background_only",
            "covered_by_group",
            "not_decision_relevant",
            "needs_human_or_model_review",
        ],
        "allowed_answer_relation": [
            "supports_answer",
            "challenges_answer",
            "bounds_scope",
            "identifies_crux",
            "contextualizes_answer",
            "not_decision_relevant",
            "uncertain_relation",
        ],
    }


def _compact_answer_frame(value: Any) -> dict[str, Any]:
    frame = _dict(value)
    return {
        key: frame.get(key)
        for key in (
            "answer_status",
            "current_best_answer",
            "confidence",
            "classification_rule",
            "classification_target_policy",
            "live_answer_options",
        )
        if frame.get(key) not in (None, "", [], {})
    }


def _source_cards_for_prompt(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for row in rows:
        quality = _dict(row.get("source_quality"))
        for source_id in _string_list(row.get("source_ids")):
            card = cards.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "source_quality": quality,
                    "source_bottom_lines": [],
                    "source_bottom_line_signals": [],
                },
            )
            if quality and not card.get("source_quality"):
                card["source_quality"] = quality
            for bottom_line in _source_bottom_lines_for_prompt(row.get("source_bottom_lines")):
                if isinstance(bottom_line, dict) and str(bottom_line.get("source_id") or "") == source_id:
                    card["source_bottom_lines"].append(bottom_line)
            card["source_bottom_line_signals"].extend(_string_list(row.get("source_bottom_line_signals")))
    compact_cards = {}
    for source_id, card in cards.items():
        compact_cards[source_id] = {
            key: value
            for key, value in {
                "source_quality": card.get("source_quality"),
                "source_bottom_lines": _list(card.get("source_bottom_lines"))[:3],
                "source_bottom_line_signals": _dedupe(_string_list(card.get("source_bottom_line_signals")))[:4],
            }.items()
            if value not in (None, "", [], {})
        }
    return compact_cards


def _source_quality_summary(row: dict[str, Any]) -> dict[str, Any]:
    appraisal = _dict(row.get("source_appraisal"))
    return {
        key: value
        for key, value in {
            "quality": row.get("quality"),
            "warnings": _string_list(row.get("source_use_warnings"))[:4],
            "decision_directness": appraisal.get("decision_directness"),
            "evidence_proximity": _string_list(appraisal.get("evidence_proximity"))[:4],
            "recommended_uses": _string_list(appraisal.get("recommended_uses"))[:4],
        }.items()
        if value not in (None, "", [], {})
    }


def _source_bottom_lines_for_prompt(value: Any) -> list[dict[str, str]]:
    rows = []
    for row in _list(value):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                key: field
                for key, field in {
                    "source_id": str(row.get("source_id") or ""),
                    "source_bottom_line": _short_text(str(row.get("source_bottom_line") or ""), 260),
                    "polarity_signal": str(row.get("polarity_signal") or ""),
                }.items()
                if field
            }
        )
    return rows[:4]


def _relation_contract_for_prompt(value: Any) -> dict[str, Any]:
    contract = _dict(value)
    return {
        key: _short_text(str(contract.get(key) or ""), 220)
        for key in ("edge_basis", "source_anchor_a", "source_anchor_b", "why_decision_relevant", "failure_condition")
        if contract.get(key)
    }


def _candidate_pair_for_prompt(value: Any) -> dict[str, Any]:
    pair = _dict(value)
    return {
        key: pair.get(key)
        for key in ("pair_id", "decision_edge_contract", "reason", "score")
        if pair.get(key) not in (None, "", [], {})
    }


def _endpoint_claims_for_prompt(value: Any) -> list[dict[str, Any]]:
    rows = []
    for row in _list(value):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                key: _endpoint_prompt_value(key, row.get(key))
                for key in (
                    "endpoint",
                    "claim_id",
                    "source_ids",
                    "decision_edge_role",
                    "decision_function",
                    "question_relevance",
                    "claim",
                    "source_bottom_lines",
                    "source_bottom_line_signals",
                )
                if row.get(key) not in (None, "", [], {})
            }
        )
    return rows[:4]


def _relation_endpoint_answer_matrix_for_prompt(value: Any) -> dict[str, Any]:
    matrix = _dict(value)
    return {
        key: field
        for key, field in {
            "relation_semantic_role": str(matrix.get("relation_semantic_role") or ""),
            "endpoint_signal_summary": str(matrix.get("endpoint_signal_summary") or ""),
            "endpoints": _endpoint_claims_for_prompt(matrix.get("endpoints")),
        }.items()
        if field not in (None, "", [], {})
    }


def _endpoint_prompt_value(key: str, value: Any) -> Any:
    if key == "claim":
        return _short_text(str(value or ""), 260)
    if key == "source_bottom_lines":
        return _source_bottom_lines_for_prompt(value)
    if key in {"source_ids", "source_bottom_line_signals"}:
        return _string_list(value)[:4]
    return value


def _memo_use_for_row(row: dict[str, Any]) -> str:
    role = str(row.get("current_role") or "").lower()
    input_kind = str(row.get("input_kind") or "")
    if input_kind == "memo_warning":
        return "needs_human_or_model_review"
    if "quant" in role:
        return "quantitative_anchor"
    if "counter" in role:
        return "load_bearing_counterweight"
    if "scope" in role or "boundary" in role:
        return "scope_or_applicability"
    if "crux" in role:
        return "decision_crux"
    if "support" in role or "answer_bearing" in role or "main_map" in role or role == "core":
        return "load_bearing_primary_support"
    if "mechanism" in role or "context" in role:
        return "mechanism_or_context"
    if "appendix" in role or "background" in role:
        return "background_only"
    return "background_only"


def _answer_relation_for_row(row: dict[str, Any]) -> str:
    memo_use = _memo_use_for_row(row)
    return {
        "load_bearing_primary_support": "supports_answer",
        "quantitative_anchor": "supports_answer",
        "load_bearing_counterweight": "challenges_answer",
        "scope_or_applicability": "bounds_scope",
        "decision_crux": "identifies_crux",
        "mechanism_or_context": "contextualizes_answer",
        "background_only": "contextualizes_answer",
        "covered_by_group": "contextualizes_answer",
        "not_decision_relevant": "not_decision_relevant",
        "needs_human_or_model_review": "uncertain_relation",
    }.get(memo_use, "uncertain_relation")


def _effect_for_relation(relation: str) -> str:
    return {
        "supports_answer": "supports current_best_answer",
        "challenges_answer": "weakens current_best_answer",
        "bounds_scope": "bounds current_best_answer",
        "identifies_crux": "explains tension",
        "contextualizes_answer": "background",
        "not_decision_relevant": "background",
    }.get(str(relation or ""), "")


def _decision_contribution_for_row(row: dict[str, Any]) -> str:
    claim = _short_text(str(row.get("claim") or row.get("why_it_matters") or ""), 220)
    if claim:
        return f"Scaffold contribution: {claim}"
    return "Scaffold contribution from the ledger row."


def _use_in_reasoning_for_row(row: dict[str, Any]) -> str:
    return {
        "load_bearing_primary_support": "answer anchor",
        "quantitative_anchor": "quantity calibrator",
        "load_bearing_counterweight": "counterweight",
        "scope_or_applicability": "scope limiter",
        "decision_crux": "decision crux",
        "mechanism_or_context": "mechanism/context",
        "background_only": "trace only",
        "covered_by_group": "trace only",
        "not_decision_relevant": "trace only",
        "needs_human_or_model_review": "review flag",
    }.get(_memo_use_for_row(row), "trace only")


def _quantity_takeaway_for_row(row: dict[str, Any]) -> str:
    quantities = _string_list(row.get("quantity_values"))
    if not quantities:
        return ""
    return "Decision-facing quantities: " + ", ".join(quantities[:6])


def _if_omitted_for_row(row: dict[str, Any]) -> str:
    memo_use = _memo_use_for_row(row)
    if memo_use in {"load_bearing_primary_support", "load_bearing_counterweight", "quantitative_anchor", "scope_or_applicability", "decision_crux"}:
        return "The decision model may lose a load-bearing support, counterweight, quantity, crux, or scope boundary."
    if memo_use == "needs_human_or_model_review":
        return "The decision model may miss a warning that needs explicit review."
    return "The audit trail may lose context while the main answer remains stable."


def _scaffold_rationale(row: dict[str, Any]) -> str:
    role = str(row.get("current_role") or "unknown role")
    priority = str(row.get("current_priority") or "unknown priority")
    return f"Scaffold assignment from current role {role} and priority {priority}."


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    for candidate in (text, _repair_json_syntax(text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {}


def _repair_json_syntax(text: str) -> str:
    return re.sub(r",\s*([\]}])", r"\1", text)


def _repair_covered_by_aliases(payload: Any, known_ids: list[str]) -> Any:
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return payload
    aliases: dict[str, str] = {}
    for known_id in known_ids:
        aliases.setdefault(_id_alias(known_id), known_id)
    for row in payload["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("covered_by"), list):
            continue
        repaired = []
        for target in row["covered_by"]:
            text = str(target).strip()
            repaired.append(aliases.get(_id_alias(text), text))
        row["covered_by"] = repaired
    return payload


def _id_alias(value: str) -> str:
    return _norm(str(value).replace("-", "_"))


def _report(status: str, parse_report: dict[str, Any], *, issues: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_id": "analyst_adjudication_report_v1",
        "status": status,
        "accepted": status.startswith("accepted"),
        "parse_status": parse_report.get("status"),
        "row_count": parse_report.get("row_count", 0),
        "ledger_row_count": parse_report.get("ledger_row_count", 0),
        "issues": [*(issues or []), *[str(issue) for issue in parse_report.get("issues", [])]],
    }


def _chunk_size() -> int:
    try:
        return max(1, int(os.environ.get("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)))
    except ValueError:
        return DEFAULT_CHUNK_SIZE


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)] or [[]]


def _chunk_ledger(ledger: dict[str, Any], rows: list[dict[str, Any]], *, index: int, total: int) -> dict[str, Any]:
    return {
        **ledger,
        "row_count": len(rows),
        "rows": rows,
        "adjudication_chunk": {"index": index, "total": total, "row_count": len(rows)},
    }


def _chunk_report(
    index: int,
    total: int,
    status: str,
    parse_report: dict[str, Any],
    *,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "chunk_index": index,
        "chunk_count": total,
        "status": status,
        "parse_status": parse_report.get("status"),
        "valid": parse_report.get("valid", False),
        "row_count": parse_report.get("row_count", 0),
        "ledger_row_count": parse_report.get("ledger_row_count", 0),
        "missing_evidence_item_ids": parse_report.get("missing_evidence_item_ids", []),
        "unknown_evidence_item_ids": parse_report.get("unknown_evidence_item_ids", []),
        "invalid_covered_by": parse_report.get("invalid_covered_by", []),
        "errors": parse_report.get("errors", []),
        "issues": [*(issues or []), *[str(issue) for issue in parse_report.get("issues", [])]],
    }


def _retry_report(attempt: int, status: str, parse_report: dict[str, Any], error: str = "") -> dict[str, Any]:
    return {
        "attempt": attempt,
        "status": status,
        "parse_status": parse_report.get("status"),
        "valid": parse_report.get("valid", False),
        "issues": [str(issue) for issue in parse_report.get("issues", [])],
        **({"error": error} if error else {}),
    }


def _chunk_progress_details(
    index: int,
    total: int,
    rows: list[dict[str, Any]],
    phase: str,
    *,
    prompt_chars: int,
    raw_chars: int = 0,
    attempt: int,
    status: str = "",
    wall_seconds: float | None = None,
    parsed_row_count: int | None = None,
    issue_count: int | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "substage": "analyst_adjudication_chunk",
        "phase": phase,
        "chunk_index": index,
        "chunk_count": total,
        "row_count": len(rows),
        "evidence_item_ids": [
            str(row.get("evidence_item_id") or "")
            for row in rows
            if str(row.get("evidence_item_id") or "").strip()
        ],
        "attempt": attempt,
        "prompt_chars": prompt_chars,
    }
    if raw_chars:
        details["raw_chars"] = raw_chars
    if status:
        details["chunk_status"] = status
    if wall_seconds is not None:
        details["wall_seconds"] = wall_seconds
    if parsed_row_count is not None:
        details["parsed_row_count"] = parsed_row_count
    if issue_count is not None:
        details["issue_count"] = issue_count
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


def _with_retry_report(report: dict[str, Any], retry_reports: list[dict[str, Any]]) -> dict[str, Any]:
    updated = dict(report)
    updated["attempt_count"] = len(retry_reports)
    updated["retry_reports"] = retry_reports
    return updated


def _chunk_report_bundle(chunks: list[dict[str, Any]], *, scaffold_chunk_count: int) -> dict[str, Any]:
    return {
        "schema_id": "analyst_adjudication_chunk_reports_v1",
        "chunk_count": len(chunks),
        "scaffold_chunk_count": scaffold_chunk_count,
        "chunks": chunks,
    }


def _dedupe_adjudication_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for row in rows:
        row_id = str(row.get("evidence_item_id") or "")
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        result.append(row)
    return result


def _order_rows_by_ledger(rows: list[dict[str, Any]], ledger_ids: list[str]) -> list[dict[str, Any]]:
    by_id = {str(row.get("evidence_item_id")): row for row in rows if str(row.get("evidence_item_id") or "")}
    return [by_id[row_id] for row_id in ledger_ids if row_id in by_id]


def _merged_rationale(chunk_reports: list[dict[str, Any]]) -> str:
    accepted = sum(1 for row in chunk_reports if row.get("status") == "accepted")
    failed = sum(1 for row in chunk_reports if row.get("status") != "accepted")
    return f"Chunked analyst adjudication merged {accepted} accepted chunks and reported {failed} failed or partial chunks without deterministic replacement."


def _ledger_ids(ledger: dict[str, Any]) -> list[str]:
    return [
        str(row.get("evidence_item_id"))
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "")
    ]
