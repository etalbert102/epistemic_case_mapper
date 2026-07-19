from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_logic import naturalize_decision_logic_payload
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_schemas import (
    AnalystDecisionModel,
    build_analyst_decision_model_parse_report,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import run_model_backend


def run_analyst_decision_model_repair(
    *,
    initial_model: dict[str, Any],
    initial_parse_report: dict[str, Any],
    context: dict[str, Any],
    ledger: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
) -> dict[str, Any]:
    repair_packet = _decision_model_repair_packet(initial_parse_report, context)
    if not repair_packet.get("omitted_obligations"):
        return _repair_report("not_needed", initial_parse_report, accepted=False)
    if backend.strip() == "prompt":
        return _repair_report("skipped_prompt_backend", initial_parse_report, accepted=False, issues=["prompt backend cannot run repair"])

    candidate = deepcopy(initial_model)
    prompts: list[str] = []
    raws: list[str] = []
    batch_reports: list[dict[str, Any]] = []
    for batch_index, repair_rows in enumerate(_repair_batches(repair_packet), start=1):
        prompt = build_analyst_decision_model_repair_prompt(
            current_model=candidate,
            repair_rows=repair_rows,
            decision_question=str(context.get("decision_question") or ""),
            batch_index=batch_index,
        )
        prompts.append(prompt)
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                num_predict=num_predict,
            )
        except RuntimeError as exc:
            report = _repair_report("backend_error_kept_initial", initial_parse_report, accepted=False, issues=[str(exc)])
            report["analyst_decision_model_repair_prompt"] = "\n\n---\n\n".join(prompts)
            report["batch_reports"] = batch_reports
            return report
        raws.append(result.text)
        assignment_payload = _extract_json(result.text)
        candidate, batch_report = _apply_decision_model_assignments(candidate, assignment_payload, repair_rows)
        batch_reports.append(batch_report)

    candidate_parse_report = build_analyst_decision_model_parse_report(candidate, ledger, retention_obligations=context.get("retention_obligations"))
    report = _repair_report(
        "candidate_invalid_kept_initial" if not candidate_parse_report.get("valid") else "candidate_evaluated",
        candidate_parse_report,
        accepted=False,
    )
    report["analyst_decision_model_repair_prompt"] = "\n\n---\n\n".join(prompts)
    report["analyst_decision_model_repair_raw"] = "\n\n---\n\n".join(raws)
    report["analyst_decision_model_repair_parse_report"] = candidate_parse_report
    report["batch_reports"] = batch_reports
    report["batch_count"] = len(batch_reports)
    if not candidate_parse_report.get("valid"):
        return report

    candidate = AnalystDecisionModel.model_validate(candidate).model_dump()
    candidate["decision_logic"] = naturalize_decision_logic_payload(_dict(candidate.get("decision_logic")))
    before_score = _decision_model_warning_score(initial_parse_report)
    after_score = _decision_model_warning_score(candidate_parse_report)
    report["before_warning_score"] = before_score
    report["after_warning_score"] = after_score
    if after_score >= before_score:
        report["status"] = "no_improvement_kept_initial"
        report["issues"] = ["repair did not reduce decision-model warning score"]
        return report
    report["status"] = "accepted"
    report["accepted"] = True
    report["analyst_decision_model"] = candidate
    report["analyst_decision_model_parse_report"] = candidate_parse_report
    report["issues"] = []
    return report


def compact_decision_model_repair_report(repair: dict[str, Any]) -> dict[str, Any]:
    return {
        key: repair.get(key)
        for key in (
            "schema_id",
            "status",
            "accepted",
            "parse_status",
            "valid",
            "covered_evidence_item_count",
            "missing_accounting_count",
            "obligation_omission_count",
            "before_warning_score",
            "after_warning_score",
            "batch_count",
            "issues",
        )
        if key in repair
    }


