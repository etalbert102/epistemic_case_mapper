from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_decision_diagnosticity import apply_decision_diagnostic_ranking
from epistemic_case_mapper.map_briefing_analyst_decision_logic import (
    argument_plan_transition,
    is_scaffolded_decision_logic_text,
    naturalize_decision_logic_payload,
    naturalize_decision_logic_text,
)
from epistemic_case_mapper.map_briefing_analyst_decision_model_prompt_contract import (
    decision_model_required_output_schema,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import model_parallelism, run_parallel
from epistemic_case_mapper.model_stage_retry import model_stage_attempts


def should_use_parallel_analyst_decision_model(context: dict[str, Any]) -> bool:
    try:
        threshold = max(1, int(os.environ.get("ECM_ANALYST_DECISION_MODEL_PARALLEL_THRESHOLD", "12")))
    except ValueError:
        threshold = 12
    return len(_rows(context)) > threshold


def run_parallel_analyst_decision_model(
    *,
    context: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
    run_backend: Callable[..., Any],
) -> dict[str, Any]:
    started = time.monotonic()
    tasks = build_decision_model_tasks(context)
    task_results = run_parallel(
        tasks,
        lambda task: _run_task(
            task,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            num_predict=num_predict,
            run_backend=run_backend,
        ),
        max_workers=model_parallelism(backend),
    )
    payloads = [row.get("payload") for row in task_results if isinstance(row.get("payload"), dict) and row.get("status") == "parsed"]
    merged = merge_decision_model_payloads(context, payloads)
    return {
        "payload": merged,
        "prompt": _join([str(row.get("prompt") or "") for row in task_results], "analyst decision model task prompt"),
        "raw": _join([str(row.get("raw") or "") for row in task_results], "analyst decision model task raw"),
        "report": {
            "schema_id": "parallel_analyst_decision_model_report_v1",
            "method": "parallel_grouped_analyst_decision_model",
            "task_count": len(tasks),
            "parsed_count": len(payloads),
            "failed_count": sum(1 for row in task_results if row.get("status") != "parsed"),
            "parallelism": model_parallelism(backend),
            "wall_seconds": round(time.monotonic() - started, 3),
            "task_reports": [_public_task_report(row) for row in task_results],
        },
    }


def build_decision_model_tasks(context: dict[str, Any], *, max_rows_per_task: int | None = None) -> list[dict[str, Any]]:
    size = _task_size(max_rows_per_task)
    rows = _rows(context)
    tasks = []
    for offset in range(0, len(rows), size):
        task_rows = rows[offset : offset + size]
        tasks.append(
            {
                "task_id": f"analyst_decision_model_task_{len(tasks) + 1:03d}",
                "decision_question": context.get("decision_question", ""),
                "stable_final_answer_frame": _dict(context.get("stable_final_answer_frame")),
                "evidence_rows": [_compact_task_row(row) for row in task_rows],
                "obligation_group_skeleton": _skeleton_for_rows(context, task_rows),
                "model_hints": _hints_for_rows(context, task_rows),
            }
        )
    return tasks


def build_decision_model_task_prompt(task: dict[str, Any]) -> str:
    packet = {
            "task": "Build local analyst decision-model groups for only these evidence rows. Return strict JSON only.",
        "decision_question": task.get("decision_question"),
        "stable_final_answer_frame": _dict(task.get("stable_final_answer_frame")),
        "instructions": [
                "Use stable_final_answer_frame.classification_target_policy when deciding whether evidence supports, weakens, bounds, distinguishes, or contextualizes an answer.",
                "When answer_status is selected or provisional and current_best_answer is present, classify relative to that answer while preserving the affected live option in target_answer_option.",
                "When answer_status is multi_option or unresolved, organize evidence around the live answer options, conditions, and cruxes instead of forcing a single final-answer polarity.",
                "Group rows when they support the same decision-relevant proposition.",
                "Keep support, counterweight, scope, crux, mechanism/context, and quantity roles analytically distinct.",
                "Do not use load_bearing_counterweight for evidence that only rebuts a rejected or feared alternative while supporting a selected/provisional current_best_answer.",
                "Use scope_or_applicability for subgroup, dose, population, or applicability boundaries unless the row directly weakens the selected/provisional current_best_answer or named target answer inside its stated scope.",
                "Rank groups by decision diagnosticity, not generic relevance. Outcome/effect, quantity, crux, counterweight, and scope-boundary evidence should outrank background or contextual guidance when they more directly change the answer.",
                "If a row is merely contextual, do not make it the top support unless it is the actual reason the decision answer changes.",
                "Every supplied evidence_item_id must appear in either evidence_groups.covered_evidence_item_ids or evidence_dispositions.",
                "For every supplied evidence_item_id, fill memo_relevance_decisions with memo_spine, supporting_context, trace_only, or exclude.",
                "For every supplied quantity_value, fill quantity_relevance_decisions. Mark must_use only when the quantity calibrates the answer, threshold, tradeoff, scope boundary, or update trigger.",
                "Give reader-facing quantities a short retention_phrase that says what the number measures.",
                "Use only supplied evidence IDs. Do not invent sources, quantities, or IDs.",
                "Use ordinary analyst language. This is an intermediate model for later synthesis, not a memo.",
        ],
        "allowed_memo_inclusion": ["memo_spine", "supporting_context", "trace_only", "exclude"],
        "allowed_quantity_inclusion": ["must_use", "supporting_context", "trace_only", "exclude"],
        "allowed_memo_role": [
            "load_bearing_primary_support",
            "load_bearing_counterweight",
            "quantitative_anchor",
            "scope_or_applicability",
            "decision_crux",
            "mechanism_or_context",
            "background_only",
            "needs_human_or_model_review",
        ],
        "required_output_schema": decision_model_required_output_schema(task.get("decision_question")),
        "context": task,
    }
    return json.dumps(packet, indent=2, ensure_ascii=False)


def merge_decision_model_payloads(context: dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
    groups = []
    dispositions_by_id: dict[str, dict[str, Any]] = {}
    for payload_index, payload in enumerate(payloads, start=1):
        for group_index, group in enumerate(_list(payload.get("evidence_groups")), start=1):
            if not isinstance(group, dict):
                continue
            normalized = dict(group)
            normalized["group_id"] = _stable_group_id(normalized, payload_index, group_index)
            normalized["covered_evidence_item_ids"] = _known_ids(context, _string_list(normalized.get("covered_evidence_item_ids")))
            if normalized["covered_evidence_item_ids"]:
                groups.append(normalized)
        for row in _list(payload.get("evidence_dispositions")):
            if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip():
                dispositions_by_id[str(row.get("evidence_item_id"))] = dict(row)
    groups = _dedupe_groups(groups)
    groups, _ranking_guard = apply_decision_diagnostic_ranking(groups, _rows(context))
    groups = [_schema_safe_group(group) for group in groups]
    covered = {evidence_id for group in groups for evidence_id in _string_list(group.get("covered_evidence_item_ids"))}
    dispositions = _merged_dispositions(context, groups, dispositions_by_id, covered)
    memo_relevance_decisions = _merged_memo_relevance_decisions(context, payloads, groups, dispositions)
    return {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": context.get("decision_question", ""),
        "direct_answer": _merged_direct_answer(payloads),
        "confidence": _merged_confidence(payloads),
        "overall_rationale": _overall_rationale(groups, payloads),
        "evidence_groups": groups,
        "evidence_dispositions": dispositions,
        "memo_relevance_decisions": memo_relevance_decisions,
        "quantity_relevance_decisions": _merged_quantity_relevance_decisions(context, payloads, memo_relevance_decisions),
        "quantitative_anchors": _merged_texts(context, payloads, "quantitative_anchors"),
        "what_would_change_the_answer": _merged_texts(context, payloads, "what_would_change_the_answer"),
        "decision_logic": _decision_logic(context, groups, payloads),
        "argument_plan": _argument_plan(groups, payloads),
    }


def _run_task(
    task: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
    run_backend: Callable[..., Any],
) -> dict[str, Any]:
    prompt = build_decision_model_task_prompt(task)
    started = time.monotonic()
    retry_reports: list[dict[str, Any]] = []
    raw = ""
    attempts = model_stage_attempts()
    for attempt in range(1, attempts + 1):
        try:
            result = run_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries, num_predict=max(2048, min(num_predict, _task_num_predict())))
        except RuntimeError as exc:
            retry_reports.append({"attempt": attempt, "status": "backend_error", "error": str(exc)})
            if attempt < attempts:
                continue
            return _task_result(task, "backend_error", prompt, "", started, issues=[str(exc)], retry_reports=retry_reports)
        raw = str(getattr(result, "text", result))
        payload = _extract_json(raw)
        status = "parsed" if isinstance(payload, dict) and payload.get("schema_id") == "analyst_decision_model_v1" else "parse_failed"
        retry_reports.append({"attempt": attempt, "status": status})
        if status == "parsed":
            return _task_result(task, status, prompt, raw, started, payload=payload, retry_reports=retry_reports)
    return _task_result(task, "parse_failed", prompt, raw, started, retry_reports=retry_reports)


def _task_result(
    task: dict[str, Any],
    status: str,
    prompt: str,
    raw: str,
    started: float,
    *,
    payload: dict[str, Any] | None = None,
    issues: list[str] | None = None,
    retry_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "status": status,
        "prompt": prompt,
        "raw": raw,
        "payload": payload or {},
        "duration_seconds": round(time.monotonic() - started, 3),
        "prompt_chars": len(prompt),
        "raw_chars": len(raw),
        "issues": issues or [],
        "attempt_count": len(retry_reports or []),
        "retry_reports": retry_reports or [],
    }


def _rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(context.get("evidence_rows")) if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()]


