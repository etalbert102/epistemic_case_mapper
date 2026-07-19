from __future__ import annotations

import json
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from epistemic_case_mapper.model_backends import model_parallelism, run_model_backend, run_parallel
from epistemic_case_mapper.model_stage_retry import model_stage_attempts
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_schemas import (
    build_analyst_adjudication_parse_report,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_faithfulness import (
    repair_adjudication_source_faithfulness,
)


CompactMemoUse = Literal[
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
    "mechanism_or_context",
    "background_only",
    "not_decision_relevant",
    "needs_human_or_model_review",
]
CompactAnswerRelation = Literal[
    "supports_answer",
    "challenges_answer",
    "bounds_scope",
    "identifies_crux",
    "contextualizes_answer",
    "not_decision_relevant",
    "uncertain_relation",
]
PriorityTier = Literal["core", "supporting", "context"]


class EvidenceAdjudicationResponseRowV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item_id: str = Field(min_length=1)
    memo_use: CompactMemoUse
    answer_relation: CompactAnswerRelation
    priority: PriorityTier
    reason: str = Field(min_length=1, max_length=360)
    guardrail: str = Field(default="", max_length=240)
    target_answer_option: str = Field(default="", max_length=160)

    @field_validator("evidence_item_id", "reason", "guardrail", "target_answer_option", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("memo_use", mode="before")
    @classmethod
    def _normalize_memo_use(cls, value: Any) -> str:
        normalized = _enum_text(value)
        return {
            "primary_support": "load_bearing_primary_support",
            "support": "load_bearing_primary_support",
            "counterweight": "load_bearing_counterweight",
            "challenges_answer": "load_bearing_counterweight",
            "scope": "scope_or_applicability",
            "bounds_scope": "scope_or_applicability",
            "crux": "decision_crux",
            "identifies_crux": "decision_crux",
            "context": "mechanism_or_context",
            "contextualizes_answer": "mechanism_or_context",
            "background": "background_only",
            "trace_only": "background_only",
            "exclude": "not_decision_relevant",
            "uncertain_relation": "needs_human_or_model_review",
        }.get(normalized, normalized)

    @field_validator("answer_relation", mode="before")
    @classmethod
    def _normalize_answer_relation(cls, value: Any) -> str:
        normalized = _enum_text(value)
        return {
            "support": "supports_answer",
            "supports": "supports_answer",
            "counterweight": "challenges_answer",
            "challenge": "challenges_answer",
            "scope": "bounds_scope",
            "bounds_answer": "bounds_scope",
            "crux": "identifies_crux",
            "context": "contextualizes_answer",
            "background": "contextualizes_answer",
            "irrelevant": "not_decision_relevant",
            "uncertain": "uncertain_relation",
        }.get(normalized, normalized)

    @field_validator("priority", mode="before")
    @classmethod
    def _normalize_priority(cls, value: Any) -> str:
        normalized = _enum_text(value)
        return {
            "critical": "core",
            "high": "core",
            "medium": "supporting",
            "low": "context",
            "background": "context",
        }.get(normalized, normalized)


class AnalystAdjudicationResponseV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[EvidenceAdjudicationResponseRowV2]

    @model_validator(mode="after")
    def _unique_rows(self) -> "AnalystAdjudicationResponseV2":
        row_ids = [row.evidence_item_id for row in self.rows]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("rows must have unique evidence_item_id values")
        return self


def analyst_adjudication_response_schema_v2() -> dict[str, Any]:
    return AnalystAdjudicationResponseV2.model_json_schema()


def adapt_analyst_adjudication_v2(response: Any, ledger: dict[str, Any]) -> dict[str, Any]:
    parsed = AnalystAdjudicationResponseV2.model_validate(response)
    ledger_rows = _dict_rows(ledger.get("rows"))
    ledger_by_id = {
        str(row.get("evidence_item_id") or "").strip(): row
        for row in ledger_rows
        if str(row.get("evidence_item_id") or "").strip()
    }
    expected_ids = list(ledger_by_id)
    response_by_id = {row.evidence_item_id: row for row in parsed.rows}
    unknown_ids = sorted(set(response_by_id) - set(ledger_by_id))
    missing_ids = sorted(set(ledger_by_id) - set(response_by_id))
    if unknown_ids or missing_ids:
        raise ValueError(
            "compact adjudication must cover the ledger exactly: "
            f"missing_evidence_item_ids={missing_ids} unknown_evidence_item_ids={unknown_ids}"
        )

    rank_by_id = _global_rank_by_id(parsed.rows, ledger_by_id, expected_ids)
    rows = [
        _canonical_row(response_by_id[evidence_id], ledger_by_id[evidence_id], rank_by_id[evidence_id], ledger)
        for evidence_id in expected_ids
    ]
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": str(ledger.get("decision_question") or "").strip(),
        "rows": rows,
        "overall_rationale": "Compact analyst adjudication projected deterministically onto the canonical v1 artifact.",
    }


def run_analyst_adjudication_v2(
    ledger: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    chunk_size: int,
    scaffold_builder: Any,
    progress: Any = None,
) -> dict[str, Any]:
    started = time.monotonic()
    ledger_rows = _dict_rows(ledger.get("rows"))
    chunks = [ledger_rows[offset : offset + max(1, chunk_size)] for offset in range(0, len(ledger_rows), max(1, chunk_size))]
    full_prompt = build_analyst_adjudication_prompt_v2(ledger)
    if backend.strip() == "prompt":
        canonical = scaffold_builder(ledger)
        canonical, repair_report = repair_adjudication_source_faithfulness(ledger, canonical)
        parse_report = build_analyst_adjudication_parse_report(canonical, ledger)
        return _result_bundle(
            canonical=canonical,
            prompt=full_prompt,
            raw="",
            parse_report=parse_report,
            chunk_reports=[_chunk_report(1, len(ledger_rows), "prompt_backend_scaffold", 0, 0)],
            repair_report=repair_report,
            status="prompt_backend_scaffold",
            compact_row_count=0,
            first_pass_missing_count=0,
            recovery_rounds=0,
            initial_chunk_count=1,
            parallelism=1,
            response_schema_supplied=False,
            started=started,
        )

    indexed_chunks = list(enumerate(chunks, start=1))
    initial = run_parallel(
        indexed_chunks,
        lambda item: _run_v2_chunk(
            item,
            ledger=ledger,
            total=len(chunks),
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            phase="initial",
            progress=progress,
        ),
        max_workers=model_parallelism(backend),
    )
    expected_ids = [str(row.get("evidence_item_id") or "") for row in ledger_rows if str(row.get("evidence_item_id") or "")]
    compact_by_id = _accepted_compact_rows(initial, set(expected_ids))
    first_pass_missing = [evidence_id for evidence_id in expected_ids if evidence_id not in compact_by_id]
    recovery_results: list[dict[str, Any]] = []
    recovery_rounds = 0
    missing = first_pass_missing
    while missing and recovery_rounds < model_stage_attempts():
        missing_set = set(missing)
        missing_rows = [row for row in ledger_rows if str(row.get("evidence_item_id") or "") in missing_set]
        repair_chunks = [
            missing_rows[offset : offset + max(1, chunk_size)]
            for offset in range(0, len(missing_rows), max(1, chunk_size))
        ]
        round_results = run_parallel(
            list(enumerate(repair_chunks, start=1)),
            lambda item: _run_v2_chunk(
                item,
                ledger=ledger,
                total=len(repair_chunks),
                backend=backend,
                backend_timeout=backend_timeout,
                backend_retries=backend_retries,
                phase="missing_row_repair",
                progress=progress,
            ),
            max_workers=model_parallelism(backend),
        )
        recovery_results.extend(round_results)
        compact_by_id.update(_accepted_compact_rows(round_results, set(missing)))
        missing = [evidence_id for evidence_id in expected_ids if evidence_id not in compact_by_id]
        recovery_rounds += 1

    compact_payload = {"rows": [compact_by_id[evidence_id] for evidence_id in expected_ids if evidence_id in compact_by_id]}
    canonical = _adapt_available_rows(compact_payload, ledger)
    canonical, repair_report = repair_adjudication_source_faithfulness(ledger, canonical)
    parse_report = build_analyst_adjudication_parse_report(canonical, ledger)
    failed_chunks = sum(1 for row in [*initial, *recovery_results] if row["status"] != "accepted")
    status = (
        "accepted_after_missing_row_repair"
        if parse_report.get("valid") and recovery_results
        else "accepted"
        if parse_report.get("valid") and not failed_chunks
        else "accepted_with_chunk_warnings"
        if parse_report.get("valid")
        else "model_output_invalid"
    )
    prompts = [str(row.get("prompt") or "") for row in [*initial, *recovery_results]]
    raws = [str(row.get("raw") or "") for row in [*initial, *recovery_results]]
    return _result_bundle(
        canonical=canonical,
        prompt="\n\n".join(prompts),
        raw="\n\n".join(raws),
        parse_report=parse_report,
        chunk_reports=[row["report"] for row in [*initial, *recovery_results]],
        repair_report=repair_report,
        status=status,
        compact_row_count=len(compact_by_id),
        first_pass_missing_count=len(first_pass_missing),
        recovery_rounds=recovery_rounds,
        initial_chunk_count=len(initial),
        parallelism=model_parallelism(backend),
        response_schema_supplied=True,
        started=started,
    )


def build_analyst_adjudication_schema_comparison(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_by_id = _canonical_by_id(baseline)
    candidate_by_id = _canonical_by_id(candidate)
    all_ids = sorted(set(baseline_by_id) | set(candidate_by_id))
    differences = []
    for evidence_id in all_ids:
        old = baseline_by_id.get(evidence_id, {})
        new = candidate_by_id.get(evidence_id, {})
        changed = [
            field
            for field in ("memo_use", "answer_relation", "target_answer_option")
            if str(old.get(field) or "").strip() != str(new.get(field) or "").strip()
        ]
        if changed or not old or not new:
            differences.append(
                {
                    "evidence_item_id": evidence_id,
                    "changed_fields": changed,
                    "baseline_present": bool(old),
                    "candidate_present": bool(new),
                    "baseline_memo_use": old.get("memo_use"),
                    "candidate_memo_use": new.get("memo_use"),
                    "baseline_answer_relation": old.get("answer_relation"),
                    "candidate_answer_relation": new.get("answer_relation"),
                    "high_impact": _high_impact_difference(old, new, changed),
                }
            )
    return {
        "schema_id": "analyst_adjudication_schema_comparison_v1",
        "baseline_row_count": len(baseline_by_id),
        "candidate_row_count": len(candidate_by_id),
        "difference_count": len(differences),
        "high_impact_difference_count": sum(1 for row in differences if row["high_impact"]),
        "differences": differences,
    }


def build_analyst_adjudication_prompt_v2(ledger: dict[str, Any]) -> str:
    rows = [_prompt_row(row) for row in _dict_rows(ledger.get("rows"))]
    packet = {
        "task": "Classify each evidence row for decision-model routing.",
        "decision_question": ledger.get("decision_question"),
        "answer_frame": _compact_answer_frame(ledger.get("stable_final_answer_frame")),
        "instructions": [
            "Return exactly one row for every supplied evidence_item_id.",
            "Classify relative to current_best_answer when one is supplied; otherwise use the relevant live answer option.",
            "Use primary support/supports only when the row strengthens that answer; use counterweight/challenges when it weakens the answer or confidence in it.",
            "Use scope_or_applicability/bounds_scope for dose, subgroup, population, endpoint, or applicability limits that bound rather than directly weaken the answer.",
            "Use source_bottom_lines and source_bottom_line_signals over support-shaped claim wording when they conflict.",
            "Treat candidate relation labels as provisional and judge their endpoint evidence before assigning a role.",
            "Use guardrail only for a qualifier or unsafe inference that must travel with the row.",
            "When live_answer_options are supplied, copy the relevant target option exactly or leave target_answer_option empty.",
            "Do not copy sources, quantities, claims, or provenance into the response.",
            "Return strict JSON only.",
        ],
        "output_contract": {
            "required": ["evidence_item_id", "memo_use", "answer_relation", "priority", "reason"],
            "optional": ["guardrail", "target_answer_option"],
            "memo_use": list(CompactMemoUse.__args__),
            "answer_relation": list(CompactAnswerRelation.__args__),
            "priority": list(PriorityTier.__args__),
        },
        "evidence_rows": rows,
    }
    return (
        "You are an analyst triaging evidence before global decision modeling.\n"
        "Return a strict JSON object only.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def _run_v2_chunk(
    item: tuple[int, list[dict[str, Any]]],
    *,
    ledger: dict[str, Any],
    total: int,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    phase: str,
    progress: Any,
) -> dict[str, Any]:
    index, rows = item
    chunk_ledger = {**ledger, "rows": rows}
    prompt = build_analyst_adjudication_prompt_v2(chunk_ledger)
    expected_ids = {
        str(row.get("evidence_item_id") or "")
        for row in rows
        if str(row.get("evidence_item_id") or "")
    }
    _progress(progress, "started", index=index, total=total, phase=phase, row_count=len(rows))
    raw = ""
    last_issue = ""
    for attempt in range(1, model_stage_attempts() + 1):
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                response_schema=analyst_adjudication_response_schema_v2(),
            )
            raw = result.text
            payload = _normalize_compact_payload(_extract_json(raw))
            parsed = AnalystAdjudicationResponseV2.model_validate(payload)
            invalid_targets = _invalid_target_options(parsed.rows, chunk_ledger)
            if invalid_targets:
                last_issue = f"unsupported_target_answer_options={invalid_targets}"
                continue
            returned_ids = {row.evidence_item_id for row in parsed.rows}
            unknown = sorted(returned_ids - expected_ids)
            missing = sorted(expected_ids - returned_ids)
            if unknown:
                last_issue = f"missing={missing} unknown={unknown}"
                continue
            compact_rows = [row.model_dump() for row in parsed.rows]
            if missing:
                _progress(progress, "partial", index=index, total=total, phase=phase, row_count=len(rows), attempt=attempt)
                return {
                    "status": "partial",
                    "rows": compact_rows,
                    "prompt": prompt,
                    "raw": raw,
                    "report": _chunk_report(
                        index,
                        len(rows),
                        "model_output_partial",
                        attempt,
                        len(raw),
                        issues=[f"missing={missing}"],
                    ),
                }
            _progress(progress, "completed", index=index, total=total, phase=phase, row_count=len(rows), attempt=attempt)
            return {
                "status": "accepted",
                "rows": compact_rows,
                "prompt": prompt,
                "raw": raw,
                "report": _chunk_report(index, len(rows), "accepted", attempt, len(raw)),
            }
        except (RuntimeError, ValueError) as exc:
            last_issue = f"{type(exc).__name__}: {exc}"
    _progress(progress, "failed", index=index, total=total, phase=phase, row_count=len(rows))
    return {
        "status": "model_output_invalid",
        "rows": [],
        "prompt": prompt,
        "raw": raw,
        "report": _chunk_report(
            index,
            len(rows),
            "model_output_invalid",
            model_stage_attempts(),
            len(raw),
            issues=[last_issue] if last_issue else [],
        ),
    }


def _adapt_available_rows(compact_payload: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    available_ids = {
        str(row.get("evidence_item_id") or "")
        for row in _dict_rows(compact_payload.get("rows"))
        if str(row.get("evidence_item_id") or "")
    }
    subset_ledger = {
        **ledger,
        "rows": [
            row
            for row in _dict_rows(ledger.get("rows"))
            if str(row.get("evidence_item_id") or "") in available_ids
        ],
    }
    if not available_ids:
        return {
            "schema_id": "analyst_adjudication_v1",
            "decision_question": str(ledger.get("decision_question") or ""),
            "rows": [],
            "overall_rationale": "Compact analyst adjudication did not return valid rows.",
        }
    return adapt_analyst_adjudication_v2(compact_payload, subset_ledger)


def _result_bundle(
    *,
    canonical: dict[str, Any],
    prompt: str,
    raw: str,
    parse_report: dict[str, Any],
    chunk_reports: list[dict[str, Any]],
    repair_report: dict[str, Any],
    status: str,
    compact_row_count: int,
    first_pass_missing_count: int,
    recovery_rounds: int,
    initial_chunk_count: int,
    parallelism: int,
    response_schema_supplied: bool,
    started: float,
) -> dict[str, Any]:
    failed_count = sum(1 for row in chunk_reports if row.get("status") not in {"accepted", "prompt_backend_scaffold"})
    initial_failed_count = sum(
        1
        for row in chunk_reports[:initial_chunk_count]
        if row.get("status") not in {"accepted", "prompt_backend_scaffold"}
    )
    report = {
        "schema_id": "analyst_adjudication_report_v1",
        "status": status,
        "accepted": bool(parse_report.get("valid")),
        "parse_status": parse_report.get("status"),
        "issues": list(parse_report.get("issues") or []),
        "source_faithfulness_repair": repair_report,
    }
    return {
        "analyst_adjudication": canonical,
        "analyst_adjudication_prompt": prompt,
        "analyst_adjudication_raw": raw,
        "analyst_adjudication_parse_report": parse_report,
        "analyst_adjudication_chunk_reports": {
            "schema_id": "analyst_adjudication_chunk_reports_v1",
            "chunk_count": len(chunk_reports),
            "scaffold_chunk_count": sum(1 for row in chunk_reports if row.get("status") == "prompt_backend_scaffold"),
            "failed_chunk_count": failed_count,
            "initial_failed_chunk_count": initial_failed_count,
            "missing_row_repair_chunk_count": max(0, len(chunk_reports) - initial_chunk_count),
            "missing_row_repair_round_count": recovery_rounds,
            "parallelism": parallelism,
            "chunks": chunk_reports,
        },
        "analyst_source_faithfulness_repair_report": repair_report,
        "analyst_adjudication_report": report,
        "analyst_adjudication_schema_report": {
            "schema_id": "analyst_adjudication_schema_report_v1",
            "schema_version": "v2",
            "response_schema_supplied": response_schema_supplied,
            "model_row_field_count": len(EvidenceAdjudicationResponseRowV2.model_fields),
            "canonical_row_field_count": 19,
            "compact_row_count": compact_row_count,
            "first_pass_missing_row_count": first_pass_missing_count,
            "missing_row_repair_round_count": recovery_rounds,
            "prompt_chars": len(prompt),
            "raw_chars": len(raw),
            "wall_seconds": round(time.monotonic() - started, 3),
        },
    }


def _chunk_report(
    index: int,
    row_count: int,
    status: str,
    attempt: int,
    raw_chars: int,
    *,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "chunk_index": index,
        "row_count": row_count,
        "status": status,
        "attempt": attempt,
        "raw_chars": raw_chars,
        "issues": issues or [],
    }


def _accepted_compact_rows(results: list[dict[str, Any]], allowed_ids: set[str]) -> dict[str, dict[str, Any]]:
    accepted: dict[str, dict[str, Any]] = {}
    for result in results:
        if result.get("status") not in {"accepted", "partial"}:
            continue
        for row in _dict_rows(result.get("rows")):
            evidence_id = str(row.get("evidence_item_id") or "")
            if evidence_id in allowed_ids and evidence_id not in accepted:
                accepted[evidence_id] = row
    return accepted


def _invalid_target_options(
    rows: list[EvidenceAdjudicationResponseRowV2],
    ledger: dict[str, Any],
) -> list[dict[str, str]]:
    frame = ledger.get("stable_final_answer_frame") if isinstance(ledger.get("stable_final_answer_frame"), dict) else {}
    options = frame.get("live_answer_options")
    allowed = _answer_option_values(options)
    if not allowed:
        return []
    return [
        {"evidence_item_id": row.evidence_item_id, "target_answer_option": row.target_answer_option}
        for row in rows
        if row.target_answer_option and _normalized(row.target_answer_option) not in allowed
    ]


def _answer_option_values(value: Any) -> set[str]:
    values: set[str] = set()
    for option in value if isinstance(value, list) else []:
        if isinstance(option, dict):
            for key in ("candidate_answer_id", "option_id", "id", "label", "answer", "stance"):
                if option.get(key):
                    values.add(_normalized(option[key]))
        elif str(option or "").strip():
            values.add(_normalized(option))
    return values


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _enum_text(value: Any) -> str:
    return _normalized(value).replace("-", "_").replace(" ", "_")


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _normalize_compact_payload(payload: Any) -> Any:
    if isinstance(payload, list):
        return {"rows": payload}
    if isinstance(payload, dict) and len(payload) == 1:
        wrapper = next(iter(payload))
        wrapped_rows = payload[wrapper]
        if isinstance(wrapped_rows, list) and all(
            isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
            for row in wrapped_rows
        ):
            return {"rows": wrapped_rows}
    return payload


def _progress(progress: Any, status: str, **details: Any) -> None:
    if progress is not None:
        progress("analyst_adjudication_chunk", status, {"substage": "analyst_adjudication_chunk", **details})


def _canonical_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_item_id") or ""): row
        for row in _dict_rows(payload.get("rows"))
        if str(row.get("evidence_item_id") or "")
    }


def _high_impact_difference(old: dict[str, Any], new: dict[str, Any], changed_fields: list[str]) -> bool:
    high_impact_roles = {
        "load_bearing_primary_support",
        "load_bearing_counterweight",
        "quantitative_anchor",
        "scope_or_applicability",
        "decision_crux",
        "not_decision_relevant",
    }
    return bool(
        "memo_use" in changed_fields
        and {str(old.get("memo_use") or ""), str(new.get("memo_use") or "")} & high_impact_roles
        or "answer_relation" in changed_fields
        or "target_answer_option" in changed_fields
    )


def _global_rank_by_id(
    rows: list[EvidenceAdjudicationResponseRowV2],
    ledger_by_id: dict[str, dict[str, Any]],
    ledger_order: list[str],
) -> dict[str, int]:
    tier_order = {"core": 0, "supporting": 1, "context": 2}
    position = {evidence_id: index for index, evidence_id in enumerate(ledger_order)}
    ordered = sorted(
        rows,
        key=lambda row: (
            tier_order[row.priority],
            _integer(ledger_by_id[row.evidence_item_id].get("current_priority"), 100),
            position[row.evidence_item_id],
        ),
    )
    return {row.evidence_item_id: min(index, 100) for index, row in enumerate(ordered, start=1)}


def _canonical_row(
    row: EvidenceAdjudicationResponseRowV2,
    ledger_row: dict[str, Any],
    importance_rank: int,
    ledger: dict[str, Any],
) -> dict[str, Any]:
    guardrail = row.guardrail
    return {
        "evidence_item_id": row.evidence_item_id,
        "memo_use": row.memo_use,
        "importance_rank": importance_rank,
        "rationale": row.reason,
        "answer_relation": row.answer_relation,
        "covered_by": [],
        "source_ids": _strings(ledger_row.get("source_ids")),
        "quantity_values": _strings(ledger_row.get("quantity_values")),
        "target_answer_option": row.target_answer_option,
        "effect_on_final_answer": _effect_on_answer(row.answer_relation, row.target_answer_option, ledger),
        "tension_type": "",
        "downgrade_reason": row.reason
        if row.memo_use in {"background_only", "not_decision_relevant"}
        else "",
        "decision_contribution": row.reason,
        "use_in_reasoning": _reasoning_use(row.memo_use),
        "key_qualifier": guardrail,
        "quantity_takeaway": "",
        "source_weight_note": "",
        "misuse_warning": guardrail,
        "if_omitted": "",
    }


def _effect_on_answer(answer_relation: str, target_answer_option: str, ledger: dict[str, Any]) -> str:
    frame = ledger.get("stable_final_answer_frame") if isinstance(ledger.get("stable_final_answer_frame"), dict) else {}
    has_current_answer = bool(str(frame.get("current_best_answer") or "").strip())
    target = "current_best_answer" if has_current_answer else "target answer" if target_answer_option else "answer"
    return {
        "supports_answer": f"supports {target}",
        "challenges_answer": f"weakens {target}",
        "bounds_scope": f"bounds {target}",
        "identifies_crux": "distinguishes live options",
        "contextualizes_answer": f"contextualizes {target}",
        "not_decision_relevant": "background",
        "uncertain_relation": "explains tension",
    }[answer_relation]


def _reasoning_use(memo_use: str) -> str:
    return {
        "load_bearing_primary_support": "answer anchor",
        "load_bearing_counterweight": "counterweight",
        "quantitative_anchor": "quantity calibrator",
        "scope_or_applicability": "scope limiter",
        "decision_crux": "decision crux",
        "mechanism_or_context": "mechanism/context",
        "background_only": "trace only",
        "not_decision_relevant": "trace only",
        "needs_human_or_model_review": "review",
    }[memo_use]


def _prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "evidence_item_id": row.get("evidence_item_id"),
        "input_kind": row.get("input_kind"),
        "current_role": row.get("current_role"),
        "current_priority": row.get("current_priority"),
        "current_weight": row.get("current_weight"),
        "directionality": row.get("directionality"),
        "relation_semantic_role": row.get("relation_semantic_role"),
        "source_ids": _strings(row.get("source_ids"))[:6],
        "source_quality": _source_quality(row),
        "quantity_values": _strings(row.get("quantity_values"))[:6],
        "claim": _short_text(row.get("claim"), 360),
        "source_bottom_lines": _source_bottom_lines(row.get("source_bottom_lines")),
        "source_bottom_line_signals": _strings(row.get("source_bottom_line_signals"))[:4],
        "why_it_matters": _short_text(row.get("why_it_matters"), 180),
        "failure_condition": _short_text(row.get("failure_condition"), 180),
        "existing_warning_codes": _strings(row.get("existing_warning_codes"))[:4],
    }
    if str(row.get("input_kind") or "") == "candidate_decision_edge":
        compact.update(
            {
                "relation_contract": _selected_dict(
                    row.get("relation_contract"),
                    ("edge_basis", "source_anchor_a", "source_anchor_b", "why_decision_relevant", "failure_condition"),
                ),
                "candidate_pair": _selected_dict(
                    row.get("candidate_pair"),
                    ("pair_id", "decision_edge_contract", "reason", "score", "pair_intent"),
                ),
                "endpoint_claims": [_endpoint_claim(item) for item in _dict_rows(row.get("endpoint_claims"))[:4]],
                "relation_endpoint_answer_matrix": row.get("relation_endpoint_answer_matrix")
                if isinstance(row.get("relation_endpoint_answer_matrix"), dict)
                else {},
            }
        )
    return _drop_empty(compact)