def build_analyst_decision_model_repair_prompt(
    *,
    current_model: dict[str, Any],
    repair_rows: list[dict[str, Any]],
    decision_question: str,
    batch_index: int = 1,
) -> str:
    packet = {
        "decision_question": decision_question,
        "batch_index": batch_index,
        "task": [
            "Assign each repair_row to the current analyst decision model.",
            "Return assignments only; deterministic code will apply them to the current model.",
            "Prefer add_to_group when an existing group already covers the proposition.",
            "Use create_group only when the row would distort every existing group.",
            "Use disposition only when the row should stay background, not decision relevant, or needs review.",
            "Keep support, counterweight, crux, quantity, and scope evidence analytically distinguishable when choosing a group.",
            "Return strict JSON only.",
        ],
        "current_model_summary": _decision_model_assignment_summary(current_model),
        "repair_rows": _repair_rows_for_model(repair_rows),
        "required_output_schema": {
            "schema_id": "analyst_decision_group_assignments_v1",
            "assignments": [
                {
                    "evidence_item_id": "one evidence_item_id from repair_rows",
                    "action": "add_to_group | create_group | disposition",
                    "target_group_id": "existing group_id when action is add_to_group",
                    "new_group": {
                        "group_id": "stable new group label when action is create_group",
                        "proposition": "decision-relevant proposition",
                        "memo_role": "load_bearing_primary_support | load_bearing_counterweight | quantitative_anchor | scope_or_applicability | decision_crux | mechanism_or_context | background_only | needs_human_or_model_review",
                        "importance_rank": "integer 1-100",
                        "rationale": "why this group matters",
                        "evidence_strength": "brief strength assessment",
                        "answer_impact": "how this group changes or bounds the answer",
                        "uncertainty_type": "measurement, external validity, confounding, missing evidence, implementation, none, or other",
                        "applicability_limits": ["scope/population/context limits"],
                        "conflict_note": "conflict or tension, if any",
                    },
                    "disposition": "background | not_decision_relevant | needs_review",
                    "rationale": "why this assignment is appropriate",
                }
            ],
        },
    }
    return (
        "You are assigning omitted evidence rows into an existing analyst decision model.\n"
        "Make only semantic assignment choices; deterministic code will perform the edit.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def _decision_model_repair_packet(parse_report: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    omitted = {
        obligation_type: _string_list(ids)
        for obligation_type, ids in _dict(parse_report.get("obligation_omissions")).items()
        if _string_list(ids)
    }
    missing_accounting_ids = set(_string_list(parse_report.get("missing_accounting_ids")))
    all_omitted_ids = _dedupe([evidence_id for ids in omitted.values() for evidence_id in ids])
    row_lookup = {str(row.get("evidence_item_id") or ""): row for row in _list(context.get("evidence_rows")) if isinstance(row, dict)}
    return {
        "schema_id": "analyst_decision_model_repair_packet_v1",
        "omitted_obligations": {
            obligation_type: [_repair_context_row(row_lookup.get(evidence_id, {}), obligation_type) for evidence_id in ids]
            for obligation_type, ids in omitted.items()
        },
        "missing_accounting_rows": [
            _repair_context_row(row_lookup.get(evidence_id, {}), "missing_accounting")
            for evidence_id in sorted(missing_accounting_ids - set(all_omitted_ids))
        ][:12],
    }


def _repair_rows_for_model(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in row.items()
            if key not in {"source_label", "source_labels", "display_label", "citation_label"}
        }
        for row in rows
    ]


def _repair_batches(repair_packet: dict[str, Any]) -> list[list[dict[str, Any]]]:
    rows = _dedupe_repair_rows(
        [
            row
            for values in _dict(repair_packet.get("omitted_obligations")).values()
            for row in _list(values)
            if isinstance(row, dict)
        ]
        + [row for row in _list(repair_packet.get("missing_accounting_rows")) if isinstance(row, dict)]
    )
    if not rows:
        return []
    try:
        batch_size = max(1, int(os.environ.get("ECM_ANALYST_DECISION_REPAIR_BATCH_SIZE", "8")))
    except ValueError:
        batch_size = 8
    return [rows[index : index + batch_size] for index in range(0, len(rows), batch_size)]


def _dedupe_repair_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        if not evidence_id:
            continue
        if evidence_id not in merged:
            merged[evidence_id] = dict(row)
            merged[evidence_id]["obligation_types"] = []
            order.append(evidence_id)
        obligation = str(row.get("obligation_type") or "").strip()
        if obligation:
            merged[evidence_id]["obligation_types"] = _dedupe([*merged[evidence_id].get("obligation_types", []), obligation])
        for key, value in row.items():
            if key == "obligation_type":
                continue
            if value not in ("", None, [], {}) and merged[evidence_id].get(key) in ("", None, [], {}):
                merged[evidence_id][key] = value
    return [merged[evidence_id] for evidence_id in order]