def _task_size(value: int | None) -> int:
    if value:
        return max(1, int(value))
    try:
        return max(1, int(os.environ.get("ECM_ANALYST_DECISION_MODEL_TASK_SIZE", "4")))
    except ValueError:
        return 4


def _task_num_predict() -> int:
    try:
        return max(2048, int(os.environ.get("ECM_ANALYST_DECISION_MODEL_TASK_NUM_PREDICT", "4096")))
    except ValueError:
        return 4096


def _skeleton_for_rows(context: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = {str(row.get("evidence_item_id") or "") for row in rows}
    selected = []
    for group in _list(context.get("obligation_group_skeleton")):
        if not isinstance(group, dict):
            continue
        evidence_ids = [evidence_id for evidence_id in _string_list(group.get("evidence_item_ids")) if evidence_id in ids]
        if evidence_ids:
            selected.append(
                {
                    "skeleton_group_id": group.get("skeleton_group_id"),
                    "target_memo_role": group.get("target_memo_role"),
                    "primary_obligation_type": group.get("primary_obligation_type"),
                    "evidence_item_ids": evidence_ids,
                }
            )
    return selected


def _hints_for_rows(context: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    ids = {str(row.get("evidence_item_id") or "") for row in rows}
    hints = context.get("model_hints") if isinstance(context.get("model_hints"), dict) else {}
    return {
        "near_duplicate_pairs": [
            row
            for row in _list(hints.get("near_duplicate_pairs"))
            if isinstance(row, dict) and str(row.get("left")) in ids and str(row.get("right")) in ids
        ],
        "similarity_clusters": [
            row
            for row in _list(hints.get("similarity_clusters"))
            if isinstance(row, dict) and any(evidence_id in ids for evidence_id in _string_list(row.get("evidence_item_ids")))
        ],
        "top_central_evidence_item_ids": [evidence_id for evidence_id in _string_list(hints.get("top_central_evidence_item_ids")) if evidence_id in ids],
    }


def _compact_task_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "evidence_item_id": row.get("evidence_item_id"),
        "claim_id": row.get("claim_id"),
        "input_kind": row.get("input_kind"),
        "current_role": row.get("current_role"),
        "adjudicated_memo_use": row.get("adjudicated_memo_use"),
        "adjudicated_answer_relation": row.get("adjudicated_answer_relation"),
        "adjudicated_importance_rank": row.get("adjudicated_importance_rank"),
        "target_answer_option": row.get("target_answer_option"),
        "effect_on_final_answer": row.get("effect_on_final_answer"),
        "tension_type": row.get("tension_type"),
        "decision_contribution": _short_text(str(row.get("decision_contribution") or ""), 260),
        "use_in_reasoning": _short_text(str(row.get("use_in_reasoning") or ""), 100),
        "key_qualifier": _short_text(str(row.get("key_qualifier") or ""), 160),
        "quantity_takeaway": _short_text(str(row.get("quantity_takeaway") or ""), 180),
        "source_weight_note": _short_text(str(row.get("source_weight_note") or ""), 160),
        "misuse_warning": _short_text(str(row.get("misuse_warning") or ""), 180),
        "if_omitted": _short_text(str(row.get("if_omitted") or ""), 180),
        "source_ids": _string_list(row.get("source_ids"))[:4],
        "source_quality": row.get("source_quality") if isinstance(row.get("source_quality"), dict) else {},
        "claim": _short_text(str(row.get("claim") or ""), 320),
        "quantity_values": _string_list(row.get("quantity_values"))[:6],
        "why_it_matters": _short_text(str(row.get("why_it_matters") or ""), 160),
        "failure_condition": _short_text(str(row.get("failure_condition") or ""), 120),
        "existing_warning_codes": _string_list(row.get("existing_warning_codes"))[:4],
    }
    if str(row.get("input_kind") or "") == "candidate_decision_edge":
        compact["relation_contract"] = _relation_contract_for_task(row.get("relation_contract"))
        compact["candidate_pair"] = _candidate_pair_for_task(row.get("candidate_pair"))
        compact["endpoint_claims"] = _endpoint_claims_for_task(row.get("endpoint_claims"))
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _relation_contract_for_task(value: Any) -> dict[str, Any]:
    contract = value if isinstance(value, dict) else {}
    return {
        key: _short_text(str(contract.get(key) or ""), 180)
        for key in ("edge_basis", "source_anchor_a", "source_anchor_b", "why_decision_relevant", "failure_condition")
        if contract.get(key)
    }


def _candidate_pair_for_task(value: Any) -> dict[str, Any]:
    pair = value if isinstance(value, dict) else {}
    return {
        key: pair.get(key)
        for key in ("pair_id", "decision_edge_contract", "reason", "score")
        if pair.get(key) not in (None, "", [], {})
    }


def _endpoint_claims_for_task(value: Any) -> list[dict[str, Any]]:
    rows = []
    for endpoint in _list(value)[:4]:
        if not isinstance(endpoint, dict):
            continue
        rows.append(
            {
                key: _short_text(str(endpoint.get(key) or ""), 180) if key == "claim" else endpoint.get(key)
                for key in ("endpoint", "claim_id", "decision_edge_role", "decision_function", "question_relevance", "claim")
                if endpoint.get(key) not in (None, "", [], {})
            }
        )
    return rows


def _known_ids(context: dict[str, Any], ids: list[str]) -> list[str]:
    known = {str(row.get("evidence_item_id") or "") for row in _rows(context)}
    return [evidence_id for evidence_id in ids if evidence_id in known]


def _stable_group_id(group: dict[str, Any], payload_index: int, group_index: int) -> str:
    text = str(group.get("group_id") or "").strip()
    safe = re.sub(r"[^a-zA-Z0-9_:-]+", "_", text).strip("_")
    return safe or f"analyst_parallel_group_{payload_index:03d}_{group_index:03d}"


def _dedupe_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids = set()
    deduped = []
    for group in sorted(groups, key=lambda row: (int(row.get("importance_rank", 100) or 100), str(row.get("group_id") or ""))):
        group_id = str(group.get("group_id") or "")
        if group_id in seen_ids:
            suffix = len(seen_ids) + 1
            group["group_id"] = f"{group_id}_{suffix:03d}"
        seen_ids.add(str(group.get("group_id") or ""))
        deduped.append(group)
    return deduped


def _schema_safe_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in group.items()
        if key not in {"diagnostic_priority_score", "diagnostic_priority_reasons", "best_adjudicated_importance_rank"}
    }