def _compact_answer_frame(value: Any) -> dict[str, Any]:
    frame = value if isinstance(value, dict) else {}
    return _drop_empty(
        {
            key: frame.get(key)
            for key in (
                "answer_status",
                "current_best_answer",
                "confidence",
                "classification_rule",
                "classification_target_policy",
                "live_answer_options",
            )
        }
    )


def _source_quality(row: dict[str, Any]) -> dict[str, Any]:
    appraisal = row.get("source_appraisal") if isinstance(row.get("source_appraisal"), dict) else {}
    return _drop_empty(
        {
            "quality": row.get("quality"),
            "warnings": _strings(row.get("source_use_warnings"))[:4],
            "decision_directness": appraisal.get("decision_directness"),
            "evidence_proximity": _strings(appraisal.get("evidence_proximity"))[:4],
            "recommended_uses": _strings(appraisal.get("recommended_uses"))[:4],
        }
    )


def _source_bottom_lines(value: Any) -> list[dict[str, str]]:
    return [
        _drop_empty(
            {
                "source_id": str(row.get("source_id") or ""),
                "source_bottom_line": _short_text(row.get("source_bottom_line"), 260),
                "polarity_signal": str(row.get("polarity_signal") or ""),
            }
        )
        for row in _dict_rows(value)[:4]
    ]


def _endpoint_claim(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "endpoint": row.get("endpoint"),
            "claim_id": row.get("claim_id"),
            "source_ids": _strings(row.get("source_ids"))[:4],
            "decision_edge_role": row.get("decision_edge_role"),
            "decision_function": row.get("decision_function"),
            "claim": _short_text(row.get("claim"), 240),
            "source_bottom_lines": _source_bottom_lines(row.get("source_bottom_lines")),
            "source_bottom_line_signals": _strings(row.get("source_bottom_line_signals"))[:4],
        }
    )


def _selected_dict(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    return _drop_empty({key: row.get(key) for key in keys})


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [] if value in (None, "") else [value]
    return [str(item).strip() for item in value if str(item).strip()]


def _short_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