def _repair_context_row(row: dict[str, Any], obligation_type: str) -> dict[str, Any]:
    return _drop_empty(
        {
            "evidence_item_id": row.get("evidence_item_id"),
            "obligation_type": obligation_type,
            "claim_id": row.get("claim_id"),
            "current_role": row.get("current_role"),
            "adjudicated_memo_use": row.get("adjudicated_memo_use"),
            "decision_contribution": _short_text(str(row.get("decision_contribution") or ""), 260),
            "use_in_reasoning": _short_text(str(row.get("use_in_reasoning") or ""), 100),
            "key_qualifier": _short_text(str(row.get("key_qualifier") or ""), 180),
            "quantity_takeaway": _short_text(str(row.get("quantity_takeaway") or ""), 180),
            "source_weight_note": _short_text(str(row.get("source_weight_note") or ""), 180),
            "misuse_warning": _short_text(str(row.get("misuse_warning") or ""), 180),
            "if_omitted": _short_text(str(row.get("if_omitted") or ""), 180),
            "quantity_values": row.get("quantity_values", []),
            "source_ids": row.get("source_ids", []),
            "claim": _short_text(str(row.get("claim") or ""), 420),
            "source_excerpt": _short_text(str(row.get("source_excerpt") or ""), 260),
            "why_it_matters": _short_text(str(row.get("why_it_matters") or ""), 220),
            "relation_context": row.get("relation_context", [])[:3] if isinstance(row.get("relation_context"), list) else [],
        }
    )


def _decision_model_assignment_summary(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "analyst_decision_model_assignment_summary_v1",
        "direct_answer": model.get("direct_answer"),
        "confidence": model.get("confidence"),
        "evidence_groups": [
            {
                "group_id": group.get("group_id"),
                "memo_role": group.get("memo_role"),
                "importance_rank": group.get("importance_rank"),
                "proposition": group.get("proposition"),
                "covered_evidence_item_ids": group.get("covered_evidence_item_ids", []),
                "answer_impact": group.get("answer_impact"),
                "conflict_note": group.get("conflict_note"),
            }
            for group in _list(model.get("evidence_groups"))
            if isinstance(group, dict)
        ],
    }


