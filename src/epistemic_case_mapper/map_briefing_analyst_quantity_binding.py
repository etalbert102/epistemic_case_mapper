from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_analyst_quantity_prompt import quantity_prompt_candidate
from epistemic_case_mapper.map_briefing_residual_quantities import (
    likely_residual_quantity,
    quantity_covered_by_text,
    quantity_signature,
)
from epistemic_case_mapper.map_briefing_quantity_binding_heuristics import (
    deterministic_quantity_interpretation as _deterministic_interpretation,
    deterministic_quantity_memo_use as _deterministic_memo_use,
    deterministic_quantity_rationale as _deterministic_rationale,
    deterministic_quantity_warnings as _deterministic_warnings,
    quantity_binding_confidence as _binding_confidence,
)
from epistemic_case_mapper.model_backends import run_model_backend


MemoQuantityUse = Literal["yes", "context_only", "no"]
QuantityRole = Literal["decision_anchor", "supporting_detail", "study_descriptor", "statistical_detail", "audit_only"]
DEFAULT_QUANTITY_BINDING_NUM_PREDICT = 1536


class AnalystQuantityAdjudicationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    memo_use: MemoQuantityUse
    quantity_role: QuantityRole = "audit_only"
    must_retain: bool = False
    interpretation: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    retention_phrase: str = ""
    required_for_memo_reason: str = ""
    safe_to_omit_reason: str = ""

    @field_validator(
        "candidate_id",
        "memo_use",
        "quantity_role",
        "interpretation",
        "rationale",
        "retention_phrase",
        "required_for_memo_reason",
        "safe_to_omit_reason",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def _align_role_and_retention(self) -> "AnalystQuantityAdjudicationRow":
        if self.memo_use != "yes" and self.must_retain:
            raise ValueError("must_retain requires memo_use=yes")
        if self.must_retain and self.quantity_role not in {"decision_anchor", "supporting_detail"}:
            raise ValueError("must_retain requires decision_anchor or supporting_detail quantity_role")
        if self.must_retain and not self.retention_phrase.strip():
            raise ValueError("must_retain requires retention_phrase")
        if self.must_retain and not self.required_for_memo_reason.strip():
            raise ValueError("must_retain requires required_for_memo_reason")
        return self


class AnalystQuantityAdjudication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["analyst_quantity_binding_adjudication_v1"] = "analyst_quantity_binding_adjudication_v1"
    bindings: list[AnalystQuantityAdjudicationRow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_candidate_ids(self) -> "AnalystQuantityAdjudication":
        ids = [row.candidate_id for row in self.bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("bindings must have unique candidate_id values")
        return self


def run_analyst_quantity_binding(
    *,
    synthesis_packet: dict[str, Any],
    ledger: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    deterministic = build_analyst_quantity_binding_report(synthesis_packet=synthesis_packet, ledger=ledger)
    prompt = build_analyst_quantity_binding_prompt(synthesis_packet=synthesis_packet, deterministic_report=deterministic)
    if backend.strip() == "prompt":
        report = _run_report("prompt_backend_deterministic", deterministic, parse_report=_prompt_parse_report(deterministic))
        return {
            "analyst_quantity_binding_report": {**deterministic, "run_report": report},
            "analyst_quantity_binding_prompt": prompt,
            "analyst_quantity_binding_raw": "",
            "analyst_quantity_binding_parse_report": report["parse_report"],
            "analyst_quantity_binding_run_report": report,
        }
    try:
        merged, raw, prompt, parse_report = _run_model_quantity_binding_batches(
            synthesis_packet=synthesis_packet,
            deterministic=deterministic,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
        )
    except RuntimeError as exc:
        report = _run_report(
            "backend_error_deterministic",
            deterministic,
            parse_report=_prompt_parse_report(deterministic),
            issues=[str(exc)],
        )
        return {
            "analyst_quantity_binding_report": {**deterministic, "run_report": report},
            "analyst_quantity_binding_prompt": prompt,
            "analyst_quantity_binding_raw": "",
            "analyst_quantity_binding_parse_report": report["parse_report"],
            "analyst_quantity_binding_run_report": report,
        }
    status = "accepted" if parse_report.get("valid") else "model_invalid_deterministic_fallbacks"
    report = _run_report(status, merged, parse_report=parse_report)
    return {
        "analyst_quantity_binding_report": {**merged, "run_report": report},
        "analyst_quantity_binding_prompt": prompt,
        "analyst_quantity_binding_raw": raw,
        "analyst_quantity_binding_parse_report": parse_report,
        "analyst_quantity_binding_run_report": report,
    }


def _run_model_quantity_binding_batches(
    *,
    synthesis_packet: dict[str, Any],
    deterministic: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    batch_size: int = 8,
) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    candidates = [
        row
        for row in _list(deterministic.get("candidate_bindings"))
        if isinstance(row, dict) and bool(row.get("model_adjudication_required"))
    ]
    if not candidates:
        return deterministic, "", build_analyst_quantity_binding_prompt(synthesis_packet=synthesis_packet, deterministic_report=deterministic), _prompt_parse_report(deterministic)
    prompts: list[str] = []
    raws: list[str] = []
    model_rows: list[dict[str, Any]] = []
    parse_reports: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(candidates), batch_size), start=1):
        chunk_rows = candidates[start : start + batch_size]
        chunk_report = _report_from_rows(
            chunk_rows,
            method=str(deterministic.get("method") or "deterministic_candidate_binding"),
            decision_question=str(deterministic.get("decision_question") or ""),
        )
        prompt = build_analyst_quantity_binding_prompt(synthesis_packet=synthesis_packet, deterministic_report=chunk_report)
        prompts.append(f"--- quantity binding batch {index} ---\n{prompt}")
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            response_schema=AnalystQuantityAdjudication.model_json_schema(),
            num_predict=DEFAULT_QUANTITY_BINDING_NUM_PREDICT,
        )
        raw = result.text
        raws.append(f"--- quantity binding batch {index} ---\n{raw}")
        payload = _extract_json(raw)
        merged, parse_report = merge_quantity_adjudication(chunk_report, payload)
        parse_reports.append({**parse_report, "batch_index": index, "batch_candidate_count": len(chunk_rows)})
        model_rows.extend(
            {
                "candidate_id": row.get("candidate_id"),
                "memo_use": row.get("memo_use"),
                "quantity_role": row.get("quantity_role"),
                "must_retain": row.get("must_retain"),
                "interpretation": row.get("interpretation"),
                "rationale": row.get("rationale"),
                "retention_phrase": row.get("retention_phrase"),
                "required_for_memo_reason": row.get("required_for_memo_reason"),
                "safe_to_omit_reason": row.get("safe_to_omit_reason"),
            }
            for row in _list(merged.get("candidate_bindings"))
            if isinstance(row, dict) and row.get("binding_source") == "model"
        )
    merged = _merge_model_rows_with_missing_context(deterministic, model_rows)
    parse_report = _combined_parse_report(deterministic, model_rows=model_rows, parse_reports=parse_reports)
    return merged, "\n\n".join(raws), "\n\n".join(prompts), parse_report


def build_analyst_quantity_binding_report(
    *,
    synthesis_packet: dict[str, Any],
    ledger: dict[str, Any],
    model_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ledger_by_id = {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    candidates = _quantity_candidates(synthesis_packet, ledger_by_id)
    by_id = {str(row.get("candidate_id") or ""): row for row in candidates}
    adjudicated = {
        str(row.get("candidate_id") or ""): row
        for row in (model_rows or [])
        if isinstance(row, dict) and str(row.get("candidate_id") or "") in by_id
    }
    rows = []
    for candidate in candidates:
        row = _binding_row(candidate, adjudicated.get(str(candidate.get("candidate_id") or "")))
        rows.append(row)
    return _report_from_rows(
        rows,
        method="deterministic_candidate_binding" if not model_rows else "model_adjudicated_quantity_binding",
        decision_question=str(synthesis_packet.get("decision_question") or ledger.get("decision_question") or ""),
    )


def build_analyst_quantity_binding_prompt(
    *,
    synthesis_packet: dict[str, Any],
    deterministic_report: dict[str, Any],
) -> str:
    packet = {
        "decision_question": synthesis_packet.get("decision_question"),
        "task": [
            "For each candidate quantity, decide whether it should be a reader-facing obligation in the final memo.",
            "Use yes only when the quantity directly helps answer the decision question or calibrates a load-bearing claim.",
            "Use context_only when the quantity may be useful trace context but should not be a memo obligation.",
            "Use no when the quantity describes a different population, scope, method statistic, source context, or otherwise does not quantify the proposition.",
            "Set must_retain=true only for quantities the memo would be materially worse without.",
            "Prefer a small set of reader-facing anchors over raw statistical clutter.",
            "Classify p-values, heterogeneity statistics, dates, and eligibility windows as statistical_detail or study_descriptor unless the decision question makes them load-bearing.",
            "Write a retention_phrase only for quantities that should appear in the memo.",
        ],
        "candidates": [
            quantity_prompt_candidate(row)
            for row in _list(deterministic_report.get("candidate_bindings"))
            if isinstance(row, dict) and bool(row.get("model_adjudication_required"))
        ],
        "required_output_schema": {
            "schema_id": "analyst_quantity_binding_adjudication_v1",
            "bindings": [
                {
                    "candidate_id": "copy candidate_id exactly",
                    "memo_use": "yes | context_only | no",
                    "quantity_role": "decision_anchor | supporting_detail | study_descriptor | statistical_detail | audit_only",
                    "must_retain": True,
                    "interpretation": "reader-safe explanation of what the quantity measures",
                    "rationale": "why this quantity does or does not quantify the group proposition",
                    "retention_phrase": "short reader-facing phrase to preserve if must_retain is true, otherwise empty",
                    "required_for_memo_reason": "why this number is decision-load-bearing if must_retain is true, otherwise empty",
                    "safe_to_omit_reason": "why this can stay out of memo prose if must_retain is false, otherwise empty",
                }
            ],
        },
    }
    return (
        "You are adjudicating whether extracted quantities are valid memo-facing evidence.\n"
        "Return strict JSON only. Do not return Markdown.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def merge_quantity_adjudication(
    deterministic_report: dict[str, Any],
    payload: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_ids = {
        str(row.get("candidate_id") or "")
        for row in _list(deterministic_report.get("candidate_bindings"))
        if isinstance(row, dict) and bool(row.get("model_adjudication_required"))
    }
    try:
        parsed = AnalystQuantityAdjudication.model_validate(payload)
    except ValidationError as exc:
        return deterministic_report, {
            "schema_id": "analyst_quantity_binding_parse_report_v1",
            "status": "invalid_schema",
            "valid": False,
            "errors": _jsonable_errors(exc),
            "candidate_count": len(candidate_ids),
            "accepted_binding_count": 0,
            "missing_candidate_ids": sorted(candidate_ids),
            "unknown_candidate_ids": [],
            "issues": ["invalid_schema"],
        }
    model_rows = [row.model_dump() for row in parsed.bindings]
    if candidate_ids and not model_rows:
        return deterministic_report, {
            "schema_id": "analyst_quantity_binding_parse_report_v1",
            "status": "empty_bindings",
            "valid": False,
            "errors": [],
            "candidate_count": len(candidate_ids),
            "accepted_binding_count": 0,
            "missing_candidate_ids": sorted(candidate_ids),
            "unknown_candidate_ids": [],
            "issues": ["empty_bindings"],
        }
    row_ids = {row["candidate_id"] for row in model_rows}
    unknown = sorted(row_ids - candidate_ids)
    missing = sorted(candidate_ids - row_ids)
    valid_rows = [row for row in model_rows if row["candidate_id"] in candidate_ids]
    rows = []
    by_model = {row["candidate_id"]: row for row in valid_rows}
    for candidate in _list(deterministic_report.get("candidate_bindings")):
        if not isinstance(candidate, dict):
            continue
        candidate_id = str(candidate.get("candidate_id") or "")
        if candidate_id in by_model:
            model_context = by_model[candidate_id]
        elif candidate.get("model_adjudication_required"):
            model_context = {"_missing_model_row": True}
        else:
            model_context = None
        rows.append(_binding_row(candidate, model_context))
    merged = _report_from_rows(
        rows,
        method="model_adjudicated_quantity_binding",
        decision_question=str(deterministic_report.get("decision_question") or ""),
    )
    issues = [
        *(["unknown_candidate_ids"] if unknown else []),
        *(["missing_candidate_ids_used_deterministic_fallback"] if missing else []),
    ]
    return merged, {
        "schema_id": "analyst_quantity_binding_parse_report_v1",
        "status": "ready" if not issues else "warning",
        "valid": not unknown,
        "candidate_count": len(candidate_ids),
        "accepted_binding_count": len(valid_rows),
        "missing_candidate_ids": missing,
        "unknown_candidate_ids": unknown,
        "issues": issues,
    }


def _merge_model_rows_with_missing_context(deterministic_report: dict[str, Any], model_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = {
        str(row.get("candidate_id") or "")
        for row in _list(deterministic_report.get("candidate_bindings"))
        if isinstance(row, dict) and bool(row.get("model_adjudication_required"))
    }
    valid_rows = [
        row
        for row in model_rows
        if isinstance(row, dict) and str(row.get("candidate_id") or "") in candidate_ids
    ]
    by_model = {str(row.get("candidate_id") or ""): row for row in valid_rows}
    rows = []
    for candidate in _list(deterministic_report.get("candidate_bindings")):
        if not isinstance(candidate, dict):
            continue
        candidate_id = str(candidate.get("candidate_id") or "")
        if candidate_id in by_model:
            model_context = by_model[candidate_id]
        elif candidate.get("model_adjudication_required"):
            model_context = {"_missing_model_row": True}
        else:
            model_context = None
        rows.append(_binding_row(candidate, model_context))
    return _report_from_rows(
        rows,
        method="model_adjudicated_quantity_binding_batched",
        decision_question=str(deterministic_report.get("decision_question") or ""),
    )


def _combined_parse_report(
    deterministic_report: dict[str, Any],
    *,
    model_rows: list[dict[str, Any]],
    parse_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_ids = {
        str(row.get("candidate_id") or "")
        for row in _list(deterministic_report.get("candidate_bindings"))
        if isinstance(row, dict) and bool(row.get("model_adjudication_required"))
    }
    row_ids = {str(row.get("candidate_id") or "") for row in model_rows if isinstance(row, dict)}
    unknown = sorted(row_ids - candidate_ids)
    missing = sorted(candidate_ids - row_ids)
    invalid_batches = [row for row in parse_reports if not row.get("valid")]
    issues = [
        *(["unknown_candidate_ids"] if unknown else []),
        *(["missing_candidate_ids_used_context_only"] if missing else []),
        *(["invalid_quantity_binding_batches"] if invalid_batches else []),
    ]
    return {
        "schema_id": "analyst_quantity_binding_parse_report_v1",
        "status": "ready" if not issues else "warning",
        "valid": not unknown and bool(row_ids & candidate_ids),
        "candidate_count": len(candidate_ids),
        "accepted_binding_count": len(row_ids & candidate_ids),
        "missing_candidate_ids": missing,
        "unknown_candidate_ids": unknown,
        "batch_count": len(parse_reports),
        "batch_reports": parse_reports,
        "issues": issues,
    }


def quantity_bindings_for_group(quantity_binding_report: dict[str, Any], group_id: str) -> list[dict[str, Any]]:
    return [
        row
        for row in _list(quantity_binding_report.get("approved_bindings"))
        if isinstance(row, dict) and str(row.get("group_id") or "") == str(group_id or "")
    ]


def quantity_binding_quality_summary(quantity_binding_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "analyst_quantity_binding_quality_summary_v1",
        "status": quantity_binding_report.get("status", "missing"),
        "candidate_count": quantity_binding_report.get("candidate_count", 0),
        "approved_count": quantity_binding_report.get("approved_count", 0),
        "must_retain_count": quantity_binding_report.get("must_retain_count", 0),
        "context_only_count": quantity_binding_report.get("context_only_count", 0),
        "rejected_count": quantity_binding_report.get("rejected_count", 0),
        "accepted_with_warning_count": quantity_binding_report.get("accepted_with_warning_count", 0),
        "warning_counts": quantity_binding_report.get("warning_counts", {}),
    }


def _quantity_candidates(synthesis_packet: dict[str, Any], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for group in _groups(synthesis_packet):
        group_id = str(group.get("group_id") or "")
        seen_values: set[tuple[str, str]] = set()
        for evidence_id in _string_list(group.get("covered_evidence_item_ids")):
            ledger_row = ledger_by_id.get(evidence_id, {})
            if _uses_legacy_unsplit_quantities(ledger_row):
                for quantity in _string_list(ledger_row.get("quantity_values")):
                    key = (evidence_id, quantity)
                    if key in seen_values:
                        continue
                    seen_values.add(key)
                    rows.append(
                        _candidate_row(
                            group,
                            quantity,
                            source_evidence_item_id=evidence_id,
                            ledger_row=ledger_row,
                            candidate_origin="legacy_unsplit_quantity",
                            model_adjudication_required=False,
                        )
                    )
                continue
            for quantity in _claim_bound_quantity_rows(ledger_row):
                quantity_value = _quantity_value(quantity)
                key = (evidence_id, quantity_value)
                if key in seen_values:
                    continue
                seen_values.add(key)
                rows.append(
                    _candidate_row(
                        group,
                        quantity_value,
                        source_evidence_item_id=evidence_id,
                        ledger_row=ledger_row,
                        quantity_row=quantity if isinstance(quantity, dict) else None,
                        candidate_origin="claim_map_bound",
                        model_adjudication_required=False,
                    )
                )
            for quantity in _string_list(ledger_row.get("residual_quantity_candidate_values")):
                key = (evidence_id, quantity)
                if key in seen_values:
                    continue
                seen_values.add(key)
                rows.append(
                    _candidate_row(
                        group,
                        quantity,
                        source_evidence_item_id=evidence_id,
                        ledger_row=ledger_row,
                        candidate_origin="residual_source_quantity",
                        model_adjudication_required=True,
                    )
                )
        claim_bound_group_values = {
            quantity_signature(row.get("value"))
            for row in rows
            if isinstance(row, dict)
            and str(row.get("group_id") or "") == group_id
            and str(row.get("candidate_origin") or "") == "claim_map_bound"
        }
        for quantity in _string_list(group.get("quantity_values")):
            if any(quantity == row.get("value") and str(row.get("group_id")) == group_id for row in rows):
                continue
            if quantity_signature(quantity) in claim_bound_group_values or quantity_covered_by_text(quantity, _group_quantity_context(group)):
                continue
            if not likely_residual_quantity(quantity, context_text=_group_quantity_context(group)):
                continue
            rows.append(
                _candidate_row(
                    group,
                    quantity,
                    source_evidence_item_id="",
                    ledger_row={},
                    candidate_origin="residual_group_quantity",
                    model_adjudication_required=True,
                )
            )
    return rows


def _candidate_row(
    group: dict[str, Any],
    quantity: str,
    *,
    source_evidence_item_id: str,
    ledger_row: dict[str, Any],
    quantity_row: dict[str, Any] | None = None,
    candidate_origin: str = "residual_source_quantity",
    model_adjudication_required: bool = True,
) -> dict[str, Any]:
    group_id = str(group.get("group_id") or "")
    value = str(quantity or "").strip()
    warnings = _deterministic_warnings(value, group=group, ledger_row=ledger_row)
    memo_use = _deterministic_memo_use(value, group=group, ledger_row=ledger_row, warnings=warnings)
    interpretation = _deterministic_interpretation(value, group=group, ledger_row=ledger_row, memo_use=memo_use)
    return {
        "candidate_id": _candidate_id(group_id, source_evidence_item_id, value),
        "candidate_origin": candidate_origin,
        "model_adjudication_required": model_adjudication_required,
        "group_id": group_id,
        "memo_role": str(group.get("memo_role") or ""),
        "group_proposition": str(group.get("proposition") or ""),
        "value": value,
        "claim_quantity_role": str((quantity_row or {}).get("quantity_role") or ""),
        "claim_quantity_type": str((quantity_row or {}).get("quantity_type") or ""),
        "claim_quantity_retention_hint": str((quantity_row or {}).get("retention_hint") or ""),
        "claim_quantity_interpretation": str((quantity_row or {}).get("local_interpretation") or ""),
        "source_evidence_item_id": source_evidence_item_id,
        "source_claim": str(ledger_row.get("claim") or ""),
        "source_excerpt": str(ledger_row.get("source_excerpt") or ""),
        "claim_bound_quantity_values": _string_list(ledger_row.get("claim_bound_quantity_values")),
        "residual_quantity_values": _string_list(ledger_row.get("residual_quantity_values")),
        "excluded_quantity_values": [
            quantity
            for quantity in _string_list(ledger_row.get("residual_quantity_values"))
            if quantity not in _string_list(ledger_row.get("residual_quantity_candidate_values"))
        ],
        "source_ids": _string_list(ledger_row.get("source_ids")) or _string_list(group.get("source_ids")),
        "source_labels": _string_list(ledger_row.get("source_labels")) or _string_list(group.get("source_labels")),
        "input_kind": str(ledger_row.get("input_kind") or ""),
        "deterministic_memo_use": memo_use,
        "deterministic_warnings": warnings,
        "deterministic_interpretation": interpretation,
        "deterministic_rationale": _deterministic_rationale(value, group=group, ledger_row=ledger_row, memo_use=memo_use, warnings=warnings),
    }


def _binding_row(candidate: dict[str, Any], model_row: dict[str, Any] | None) -> dict[str, Any]:
    model_row = model_row if isinstance(model_row, dict) else {}
    model_missing = bool(model_row.get("_missing_model_row"))
    memo_use = str(model_row.get("memo_use") or ("context_only" if model_missing else _fallback_memo_use(candidate)) or "context_only")
    if memo_use not in {"yes", "context_only", "no"}:
        memo_use = "context_only"
    quantity_role = str(model_row.get("quantity_role") or _fallback_quantity_role(candidate, memo_use=memo_use)).strip()
    if quantity_role not in {"decision_anchor", "supporting_detail", "study_descriptor", "statistical_detail", "audit_only"}:
        quantity_role = "audit_only"
    must_retain = bool(model_row.get("must_retain")) if model_row and not model_missing else _fallback_must_retain(candidate, memo_use=memo_use, quantity_role=quantity_role)
    if memo_use != "yes":
        must_retain = False
    if must_retain and quantity_role not in {"decision_anchor", "supporting_detail"}:
        quantity_role = "supporting_detail"
    interpretation = str(model_row.get("interpretation") or candidate.get("claim_quantity_interpretation") or candidate.get("deterministic_interpretation") or "").strip()
    rationale = str(model_row.get("rationale") or candidate.get("deterministic_rationale") or "").strip()
    retention_phrase = str(model_row.get("retention_phrase") or (interpretation if must_retain else "")).strip()
    required_reason = str(model_row.get("required_for_memo_reason") or (rationale if must_retain else "")).strip()
    safe_to_omit = str(model_row.get("safe_to_omit_reason") or ("" if must_retain else rationale)).strip()
    return {
        **candidate,
        "memo_use": memo_use,
        "quantity_role": quantity_role,
        "must_retain": must_retain,
        "interpretation": _short_text(interpretation, 420) or "Quantity preserved for traceability without memo-facing interpretation.",
        "rationale": _short_text(rationale, 420) or "No binding rationale supplied.",
        "retention_phrase": _short_text(retention_phrase, 360),
        "required_for_memo_reason": _short_text(required_reason, 360),
        "safe_to_omit_reason": _short_text(safe_to_omit, 360),
        "binding_source": "model_missing_context_only" if model_missing else ("model" if model_row else "deterministic"),
        "binding_confidence": _binding_confidence(candidate, memo_use=memo_use, model_row=model_row),
    }


def _fallback_memo_use(candidate: dict[str, Any]) -> str:
    if str(candidate.get("candidate_origin") or "") == "claim_map_bound":
        return "yes" if str(candidate.get("claim_quantity_retention_hint") or "") != "audit_only" else "context_only"
    deterministic = str(candidate.get("deterministic_memo_use") or "context_only")
    if deterministic == "yes" and candidate.get("deterministic_warnings"):
        return "context_only"
    return deterministic if deterministic in {"yes", "context_only", "no"} else "context_only"


def _fallback_must_retain(candidate: dict[str, Any], *, memo_use: str, quantity_role: str) -> bool:
    if memo_use != "yes":
        return False
    if str(candidate.get("candidate_origin") or "") == "claim_map_bound":
        return str(candidate.get("claim_quantity_retention_hint") or "") == "must_retain" and quantity_role in {
            "decision_anchor",
            "supporting_detail",
        }
    return quantity_role == "decision_anchor"


def _fallback_quantity_role(candidate: dict[str, Any], *, memo_use: str) -> str:
    if str(candidate.get("candidate_origin") or "") == "claim_map_bound":
        role = str(candidate.get("claim_quantity_role") or "")
        if role in {"effect_estimate", "uncertainty_interval", "baseline_or_absolute_risk", "threshold_or_guideline"}:
            return "decision_anchor" if memo_use == "yes" else "statistical_detail"
        if role in {"exposure_or_intervention_level", "time_horizon", "cost_or_resource"}:
            return "supporting_detail" if memo_use == "yes" else "study_descriptor"
        if role == "study_descriptor":
            return "study_descriptor"
    warnings = set(_string_list(candidate.get("deterministic_warnings")))
    memo_role = str(candidate.get("memo_role") or "")
    if memo_use == "no":
        return "audit_only"
    if "p_value_not_effect_measure" in warnings or "heterogeneity_statistic_not_effect_measure" in warnings:
        return "statistical_detail"
    if "age_scope_quantity_not_group_measure" in warnings:
        return "study_descriptor"
    if memo_role == "quantitative_anchor" and memo_use == "yes":
        return "decision_anchor"
    if memo_use == "yes":
        return "supporting_detail"
    return "study_descriptor" if memo_use == "context_only" else "audit_only"


def _report_from_rows(rows: list[dict[str, Any]], *, method: str, decision_question: str = "") -> dict[str, Any]:
    _apply_quantity_obligation_budget(rows)
    approved = [row for row in rows if row.get("memo_use") == "yes"]
    must_retain = [row for row in rows if row.get("must_retain")]
    context = [row for row in rows if row.get("memo_use") == "context_only"]
    rejected = [row for row in rows if row.get("memo_use") == "no"]
    accepted_with_warning = [row for row in approved if row.get("deterministic_warnings")]
    warning_counts: dict[str, int] = {}
    for row in rows:
        for warning in _string_list(row.get("deterministic_warnings")):
            warning_counts[warning] = warning_counts.get(warning, 0) + 1
    return {
        "schema_id": "analyst_quantity_binding_report_v1",
        "method": method,
        "status": "warning" if accepted_with_warning else "ready",
        "decision_question": decision_question,
        "candidate_count": len(rows),
        "approved_count": len(approved),
        "must_retain_count": len(must_retain),
        "context_only_count": len(context),
        "rejected_count": len(rejected),
        "accepted_with_warning_count": len(accepted_with_warning),
        "warning_counts": warning_counts,
        "candidate_bindings": rows,
        "approved_bindings": approved,
        "must_retain_bindings": must_retain,
        "context_only_bindings": context,
        "rejected_bindings": rejected,
        "issues": ["accepted_quantity_with_deterministic_warning"] if accepted_with_warning else [],
    }


def _apply_quantity_obligation_budget(rows: list[dict[str, Any]], *, per_group_limit: int = 2, global_limit: int = 12) -> None:
    selected = [row for row in rows if isinstance(row, dict) and row.get("must_retain")]
    if len(selected) <= global_limit:
        return
    by_group: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            row["_quantity_order"] = index
    for row in selected:
        by_group.setdefault(str(row.get("group_id") or ""), []).append(row)
    retained_ids: set[int] = set()
    for group_rows in by_group.values():
        for row in sorted(group_rows, key=_quantity_budget_sort_key)[:per_group_limit]:
            retained_ids.add(id(row))
    retained_ordered = sorted([row for row in selected if id(row) in retained_ids], key=_quantity_budget_sort_key)[:global_limit]
    retained_ids = {id(row) for row in retained_ordered}
    for row in selected:
        if id(row) in retained_ids:
            continue
        row["must_retain"] = False
        row["safe_to_omit_reason"] = (
            str(row.get("safe_to_omit_reason") or "").strip()
            or "Model selected this as memo-relevant, but it was demoted from mandatory retention to keep the memo quantity contract writeable."
        )
        row["required_for_memo_reason"] = ""
    for row in rows:
        if isinstance(row, dict):
            row.pop("_quantity_order", None)


def _quantity_budget_sort_key(row: dict[str, Any]) -> tuple[int, int]:
    role_score = {"decision_anchor": 0, "supporting_detail": 1, "study_descriptor": 2, "statistical_detail": 3, "audit_only": 4}
    return (role_score.get(str(row.get("quantity_role") or ""), 5), int(row.get("_quantity_order") or 0))


def _groups(synthesis_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in (
        "primary_reasoning_chain",
        "main_counterweights",
        "decision_cruxes",
        "scope_and_applicability",
        "quantitative_anchors",
        "background_context",
    ):
        rows.extend(row for row in _list(synthesis_packet.get(key)) if isinstance(row, dict))
    return rows


def _claim_bound_quantity_rows(ledger_row: dict[str, Any]) -> list[Any]:
    rows = [row for row in _list(ledger_row.get("claim_quantities")) if isinstance(row, dict)]
    if rows:
        return rows
    return _string_list(ledger_row.get("claim_bound_quantity_values"))


def _uses_legacy_unsplit_quantities(ledger_row: dict[str, Any]) -> bool:
    if not _string_list(ledger_row.get("quantity_values")):
        return False
    split_keys = (
        "claim_quantities",
        "claim_bound_quantity_values",
        "residual_quantity_values",
        "residual_quantity_candidate_values",
    )
    return not any(ledger_row.get(key) for key in split_keys)


def _quantity_value(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("value") or row.get("quantity") or "").strip()
    return str(row or "").strip()


def _group_quantity_context(group: dict[str, Any]) -> str:
    return " ".join(
        [
            str(group.get("proposition") or ""),
            str(group.get("rationale") or ""),
            str(group.get("answer_impact") or ""),
        ]
    )


def _candidate_id(group_id: str, source_evidence_item_id: str, value: str) -> str:
    source = source_evidence_item_id or "group"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")[:48] or "quantity"
    return f"{group_id}::{source}::{slug}"


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    for candidate in (text, re.sub(r",\s*([\]}])", r"\1", text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {}


def _jsonable_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "loc": [str(part) for part in error.get("loc", [])],
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
    ]


def _prompt_parse_report(deterministic: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "analyst_quantity_binding_parse_report_v1",
        "status": "deterministic",
        "valid": True,
        "candidate_count": deterministic.get("candidate_count", 0),
        "accepted_binding_count": 0,
        "missing_candidate_ids": [],
        "unknown_candidate_ids": [],
        "issues": [],
    }


def _run_report(
    status: str,
    binding_report: dict[str, Any],
    *,
    parse_report: dict[str, Any],
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_id": "analyst_quantity_binding_run_report_v1",
        "status": status,
        "candidate_count": binding_report.get("candidate_count", 0),
        "approved_count": binding_report.get("approved_count", 0),
        "context_only_count": binding_report.get("context_only_count", 0),
        "rejected_count": binding_report.get("rejected_count", 0),
        "accepted_with_warning_count": binding_report.get("accepted_with_warning_count", 0),
        "parse_report": parse_report,
        "issues": issues or binding_report.get("issues", []),
    }