def _merged_dispositions(context: dict[str, Any], groups: list[dict[str, Any]], model_dispositions: dict[str, dict[str, Any]], covered: set[str]) -> list[dict[str, Any]]:
    group_by_evidence = {
        evidence_id: str(group.get("group_id") or "")
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    rows = []
    for row in _rows(context):
        evidence_id = str(row.get("evidence_item_id") or "")
        if evidence_id in covered:
            rows.append({"evidence_item_id": evidence_id, "disposition": "foreground", "group_id": group_by_evidence.get(evidence_id, ""), "rationale": "Covered by a model-generated evidence group."})
            continue
        model_row = model_dispositions.get(evidence_id, {})
        rows.append(
            {
                "evidence_item_id": evidence_id,
                "disposition": str(model_row.get("disposition") or "background"),
                "group_id": str(model_row.get("group_id") or ""),
                "rationale": str(model_row.get("rationale") or "Not foregrounded by grouped analyst model."),
            }
        )
    return rows


def _merged_memo_relevance_decisions(
    context: dict[str, Any],
    payloads: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    dispositions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    known = {str(row.get("evidence_item_id") or ""): row for row in _rows(context)}
    decisions: dict[str, dict[str, Any]] = {}
    group_by_id = {
        evidence_id: group
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    for payload in payloads:
        for row in _list(payload.get("memo_relevance_decisions")):
            if not isinstance(row, dict):
                continue
            evidence_id = str(row.get("evidence_item_id") or "").strip()
            if evidence_id not in known:
                continue
            decisions[evidence_id] = {
                "evidence_item_id": evidence_id,
                "memo_inclusion": _memo_inclusion_value(row.get("memo_inclusion")),
                "group_id": str(row.get("group_id") or group_by_id.get(evidence_id, {}).get("group_id") or "").strip(),
                "source_ids": _string_list(row.get("source_ids")) or _string_list(known[evidence_id].get("source_ids")),
                "rationale": _short_text(str(row.get("rationale") or "Grouped analyst model relevance decision."), 360),
            }
    disposition_by_id = {str(row.get("evidence_item_id") or ""): row for row in dispositions if isinstance(row, dict)}
    for evidence_id, row in known.items():
        if evidence_id in decisions:
            continue
        group = group_by_id.get(evidence_id, {})
        disposition = disposition_by_id.get(evidence_id, {})
        decisions[evidence_id] = {
            "evidence_item_id": evidence_id,
            "memo_inclusion": _memo_inclusion_from_group_or_disposition(group, disposition),
            "group_id": str(group.get("group_id") or disposition.get("group_id") or "").strip(),
            "source_ids": _string_list(row.get("source_ids")),
            "rationale": _short_text(_memo_inclusion_rationale(group, disposition), 360),
        }
    return list(decisions.values())


def _merged_quantity_relevance_decisions(
    context: dict[str, Any],
    payloads: list[dict[str, Any]],
    memo_relevance_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = {str(row.get("evidence_item_id") or ""): row for row in _rows(context)}
    valid_quantities = {
        evidence_id: set(_string_list(row.get("quantity_values")))
        for evidence_id, row in rows.items()
    }
    decisions: dict[tuple[str, str], dict[str, Any]] = {}
    for payload in payloads:
        for row in _list(payload.get("quantity_relevance_decisions")):
            if not isinstance(row, dict):
                continue
            evidence_id = str(row.get("evidence_item_id") or "").strip()
            quantity = str(row.get("quantity_value") or "").strip()
            if evidence_id not in rows or quantity not in valid_quantities.get(evidence_id, set()):
                continue
            inclusion = _quantity_inclusion_value(row.get("memo_inclusion"))
            decisions[(evidence_id, quantity)] = {
                "evidence_item_id": evidence_id,
                "quantity_value": quantity,
                "memo_inclusion": inclusion,
                "quantity_role": _quantity_role_value(row.get("quantity_role"), inclusion),
                "retention_phrase": _short_text(str(row.get("retention_phrase") or (quantity if inclusion in {"must_use", "supporting_context"} else "")), 220),
                "rationale": _short_text(str(row.get("rationale") or "Grouped analyst model quantity relevance decision."), 360),
            }
    memo_by_id = {str(row.get("evidence_item_id") or ""): row for row in memo_relevance_decisions}
    for evidence_id, row in rows.items():
        for quantity in _string_list(row.get("quantity_values")):
            key = (evidence_id, quantity)
            if key in decisions:
                continue
            memo_inclusion = str(memo_by_id.get(evidence_id, {}).get("memo_inclusion") or "trace_only")
            quantity_inclusion = "supporting_context" if memo_inclusion == "memo_spine" and _row_is_quantity_forward(row) else "trace_only"
            decisions[key] = {
                "evidence_item_id": evidence_id,
                "quantity_value": quantity,
                "memo_inclusion": quantity_inclusion,
                "quantity_role": "supporting_detail" if quantity_inclusion == "supporting_context" else "audit_only",
                "retention_phrase": quantity if quantity_inclusion == "supporting_context" else "",
                "rationale": "Quantity retained by conservative fallback from the analyst evidence relevance decision.",
            }
    return list(decisions.values())


def _memo_inclusion_value(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"memo_spine", "supporting_context", "trace_only", "exclude"} else "trace_only"


def _quantity_inclusion_value(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"must_use", "supporting_context", "trace_only", "exclude"} else "trace_only"


def _quantity_role_value(value: Any, inclusion: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    allowed = {"decision_anchor", "supporting_detail", "study_descriptor", "statistical_detail", "audit_only"}
    if text in allowed:
        return text
    if inclusion == "must_use":
        return "decision_anchor"
    if inclusion == "supporting_context":
        return "supporting_detail"
    return "audit_only"


def _memo_inclusion_from_group_or_disposition(group: dict[str, Any], disposition: dict[str, Any]) -> str:
    role = str(group.get("memo_role") or "").strip()
    if role in {"load_bearing_primary_support", "load_bearing_counterweight", "quantitative_anchor", "decision_crux"}:
        return "memo_spine"
    if role in {"scope_or_applicability", "mechanism_or_context", "needs_human_or_model_review"}:
        return "supporting_context"
    disposition_value = str(disposition.get("disposition") or "").strip()
    if disposition_value == "not_decision_relevant":
        return "exclude"
    return "trace_only"


def _memo_inclusion_rationale(group: dict[str, Any], disposition: dict[str, Any]) -> str:
    if group:
        return str(group.get("rationale") or "Derived from the grouped analyst model evidence role.")
    return str(disposition.get("rationale") or "Not foregrounded by the grouped analyst model.")


def _row_is_quantity_forward(row: dict[str, Any]) -> bool:
    return str(row.get("current_role") or row.get("adjudicated_memo_use") or "").strip() in {
        "quantitative_anchor",
        "load_bearing_primary_support",
        "load_bearing_counterweight",
        "decision_crux",
    }


def _merged_direct_answer(payloads: list[dict[str, Any]]) -> str:
    for payload in payloads:
        text = naturalize_decision_logic_text(str(payload.get("direct_answer") or ""))
        if text and not is_scaffolded_decision_logic_text(text):
            return _short_text(text, 700)
    for payload in payloads:
        logic = naturalize_decision_logic_payload(_dict(payload.get("decision_logic")))
        text = naturalize_decision_logic_text(str(logic.get("bounded_bottom_line") or ""))
        if text and not is_scaffolded_decision_logic_text(text):
            return _short_text(text, 700)
    return ""


def _first_group(groups: list[dict[str, Any]], role: str) -> str:
    for group in groups:
        if group.get("memo_role") == role:
            return str(group.get("proposition") or "").strip()
    return ""


def _merged_confidence(payloads: list[dict[str, Any]]) -> str:
    values = [str(payload.get("confidence") or "") for payload in payloads]
    for value in ("medium", "low", "high", "not_specified"):
        if value in values:
            return value
    return "not_specified"


def _overall_rationale(groups: list[dict[str, Any]], payloads: list[dict[str, Any]]) -> str:
    rationales = [str(payload.get("overall_rationale") or "").strip() for payload in payloads if str(payload.get("overall_rationale") or "").strip()]
    if rationales:
        return _short_text(" ".join(rationales[:4]), 900)
    return ""


def _merged_texts(context: dict[str, Any], payloads: list[dict[str, Any]], key: str) -> list[str]:
    values = [item for payload in payloads for item in _string_list(payload.get(key))]
    if key == "quantitative_anchors":
        values.extend(quantity for row in _rows(context) for quantity in _string_list(row.get("quantity_values")))
    return _dedupe(values)[:20]


def _decision_logic(context: dict[str, Any], groups: list[dict[str, Any]], payloads: list[dict[str, Any]]) -> dict[str, Any]:
    logic_payloads = [naturalize_decision_logic_payload(_dict(payload.get("decision_logic"))) for payload in payloads]
    support = _first_payload_logic_text(logic_payloads, "support_summary") or _first_group(
        groups,
        "load_bearing_primary_support",
    )
    counterweight = _first_payload_logic_text(logic_payloads, "strongest_counterweight") or _first_group(
        groups,
        "load_bearing_counterweight",
    )
    return {
        "bounded_bottom_line": _first_payload_logic_text(logic_payloads, "bounded_bottom_line") or _merged_direct_answer(payloads),
        "support_summary": support,
        "strongest_counterweight": counterweight,
        "counterweight_weighting": _first_payload_logic_text(logic_payloads, "counterweight_weighting"),
        "reconciled_cruxes": _merged_logic_list(
            logic_payloads,
            "reconciled_cruxes",
            [str(group.get("proposition") or "") for group in groups if group.get("memo_role") == "decision_crux"],
            limit=4,
        ),
        "scope_boundaries": _merged_logic_list(
            logic_payloads,
            "scope_boundaries",
            [str(group.get("proposition") or "") for group in groups if group.get("memo_role") == "scope_or_applicability"],
            limit=4,
        ),
        "practical_implications": _merged_logic_list(logic_payloads, "practical_implications", [], limit=6),
        "do_not_overstate": _merged_logic_list(logic_payloads, "do_not_overstate", [], limit=6),
    }


def _argument_plan(groups: list[dict[str, Any]], payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = [row for payload in payloads for row in _list(payload.get("argument_plan")) if isinstance(row, dict)]
    if plan:
        return plan[:10]
    steps = []
    for role, step_id, goal in (
        ("load_bearing_primary_support", "answer_and_support", "State the direct answer and main support."),
        ("load_bearing_counterweight", "counterweight", "Weigh the strongest counterweight against the support."),
        ("scope_or_applicability", "scope", "Bound the answer to the right population or context."),
        ("decision_crux", "crux", "State what would change the answer."),
    ):
        selected = [group for group in groups if group.get("memo_role") == role][:4]
        if selected:
            steps.append(
                {
                    "step_id": step_id,
                    "section": "Decision Brief",
                    "writing_goal": goal,
                    "required_points": [str(group.get("proposition") or "") for group in selected],
                    "evidence_item_ids": [
                        evidence_id
                        for group in selected
                        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
                    ],
                    "transition_from_previous": argument_plan_transition(step_id),
                }
            )
    return steps


def _first_payload_logic_text(logic_payloads: list[dict[str, Any]], key: str) -> str:
    for logic in logic_payloads:
        text = naturalize_decision_logic_text(str(logic.get(key) or ""))
        if text and not is_scaffolded_decision_logic_text(text):
            return _short_text(text, 520)
    return ""


def _merged_logic_list(
    logic_payloads: list[dict[str, Any]],
    key: str,
    fallback: list[str],
    *,
    limit: int,
) -> list[str]:
    values = []
    for logic in logic_payloads:
        values.extend(_string_list(logic.get(key)))
    values.extend(fallback)
    return _dedupe(
        [
            text
            for value in values
            if (text := naturalize_decision_logic_text(str(value or "")))
            and not is_scaffolded_decision_logic_text(text)
        ]
    )[:limit]


def _public_task_report(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in ("task_id", "status", "duration_seconds", "prompt_chars", "raw_chars", "issues", "attempt_count", "retry_reports")}


def _join(texts: list[str], label: str) -> str:
    return f"\n\n--- {label} ---\n\n".join(text for text in texts if text)


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(_repair_json(text))
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(_repair_json(fenced.group(1).strip()))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(_repair_json(text[start : end + 1]))
        except json.JSONDecodeError:
            return {}
    return {}


def _repair_json(text: str) -> str:
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r":\s*null\b", ": []", text)
    return text