def _apply_decision_model_assignments(
    model: dict[str, Any],
    assignment_payload: Any,
    repair_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = deepcopy(model)
    known_ids = {str(row.get("evidence_item_id") or "") for row in repair_rows}
    group_ids = {str(group.get("group_id") or "") for group in _list(updated.get("evidence_groups")) if isinstance(group, dict)}
    report = {
        "schema_id": "analyst_decision_assignment_batch_report_v1",
        "requested_evidence_item_ids": sorted(known_ids),
        "assignment_count": 0,
        "applied_count": 0,
        "ignored_count": 0,
        "issues": [],
    }
    if isinstance(assignment_payload, dict) and not assignment_payload.get("schema_id") and isinstance(assignment_payload.get("assignments"), list):
        assignment_payload["schema_id"] = "analyst_decision_group_assignments_v1"
    if not isinstance(assignment_payload, dict) or assignment_payload.get("schema_id") != "analyst_decision_group_assignments_v1":
        report["issues"].append("invalid_assignment_schema")
        return updated, report
    assignments = [row for row in _list(assignment_payload.get("assignments")) if isinstance(row, dict)]
    report["assignment_count"] = len(assignments)
    seen_assignment_ids: set[str] = set()
    for assignment in assignments:
        evidence_id = str(assignment.get("evidence_item_id") or "").strip()
        if evidence_id not in known_ids or evidence_id in seen_assignment_ids:
            report["ignored_count"] += 1
            continue
        seen_assignment_ids.add(evidence_id)
        applied = _apply_assignment(updated, assignment, evidence_id, group_ids)
        if applied:
            report["applied_count"] += 1
        else:
            report["ignored_count"] += 1
    missing = sorted(known_ids - seen_assignment_ids)
    if missing:
        report["missing_assignment_ids"] = missing
        report["issues"].append("missing_assignments")
    return updated, report


def _apply_assignment(updated: dict[str, Any], assignment: dict[str, Any], evidence_id: str, group_ids: set[str]) -> bool:
    action = str(assignment.get("action") or "").strip()
    if action == "add_to_group":
        group_id = str(assignment.get("target_group_id") or "").strip()
        if group_id in group_ids:
            applied = _add_evidence_id_to_group(updated, evidence_id, group_id)
            _remove_disposition_for_evidence(updated, evidence_id)
            return applied
    if action == "create_group":
        group = _group_from_assignment(assignment, evidence_id, group_ids)
        if group:
            updated.setdefault("evidence_groups", []).append(group)
            group_ids.add(str(group.get("group_id") or ""))
            _remove_disposition_for_evidence(updated, evidence_id)
            return True
    if action == "disposition":
        disposition = _disposition_from_assignment(assignment, evidence_id)
        if disposition:
            _upsert_disposition(updated, disposition)
            return True
    return False


def _add_evidence_id_to_group(model: dict[str, Any], evidence_id: str, group_id: str) -> bool:
    for group in _list(model.get("evidence_groups")):
        if not isinstance(group, dict) or str(group.get("group_id") or "") != group_id:
            continue
        group["covered_evidence_item_ids"] = _dedupe([*_string_list(group.get("covered_evidence_item_ids")), evidence_id])
        return True
    return False


def _group_from_assignment(assignment: dict[str, Any], evidence_id: str, known_group_ids: set[str]) -> dict[str, Any]:
    raw = _dict(assignment.get("new_group"))
    group_id = _stable_new_group_id(str(raw.get("group_id") or ""), known_group_ids)
    proposition = _short_text(str(raw.get("proposition") or assignment.get("rationale") or evidence_id), 520)
    memo_role = str(raw.get("memo_role") or "mechanism_or_context").strip()
    if memo_role not in _allowed_decision_memo_roles():
        memo_role = "mechanism_or_context"
    try:
        importance_rank = max(1, min(100, int(raw.get("importance_rank") or 100)))
    except (TypeError, ValueError):
        importance_rank = 100
    return {
        "group_id": group_id,
        "proposition": proposition,
        "memo_role": memo_role,
        "importance_rank": importance_rank,
        "covered_evidence_item_ids": [evidence_id],
        "rationale": _short_text(str(raw.get("rationale") or assignment.get("rationale") or "Created during targeted omission repair."), 520),
        "evidence_strength": str(raw.get("evidence_strength") or ""),
        "answer_impact": str(raw.get("answer_impact") or ""),
        "uncertainty_type": str(raw.get("uncertainty_type") or ""),
        "applicability_limits": _string_list(raw.get("applicability_limits")),
        "conflict_note": str(raw.get("conflict_note") or ""),
    }


def _stable_new_group_id(candidate: str, known_group_ids: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", candidate.strip().lower()) or "repaired_evidence_group"
    base = re.sub(r"_+", "_", base).strip("_") or "repaired_evidence_group"
    group_id = base
    index = 2
    while group_id in known_group_ids:
        group_id = f"{base}_{index}"
        index += 1
    return group_id


def _disposition_from_assignment(assignment: dict[str, Any], evidence_id: str) -> dict[str, str]:
    disposition = str(assignment.get("disposition") or "").strip()
    if disposition not in {"background", "not_decision_relevant", "needs_review"}:
        disposition = "background"
    return {
        "evidence_item_id": evidence_id,
        "disposition": disposition,
        "group_id": "",
        "rationale": _short_text(str(assignment.get("rationale") or "Dispositioned during targeted omission repair."), 360),
    }


def _upsert_disposition(model: dict[str, Any], disposition: dict[str, str]) -> None:
    rows = [row for row in _list(model.get("evidence_dispositions")) if isinstance(row, dict)]
    evidence_id = str(disposition.get("evidence_item_id") or "")
    updated = False
    for row in rows:
        if str(row.get("evidence_item_id") or "") == evidence_id:
            row.update(disposition)
            updated = True
            break
    if not updated:
        rows.append(disposition)
    model["evidence_dispositions"] = rows


def _remove_disposition_for_evidence(model: dict[str, Any], evidence_id: str) -> None:
    model["evidence_dispositions"] = [
        row
        for row in _list(model.get("evidence_dispositions"))
        if not isinstance(row, dict) or str(row.get("evidence_item_id") or "") != evidence_id
    ]


def _allowed_decision_memo_roles() -> set[str]:
    return {
        "load_bearing_primary_support",
        "load_bearing_counterweight",
        "quantitative_anchor",
        "scope_or_applicability",
        "decision_crux",
        "mechanism_or_context",
        "background_only",
        "needs_human_or_model_review",
    }


def _decision_model_warning_score(parse_report: dict[str, Any]) -> int:
    omissions = sum(len(_string_list(ids)) for ids in _dict(parse_report.get("obligation_omissions")).values())
    missing = len(_string_list(parse_report.get("missing_accounting_ids")))
    fatal = 1000 if not parse_report.get("valid") else 0
    issue_penalty = len(_list(parse_report.get("issues")))
    covered = int(parse_report.get("covered_evidence_item_count") or 0)
    return fatal + omissions * 100 + missing * 10 + issue_penalty - covered


def _repair_report(
    status: str,
    parse_report: dict[str, Any],
    *,
    accepted: bool,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_id": "analyst_decision_model_repair_report_v1",
        "status": status,
        "accepted": accepted,
        "parse_status": parse_report.get("status"),
        "valid": parse_report.get("valid", False),
        "covered_evidence_item_count": parse_report.get("covered_evidence_item_count", 0),
        "missing_accounting_count": len(_string_list(parse_report.get("missing_accounting_ids"))),
        "obligation_omission_count": sum(len(_string_list(ids)) for ids in _dict(parse_report.get("obligation_omissions")).values()),
        "issues": issues or [],
    }


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


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if value not in ("", None, [], {})
    }
