from __future__ import annotations

import os
import re
import time
from typing import Any, Callable

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_group_schema import schema_safe_decision_group
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_model_global_task_prompts import (
    build_global_analyst_task_prompt,
    build_global_analyst_tasks,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_balanced_answer_frame import split_bluf_answer_hierarchy
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_model_global_task_runner import (
    public_global_task_report,
    run_global_analyst_task_calls,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_logic import (
    argument_plan_transition,
    content_based_counterweight_weighting,
    naturalize_decision_logic_payload,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_diagnosticity import apply_decision_diagnostic_ranking
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_hierarchy import normalize_source_hierarchy
from epistemic_case_mapper.model_backends import model_parallelism


def should_use_global_task_analyst_decision_model(context: dict[str, Any]) -> bool:
    mode = str(os.environ.get("ECM_ANALYST_DECISION_MODEL_MODE", "global_tasks")).strip().lower()
    if mode in {"row_sharded", "parallel_rows", "legacy_parallel"}:
        return False
    if mode in {"global_tasks", "global", "task_specific"}:
        return len(_rows(context)) > _threshold()
    return len(_rows(context)) > _threshold()


def run_global_task_analyst_decision_model(
    *,
    context: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
    run_backend: Callable[..., Any],
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    tasks = build_global_analyst_tasks(context)
    _emit_progress(
        progress,
        "analyst_decision_model_global_tasks",
        "started",
        {
            "task_count": len(tasks),
            "row_count": len(_rows(context)),
            "parallelism": model_parallelism(backend),
        },
    )
    task_results = run_global_analyst_task_calls(
        tasks,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        num_predict=num_predict,
        run_backend=run_backend,
        progress=progress,
    )
    payload = build_analyst_decision_model_from_global_tasks(context, task_results)
    _emit_progress(
        progress,
        "analyst_decision_model_global_tasks",
        "completed",
        {
            "task_count": len(tasks),
            "parsed_count": sum(1 for row in task_results if row.get("status") == "parsed"),
            "failed_count": sum(1 for row in task_results if row.get("status") != "parsed"),
            "wall_seconds": round(time.monotonic() - started, 3),
        },
    )
    return {
        "payload": payload,
        "prompt": _join([str(row.get("prompt") or "") for row in task_results], "global analyst task prompt"),
        "raw": _join([str(row.get("raw") or "") for row in task_results], "global analyst task raw"),
        "report": {
            "schema_id": "global_task_analyst_decision_model_report_v1",
            "method": "task_specific_global_analyst_decision_model",
            "task_count": len(tasks),
            "parsed_count": sum(1 for row in task_results if row.get("status") == "parsed"),
            "failed_count": sum(1 for row in task_results if row.get("status") != "parsed"),
            "parallelism": model_parallelism(backend),
            "wall_seconds": round(time.monotonic() - started, 3),
            "task_reports": [public_global_task_report(row) for row in task_results],
            "context_mode": "task_specific",
        },
    }


def build_analyst_decision_model_from_global_tasks(
    context: dict[str, Any],
    task_results: list[dict[str, Any]],
) -> dict[str, Any]:
    payloads = {
        str(result.get("task_id") or ""): _dict(result.get("payload"))
        for result in task_results
        if result.get("status") == "parsed"
    }
    answer_frame = _dict(payloads.get("answer_frame"))
    reconciliation = _dict(payloads.get("evidence_reconciliation"))
    evidence_roles = _roles_from_reconciliation(context, reconciliation)
    if not evidence_roles:
        evidence_roles = _valid_evidence_roles(context, _list(_dict(payloads.get("evidence_roles")).get("evidence_roles")))
    if not evidence_roles:
        evidence_roles = _baseline_evidence_roles(context)
    quantity_decisions = _valid_quantity_decisions(context, _list(_dict(payloads.get("quantity_plan")).get("quantity_decisions")))
    source_hierarchy, source_report = normalize_source_hierarchy(
        _dict(payloads.get("source_hierarchy")),
        allowed_source_ids=_context_source_ids(context),
    )
    source_weight_judgments = _valid_source_weight_judgments(
        context,
        _list(_dict(payloads.get("source_weighting_guidance")).get("source_weight_judgments")),
    )
    if not source_weight_judgments:
        source_weight_judgments = _source_weight_judgments_from_hierarchy(context, source_hierarchy)
    blueprint = _dict(payloads.get("argument_blueprint"))
    groups = _groups_from_global_tasks(context, answer_frame, evidence_roles, blueprint, reconciliation)
    groups, _ranking_guard = apply_decision_diagnostic_ranking(groups, _rows(context))
    groups = [schema_safe_decision_group(group) for group in groups]
    covered = {
        evidence_id
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    dispositions = _dispositions_from_roles(context, groups, evidence_roles, covered)
    memo_relevance = _memo_relevance_from_roles(context, groups, evidence_roles, dispositions)
    quantity_relevance = _quantity_relevance_from_decisions(context, quantity_decisions, memo_relevance)
    answer_hierarchy = _answer_hierarchy(answer_frame, context)
    return {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": str(context.get("decision_question") or ""),
        "direct_answer": answer_hierarchy["direct_answer"],
        "primary_answer": answer_hierarchy["primary_answer"],
        "secondary_detail": answer_hierarchy["secondary_detail"],
        "secondary_detail_type": answer_hierarchy["secondary_detail_type"],
        "full_direct_answer": answer_hierarchy["full_direct_answer"],
        "confidence": _confidence(answer_frame.get("confidence")),
        "overall_rationale": _overall_rationale(answer_frame, source_hierarchy, blueprint),
        "evidence_groups": groups,
        "evidence_dispositions": dispositions,
        "memo_relevance_decisions": memo_relevance,
        "quantity_relevance_decisions": quantity_relevance,
        "source_hierarchy": source_hierarchy,
        "source_hierarchy_report": source_report,
        "source_weight_judgments": source_weight_judgments,
        "source_weight_judgment_report": _source_weight_judgment_report(context, source_weight_judgments),
        "quantitative_anchors": _quantity_anchors(quantity_relevance),
        "what_would_change_the_answer": _what_would_change(answer_frame, evidence_roles),
        "decision_logic": _decision_logic(answer_frame, groups, evidence_roles, source_hierarchy),
        "argument_plan": _argument_plan_from_blueprint(blueprint, groups),
    }


def _answer_hierarchy(answer_frame: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    direct = _short_text(answer_frame.get("best_answer") or _stable_answer(context), 700)
    split = split_bluf_answer_hierarchy(direct)
    primary = _short_text(answer_frame.get("primary_answer") or split["primary_answer"], 520)
    secondary = _short_text(answer_frame.get("secondary_detail") or split["secondary_detail"], 420)
    secondary_type = str(answer_frame.get("secondary_detail_type") or split["secondary_detail_type"] or "").strip()
    if secondary_type == "none":
        secondary_type = ""
    return {
        "direct_answer": direct,
        "primary_answer": primary,
        "secondary_detail": secondary,
        "secondary_detail_type": secondary_type,
        "full_direct_answer": direct if secondary else "",
    }


def _groups_from_global_tasks(
    context: dict[str, Any],
    answer_frame: dict[str, Any],
    evidence_roles: list[dict[str, Any]],
    blueprint: dict[str, Any],
    reconciliation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    groups.extend(_reconciliation_groups(context, _dict(reconciliation)))
    groups.extend(_answer_frame_groups(context, answer_frame))
    groups.extend(_blueprint_groups(context, blueprint, evidence_roles))
    groups.extend(_role_groups_for_uncovered(context, evidence_roles, groups))
    return _dedupe_groups(groups)


def _reconciliation_groups(context: dict[str, Any], reconciliation: dict[str, Any]) -> list[dict[str, Any]]:
    groups = []
    for index, row in enumerate(_list(reconciliation.get("groups")), start=1):
        if not isinstance(row, dict):
            continue
        evidence_ids = _valid_ids(context, _string_list(row.get("evidence_item_ids") or row.get("covered_evidence_item_ids")))
        if not evidence_ids:
            continue
        role = _memo_role_from_decision_role(_decision_role(row.get("role") or row.get("decision_role")), "memo_spine")
        relation = _answer_relation(row.get("answer_relation"))
        groups.append(
            _group(
                group_id=f"reconcile_{_safe_id(row.get('group_id') or index)}",
                proposition=str(row.get("proposition") or ""),
                role=role,
                relation=relation,
                evidence_ids=evidence_ids,
                rationale=str(row.get("rationale") or row.get("qualifier") or "Global reconciliation group."),
                rank=_priority_band_rank(row.get("priority_band"), index),
                applicability_limits=_string_list(row.get("qualifier")),
            )
        )
    return groups


def _answer_frame_groups(context: dict[str, Any], answer_frame: dict[str, Any]) -> list[dict[str, Any]]:
    groups = []
    for index, row in enumerate(_list(answer_frame.get("main_answer_drivers")), start=1):
        groups.append(
            _group(
                group_id=f"answer_driver_{index:03d}",
                proposition=_reason_or_claim(context, row, fallback="Primary evidence supports the bounded answer."),
                role="load_bearing_primary_support",
                relation="supports_answer",
                evidence_ids=_valid_ids(context, _string_list(_dict(row).get("evidence_item_ids"))),
                rationale=str(_dict(row).get("reason") or ""),
                rank=index,
            )
        )
    for index, row in enumerate(_list(answer_frame.get("main_counterweights")), start=1):
        groups.append(
            _group(
                group_id=f"counterweight_{index:03d}",
                proposition=_reason_or_claim(context, row, fallback="Counterweight evidence bounds or weakens the answer."),
                role="load_bearing_counterweight",
                relation="challenges_answer",
                evidence_ids=_valid_ids(context, _string_list(_dict(row).get("evidence_item_ids"))),
                rationale=str(_dict(row).get("reason") or ""),
                rank=20 + index,
            )
        )
    return [group for group in groups if group.get("covered_evidence_item_ids")]


def _blueprint_groups(context: dict[str, Any], blueprint: dict[str, Any], evidence_roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    role_by_id = {str(row.get("evidence_item_id") or ""): row for row in evidence_roles}
    groups = []
    for index, row in enumerate(_list(blueprint.get("section_plan")), start=1):
        if not isinstance(row, dict):
            continue
        evidence_ids = _valid_ids(context, _string_list(row.get("must_use_evidence_item_ids")))
        if not evidence_ids:
            continue
        role = _dominant_memo_role([role_by_id.get(evidence_id, {}) for evidence_id in evidence_ids])
        relation = _dominant_answer_relation([role_by_id.get(evidence_id, {}) for evidence_id in evidence_ids])
        groups.append(
            _group(
                group_id=f"argument_{_safe_id(row.get('section_id') or index)}",
                proposition=str(row.get("core_claim") or row.get("heading") or ""),
                role=role,
                relation=relation,
                evidence_ids=evidence_ids,
                rationale=str(row.get("section_job") or row.get("source_weighting_move") or ""),
                rank=40 + index,
                applicability_limits=[],
            )
        )
    return groups


def _role_groups_for_uncovered(context: dict[str, Any], evidence_roles: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    covered = {
        evidence_id
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    by_bucket: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    rows_by_id = {str(row.get("evidence_item_id") or ""): row for row in _rows(context)}
    for role_row in evidence_roles:
        evidence_id = str(role_row.get("evidence_item_id") or "")
        if evidence_id in covered:
            continue
        inclusion = _memo_inclusion(role_row.get("memo_inclusion"))
        if inclusion in {"exclude", "trace_only"}:
            continue
        bucket = (
            _decision_role(role_row.get("decision_role")),
            _answer_relation(role_row.get("answer_relation")),
            inclusion,
        )
        by_bucket.setdefault(bucket, []).append(role_row)
    groups_out = []
    for index, ((decision_role, relation, inclusion), rows) in enumerate(sorted(by_bucket.items()), start=1):
        evidence_ids = [str(row.get("evidence_item_id") or "") for row in rows if rows_by_id.get(str(row.get("evidence_item_id") or ""))]
        if not evidence_ids:
            continue
        claims = [str(rows_by_id[evidence_id].get("claim") or "") for evidence_id in evidence_ids[:3]]
        groups_out.append(
            _group(
                group_id=f"{decision_role}_{inclusion}_{index:03d}",
                proposition=_short_text("; ".join(claims), 620),
                role=_memo_role_from_decision_role(decision_role, inclusion),
                relation=relation,
                evidence_ids=evidence_ids,
                rationale=_short_text("; ".join(str(row.get("rationale") or "") for row in rows[:3]), 520),
                rank=60 + index,
            )
        )
    return groups_out


def _group(
    *,
    group_id: str,
    proposition: str,
    role: str,
    relation: str,
    evidence_ids: list[str],
    rationale: str,
    rank: int,
    applicability_limits: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "proposition": _short_text(proposition, 720),
        "memo_role": role,
        "answer_relation": relation,
        "target_answer_option": "",
        "effect_on_final_answer": _effect_for_relation(relation),
        "tension_type": "none",
        "importance_rank": rank,
        "covered_evidence_item_ids": _dedupe(evidence_ids),
        "rationale": _short_text(rationale, 520),
        "evidence_strength": "",
        "answer_impact": _answer_impact_for_relation(relation),
        "uncertainty_type": "none",
        "applicability_limits": applicability_limits or [],
        "conflict_note": "",
    }


def _dispositions_from_roles(
    context: dict[str, Any],
    groups: list[dict[str, Any]],
    evidence_roles: list[dict[str, Any]],
    covered: set[str],
) -> list[dict[str, Any]]:
    role_by_id = {str(row.get("evidence_item_id") or ""): row for row in evidence_roles}
    group_by_id = {
        evidence_id: str(group.get("group_id") or "")
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    rows = []
    for row in _rows(context):
        evidence_id = str(row.get("evidence_item_id") or "")
        role_row = role_by_id.get(evidence_id, {})
        inclusion = _memo_inclusion(role_row.get("memo_inclusion"))
        rows.append(
            {
                "evidence_item_id": evidence_id,
                "disposition": "foreground" if evidence_id in covered else _disposition_from_inclusion(inclusion),
                "group_id": group_by_id.get(evidence_id, ""),
                "rationale": _short_text(role_row.get("rationale") or "Global analyst task evidence disposition.", 360),
            }
        )
    return rows


def _memo_relevance_from_roles(
    context: dict[str, Any],
    groups: list[dict[str, Any]],
    evidence_roles: list[dict[str, Any]],
    dispositions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    role_by_id = {str(row.get("evidence_item_id") or ""): row for row in evidence_roles}
    group_by_id = {
        evidence_id: str(group.get("group_id") or "")
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    disposition_by_id = {str(row.get("evidence_item_id") or ""): row for row in dispositions}
    result = []
    for row in _rows(context):
        evidence_id = str(row.get("evidence_item_id") or "")
        role_row = role_by_id.get(evidence_id, {})
        result.append(
            {
                "evidence_item_id": evidence_id,
                "memo_inclusion": _memo_inclusion(role_row.get("memo_inclusion")),
                "group_id": group_by_id.get(evidence_id) or str(disposition_by_id.get(evidence_id, {}).get("group_id") or ""),
                "source_ids": _string_list(row.get("source_ids")),
                "rationale": _short_text(role_row.get("rationale") or "Global analyst task memo relevance decision.", 360),
            }
        )
    return result


def _quantity_relevance_from_decisions(
    context: dict[str, Any],
    quantity_decisions: list[dict[str, Any]],
    memo_relevance: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = {str(row.get("evidence_item_id") or ""): row for row in _rows(context)}
    valid_quantities = {evidence_id: set(_string_list(row.get("quantity_values"))) for evidence_id, row in rows.items()}
    decisions: dict[tuple[str, str], dict[str, Any]] = {}
    for row in quantity_decisions:
        evidence_id = str(row.get("evidence_item_id") or "")
        quantity = str(row.get("quantity_value") or "")
        if evidence_id not in rows or quantity not in valid_quantities.get(evidence_id, set()):
            continue
        inclusion = _quantity_inclusion(row.get("memo_inclusion"))
        decisions[(evidence_id, quantity)] = {
            "evidence_item_id": evidence_id,
            "quantity_value": quantity,
            "memo_inclusion": inclusion,
            "quantity_role": _quantity_role(row.get("quantity_role"), inclusion),
            "retention_phrase": _short_text(row.get("retention_phrase") or (quantity if inclusion in {"must_use", "supporting_context"} else ""), 220),
            "rationale": _short_text(row.get("rationale") or "Global analyst task quantity relevance decision.", 360),
        }
    memo_by_id = {str(row.get("evidence_item_id") or ""): row for row in memo_relevance}
    for evidence_id, source_row in rows.items():
        for quantity in _string_list(source_row.get("quantity_values")):
            if (evidence_id, quantity) in decisions:
                continue
            memo_inclusion = str(memo_by_id.get(evidence_id, {}).get("memo_inclusion") or "trace_only")
            inclusion = "supporting_context" if memo_inclusion == "memo_spine" and _row_is_quantity_forward(source_row) else "trace_only"
            decisions[(evidence_id, quantity)] = {
                "evidence_item_id": evidence_id,
                "quantity_value": quantity,
                "memo_inclusion": inclusion,
                "quantity_role": "supporting_detail" if inclusion == "supporting_context" else "audit_only",
                "retention_phrase": quantity if inclusion == "supporting_context" else "",
                "rationale": "Quantity retained by conservative accounting from global analyst evidence relevance.",
            }
    return list(decisions.values())


def _valid_evidence_roles(context: dict[str, Any], rows: list[Any]) -> list[dict[str, Any]]:
    known = {str(row.get("evidence_item_id") or "") for row in _rows(context)}
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or "")
        if evidence_id not in known:
            continue
        result.append(
            {
                "evidence_item_id": evidence_id,
                "memo_inclusion": _memo_inclusion(row.get("memo_inclusion")),
                "decision_role": _decision_role(row.get("decision_role")),
                "answer_relation": _answer_relation(row.get("answer_relation")),
                "priority_rank": _rank(row.get("priority_rank")),
                "rationale": _short_text(row.get("rationale"), 420),
            }
        )
    return result


def _roles_from_reconciliation(context: dict[str, Any], reconciliation: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = {row["evidence_item_id"]: row for row in _baseline_evidence_roles(context)}
    if not reconciliation:
        return list(baseline.values())
    known = set(baseline)
    for group in _list(reconciliation.get("groups")):
        if not isinstance(group, dict):
            continue
        role = _decision_role(group.get("role") or group.get("decision_role"))
        relation = _answer_relation(group.get("answer_relation"))
        inclusion = "memo_spine" if str(group.get("priority_band") or "").strip().lower() == "high" else "supporting_context"
        rationale = _short_text(group.get("rationale") or group.get("proposition"), 420)
        for evidence_id in _valid_ids(context, _string_list(group.get("evidence_item_ids") or group.get("covered_evidence_item_ids"))):
            current = dict(baseline.get(evidence_id, {}))
            current.update(
                {
                    "evidence_item_id": evidence_id,
                    "memo_inclusion": _stronger_inclusion(current.get("memo_inclusion"), inclusion),
                    "decision_role": role,
                    "answer_relation": relation,
                    "priority_rank": min(_rank(current.get("priority_rank")), _priority_band_rank(group.get("priority_band"), 50)),
                    "rationale": rationale or current.get("rationale") or "Global reconciliation grouping.",
                }
            )
            baseline[evidence_id] = current
    for override in _list(reconciliation.get("overrides")):
        if not isinstance(override, dict):
            continue
        evidence_id = str(override.get("evidence_item_id") or "").strip()
        if evidence_id not in known:
            continue
        current = dict(baseline.get(evidence_id, {}))
        current.update(
            {
                "memo_inclusion": _memo_inclusion(override.get("memo_inclusion") or current.get("memo_inclusion")),
                "decision_role": _decision_role(override.get("decision_role") or current.get("decision_role")),
                "answer_relation": _answer_relation(override.get("answer_relation") or current.get("answer_relation")),
                "rationale": _short_text(override.get("rationale") or current.get("rationale"), 420),
            }
        )
        baseline[evidence_id] = current
    for evidence_id in _string_list(reconciliation.get("unresolved_evidence_item_ids")):
        if evidence_id in baseline:
            current = dict(baseline[evidence_id])
            current["memo_inclusion"] = _stronger_inclusion(current.get("memo_inclusion"), "supporting_context")
            current["decision_role"] = "crux"
            current["answer_relation"] = "uncertain_relation"
            current["rationale"] = _short_text(current.get("rationale") or "Global reconciliation flagged this evidence as unresolved.", 420)
            baseline[evidence_id] = current
    return list(baseline.values())


def _baseline_evidence_roles(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_item_id": str(row.get("evidence_item_id") or ""),
            "memo_inclusion": _memo_inclusion_from_memo_use(row.get("adjudicated_memo_use") or row.get("current_role")),
            "decision_role": _decision_role_from_memo_use(row.get("adjudicated_memo_use") or row.get("current_role")),
            "answer_relation": _answer_relation(row.get("adjudicated_answer_relation")),
            "priority_rank": _rank(row.get("adjudicated_importance_rank") or row.get("importance_rank") or row.get("current_priority")),
            "rationale": _short_text(row.get("decision_contribution") or row.get("rationale") or row.get("claim") or "Baseline role from analyst adjudication.", 420),
        }
        for row in _rows(context)
    ]


def _source_weight_judgments_from_hierarchy(context: dict[str, Any], hierarchy: dict[str, Any]) -> list[dict[str, Any]]:
    known_sources = set(_context_source_ids(context))
    rows = []
    for index, row in enumerate(_list(hierarchy.get("source_accounting")), start=1):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").strip()
        if source_id not in known_sources:
            continue
        lane = str(row.get("primary_lane") or "").strip()
        rows.append(
            _drop_empty(
                {
                    "judgment_id": f"source_hierarchy_weight_{index:03d}",
                    "source_ids": [source_id],
                    "main_use": _main_use_from_lane(lane),
                    "why_weight_this_way": _short_text(row.get("rationale"), 700),
                    "reader_facing_limit": _short_text(row.get("reader_facing_limit"), 360),
                    "memo_weight_sentence": _short_text(row.get("memo_weight_sentence") or row.get("rationale"), 520),
                    "confidence_effect": _confidence_effect_from_lane(lane),
                    "method": "source_hierarchy_accounting",
                }
            )
        )
    return rows


def _valid_quantity_decisions(context: dict[str, Any], rows: list[Any]) -> list[dict[str, Any]]:
    known = {
        str(row.get("evidence_item_id") or ""): set(_string_list(row.get("quantity_values")))
        for row in _rows(context)
    }
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or "")
        quantity = str(row.get("quantity_value") or "")
        if quantity and quantity in known.get(evidence_id, set()):
            result.append(row)
    return result


def _valid_source_weight_judgments(context: dict[str, Any], rows: list[Any]) -> list[dict[str, Any]]:
    known_sources = set(_context_source_ids(context))
    known_evidence = {str(row.get("evidence_item_id") or "") for row in _rows(context)}
    result = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        source_ids = [source_id for source_id in _string_list(row.get("source_ids") or row.get("source_id")) if source_id in known_sources]
        if not source_ids:
            continue
        evidence_ids = [evidence_id for evidence_id in _string_list(row.get("evidence_item_ids")) if evidence_id in known_evidence]
        result.append(
            _drop_empty(
                {
                    "judgment_id": f"analyst_source_weight_{index:03d}",
                    "source_ids": _dedupe(source_ids),
                    "source_type": _source_type(row.get("source_type")),
                    "main_use": _main_use(row.get("main_use")),
                    "why_weight_this_way": _short_text(row.get("why_weight_this_way"), 700),
                    "reader_facing_limit": _short_text(row.get("reader_facing_limit"), 360),
                    "what_not_to_use_it_for": [_short_text(value, 360) for value in _string_list(row.get("what_not_to_use_it_for")) if _short_text(value, 360)],
                    "memo_weight_sentence": _short_text(row.get("memo_weight_sentence"), 520),
                    "confidence_effect": _confidence_effect(row.get("confidence_effect")),
                    "evidence_item_ids": evidence_ids,
                    "method": "parallel_global_analyst_source_weighting",
                }
            )
        )
    return result


def _source_weight_judgment_report(context: dict[str, Any], judgments: list[dict[str, Any]]) -> dict[str, Any]:
    source_ids = set(_context_source_ids(context))
    judged = {source_id for row in judgments for source_id in _string_list(row.get("source_ids"))}
    missing = sorted(source_ids - judged)
    warnings = []
    if source_ids and not judgments:
        warnings.append("missing_parallel_source_weight_judgments")
    if missing:
        warnings.append("source_ids_without_parallel_source_weight_judgment")
    return {
        "schema_id": "parallel_global_source_weight_judgment_report_v1",
        "status": "ready" if not warnings else "warning",
        "method": "parallel_global_analyst_source_weighting",
        "source_count": len(source_ids),
        "judgment_count": len(judgments),
        "judged_source_count": len(judged),
        "missing_source_ids": missing[:20],
        "warnings": warnings,
    }


def _context_source_ids(context: dict[str, Any]) -> list[str]:
    return _dedupe(source_id for row in _rows(context) for source_id in _string_list(row.get("source_ids")))


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


def _threshold() -> int:
    try:
        return max(1, int(os.environ.get("ECM_ANALYST_DECISION_MODEL_PARALLEL_THRESHOLD", "12")))
    except ValueError:
        return 12


def _rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(context.get("evidence_rows")) if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()]


def _valid_ids(context: dict[str, Any], ids: list[str]) -> list[str]:
    known = {str(row.get("evidence_item_id") or "") for row in _rows(context)}
    return [evidence_id for evidence_id in ids if evidence_id in known]


def _dedupe_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for group in [group for group in groups if group.get("covered_evidence_item_ids")]:
        group_id = str(group.get("group_id") or "")
        if group_id in seen:
            group = dict(group)
            group["group_id"] = f"{group_id}_{len(seen) + 1:03d}"
        seen.add(str(group.get("group_id") or ""))
        deduped.append(group)
    return deduped


def _source_type(value: Any) -> str:
    text = _enum_text(value)
    aliases = {
        "observational": "observational_primary",
        "cohort": "observational_primary",
        "trial": "trial_or_intervention",
        "rct": "trial_or_intervention",
        "intervention": "trial_or_intervention",
        "review": "evidence_synthesis",
        "meta_analysis": "evidence_synthesis",
        "synthesis": "evidence_synthesis",
        "guidance": "guidance_or_advisory",
        "guideline": "guidance_or_advisory",
        "advisory": "guidance_or_advisory",
        "context": "contextual_summary",
        "background": "contextual_summary",
    }
    allowed = {"observational_primary", "trial_or_intervention", "evidence_synthesis", "guidance_or_advisory", "contextual_summary", "mixed_or_unclear"}
    return aliases.get(text, text) if aliases.get(text, text) in allowed else "mixed_or_unclear"


def _main_use(value: Any) -> str:
    text = _enum_text(value)
    aliases = {
        "support": "drives_answer",
        "primary": "drives_answer",
        "driver": "drives_answer",
        "calibrate": "calibrates_magnitude",
        "magnitude": "calibrates_magnitude",
        "bound": "bounds_answer",
        "counterweight": "bounds_answer",
        "scope": "defines_scope",
        "applicability": "defines_scope",
        "crux": "identifies_crux",
        "context": "contextualizes",
        "background": "contextualizes",
    }
    allowed = {"drives_answer", "calibrates_magnitude", "bounds_answer", "defines_scope", "identifies_crux", "contextualizes"}
    return aliases.get(text, text) if aliases.get(text, text) in allowed else "contextualizes"


def _confidence_effect(value: Any) -> str:
    text = _enum_text(value)
    aliases = {"raise": "raises_confidence", "raises": "raises_confidence", "lower": "lowers_confidence", "lowers": "lowers_confidence", "narrows": "narrows_scope"}
    allowed = {"raises_confidence", "lowers_confidence", "narrows_scope", "mixed", "neutral"}
    return aliases.get(text, text) if aliases.get(text, text) in allowed else "neutral"


def _enum_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _reason_or_claim(context: dict[str, Any], row: Any, *, fallback: str) -> str:
    data = _dict(row)
    reason = str(data.get("reason") or "").strip()
    if reason:
        return reason
    rows_by_id = {str(source.get("evidence_item_id") or ""): source for source in _rows(context)}
    claims = [
        str(rows_by_id[evidence_id].get("claim") or "")
        for evidence_id in _string_list(data.get("evidence_item_ids"))
        if evidence_id in rows_by_id
    ]
    return _short_text("; ".join(claims) or fallback, 620)


def _dominant_memo_role(rows: list[dict[str, Any]]) -> str:
    roles = [_decision_role(row.get("decision_role")) for row in rows if row]
    for role, memo_role in (
        ("counterweight", "load_bearing_counterweight"),
        ("crux", "decision_crux"),
        ("scope_boundary", "scope_or_applicability"),
        ("calibrator", "quantitative_anchor"),
        ("answer_driver", "load_bearing_primary_support"),
    ):
        if role in roles:
            return memo_role
    return "mechanism_or_context"


def _dominant_answer_relation(rows: list[dict[str, Any]]) -> str:
    relations = [_answer_relation(row.get("answer_relation")) for row in rows if row]
    for relation in ("challenges_answer", "identifies_crux", "bounds_scope", "supports_answer", "contextualizes_answer"):
        if relation in relations:
            return relation
    return "contextualizes_answer"


def _memo_role_from_decision_role(role: str, inclusion: str) -> str:
    if role == "answer_driver":
        return "load_bearing_primary_support"
    if role == "counterweight":
        return "load_bearing_counterweight"
    if role == "calibrator":
        return "quantitative_anchor"
    if role == "scope_boundary":
        return "scope_or_applicability"
    if role == "crux":
        return "decision_crux"
    if inclusion == "memo_spine":
        return "mechanism_or_context"
    return "background_only"


def _decision_role_from_memo_use(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "counter" in text or "challenge" in text:
        return "counterweight"
    if "quant" in text or "calibrator" in text:
        return "calibrator"
    if "scope" in text or "applicability" in text or "boundary" in text:
        return "scope_boundary"
    if "crux" in text:
        return "crux"
    if "support" in text or "primary" in text or "driver" in text:
        return "answer_driver"
    return "context"


def _memo_inclusion_from_memo_use(value: Any) -> str:
    text = str(value or "").strip().lower()
    if any(token in text for token in ("primary", "counter", "quantitative", "scope", "crux", "spine", "load_bearing")):
        return "memo_spine"
    if "not_decision_relevant" in text:
        return "exclude"
    if "background" in text or "covered" in text:
        return "trace_only"
    return "supporting_context"


def _stronger_inclusion(left: Any, right: Any) -> str:
    order = {"exclude": 0, "trace_only": 1, "supporting_context": 2, "memo_spine": 3}
    left_value = _memo_inclusion(left)
    right_value = _memo_inclusion(right)
    return left_value if order[left_value] >= order[right_value] else right_value


def _priority_band_rank(value: Any, fallback: int) -> int:
    text = str(value or "").strip().lower()
    if text == "high":
        return 10
    if text == "medium":
        return 35
    if text == "low":
        return 70
    return fallback


def _main_use_from_lane(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "primary" in text or "driver" in text:
        return "drives_answer"
    if "quant" in text or "calibrator" in text:
        return "calibrates_magnitude"
    if "counter" in text:
        return "bounds_answer"
    if "scope" in text or "boundary" in text:
        return "defines_scope"
    if "crux" in text:
        return "identifies_crux"
    return "contextualizes"


def _confidence_effect_from_lane(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "primary" in text or "driver" in text:
        return "raises_confidence"
    if "counter" in text:
        return "lowers_confidence"
    if "scope" in text or "boundary" in text:
        return "narrows_scope"
    return "neutral"


def _decision_role(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"answer_driver", "calibrator", "counterweight", "scope_boundary", "crux", "context"} else "context"


def _answer_relation(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"supports_answer", "challenges_answer", "bounds_scope", "identifies_crux", "contextualizes_answer", "not_decision_relevant", "uncertain_relation"} else "contextualizes_answer"


def _memo_inclusion(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"memo_spine", "supporting_context", "trace_only", "exclude"} else "trace_only"


def _quantity_inclusion(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"must_use", "supporting_context", "trace_only", "exclude"} else "trace_only"


def _quantity_role(value: Any, inclusion: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"decision_anchor", "supporting_detail", "study_descriptor", "statistical_detail", "audit_only"}:
        return text
    if inclusion == "must_use":
        return "decision_anchor"
    if inclusion == "supporting_context":
        return "supporting_detail"
    return "audit_only"


def _disposition_from_inclusion(inclusion: str) -> str:
    if inclusion in {"memo_spine", "supporting_context"}:
        return "foreground"
    if inclusion == "exclude":
        return "not_decision_relevant"
    return "background"


def _effect_for_relation(relation: str) -> str:
    return {
        "supports_answer": "supports current_best_answer",
        "challenges_answer": "weakens current_best_answer",
        "bounds_scope": "bounds current_best_answer",
        "identifies_crux": "distinguishes live options",
        "contextualizes_answer": "background",
    }.get(relation, "background")


def _answer_impact_for_relation(relation: str) -> str:
    return {
        "supports_answer": "Supports the current best answer.",
        "challenges_answer": "Weakens or bounds confidence in the current best answer.",
        "bounds_scope": "Defines where the answer applies.",
        "identifies_crux": "Identifies what would change the answer.",
        "contextualizes_answer": "Provides context for interpreting or applying the answer.",
    }.get(relation, "Provides context for the answer.")


def _rank(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 100


def _safe_id(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9_:-]+", "_", str(value or "")).strip("_").lower()
    return text or "section"


def _stable_answer(context: dict[str, Any]) -> str:
    return str(_dict(context.get("stable_final_answer_frame")).get("current_best_answer") or "")


def _confidence(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"low", "medium", "high", "not_specified"} else "not_specified"


def _overall_rationale(answer_frame: dict[str, Any], source_hierarchy: dict[str, Any], blueprint: dict[str, Any]) -> str:
    return _short_text(
        " ".join(
            text
            for text in (
                str(answer_frame.get("confidence_basis") or ""),
                str(source_hierarchy.get("hierarchy_thesis") or ""),
                str(blueprint.get("memo_thesis") or ""),
            )
            if text.strip()
        ),
        900,
    )


def _quantity_anchors(quantity_relevance: list[dict[str, Any]]) -> list[str]:
    return _dedupe(
        str(row.get("retention_phrase") or row.get("quantity_value") or "")
        for row in quantity_relevance
        if row.get("memo_inclusion") in {"must_use", "supporting_context"}
    )[:20]


def _what_would_change(answer_frame: dict[str, Any], evidence_roles: list[dict[str, Any]]) -> list[str]:
    values = _string_list(answer_frame.get("what_would_change_the_answer"))
    values.extend(str(row.get("rationale") or "") for row in evidence_roles if row.get("decision_role") == "crux")
    return _dedupe(_short_text(value, 320) for value in values if value)[:8]


def _decision_logic(
    answer_frame: dict[str, Any],
    groups: list[dict[str, Any]],
    evidence_roles: list[dict[str, Any]],
    source_hierarchy: dict[str, Any],
) -> dict[str, Any]:
    support = _group_summary(groups, "load_bearing_primary_support", limit=2)
    counterweight = _group_summary(groups, "load_bearing_counterweight", limit=2)
    scope = _string_list(answer_frame.get("scope_boundaries"))[:6]
    counterweight_weighting = _short_text(
        answer_frame.get("counterweight_weighting")
        or answer_frame.get("why_counterweights_do_or_do_not_change_answer")
        or content_based_counterweight_weighting(
            support=support,
            counterweight=counterweight,
            fallback=" ".join([*scope[:2], str(source_hierarchy.get("hierarchy_thesis") or "")]).strip(),
        ),
        520,
    )
    logic = {
        "bounded_bottom_line": _short_text(answer_frame.get("best_answer"), 700),
        "support_summary": support,
        "strongest_counterweight": counterweight,
        "counterweight_weighting": counterweight_weighting,
        "reconciled_cruxes": _what_would_change(answer_frame, evidence_roles),
        "scope_boundaries": scope,
        "practical_implications": _dedupe(
            [
                *_string_list(answer_frame.get("practical_implication")),
                *_string_list(answer_frame.get("practical_implications")),
            ]
        )[:6],
        "do_not_overstate": _string_list(answer_frame.get("do_not_overstate"))[:8],
    }
    return naturalize_decision_logic_payload(logic)


def _group_summary(groups: list[dict[str, Any]], role: str, *, limit: int) -> str:
    values = [
        str(group.get("proposition") or "").strip()
        for group in groups
        if group.get("memo_role") == role and str(group.get("proposition") or "").strip()
    ]
    return _short_text("; ".join(_dedupe(values)[:limit]), 760)


def _argument_plan_from_blueprint(blueprint: dict[str, Any], groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, row in enumerate(_list(blueprint.get("section_plan")), start=1):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "step_id": _safe_id(row.get("section_id") or f"step_{index:03d}"),
                "section": str(row.get("heading") or "Decision Brief"),
                "writing_goal": _short_text(row.get("section_job") or row.get("core_claim"), 360),
                "required_points": _dedupe(
                    [
                        str(row.get("core_claim") or ""),
                        *_string_list(row.get("must_use_quantities")),
                        str(row.get("source_weighting_move") or ""),
                    ]
                )[:8],
                "evidence_item_ids": _string_list(row.get("must_use_evidence_item_ids"))[:14],
                "transition_from_previous": _short_text(row.get("transition") or argument_plan_transition(str(row.get("section_id") or "")), 260),
            }
        )
    if rows:
        return rows[:12]
    return [
        {
            "step_id": str(group.get("group_id") or f"group_{index:03d}"),
            "section": "Decision Brief",
            "writing_goal": _short_text(group.get("rationale") or group.get("proposition"), 360),
            "required_points": [str(group.get("proposition") or "")],
            "evidence_item_ids": _string_list(group.get("covered_evidence_item_ids")),
            "transition_from_previous": argument_plan_transition(str(group.get("memo_role") or "")),
        }
        for index, group in enumerate(groups[:8], start=1)
    ]


def _row_is_quantity_forward(row: dict[str, Any]) -> bool:
    return str(row.get("current_role") or row.get("adjudicated_memo_use") or "").strip() in {
        "quantitative_anchor",
        "load_bearing_primary_support",
        "load_bearing_counterweight",
        "decision_crux",
    }


def _join(chunks: list[str], label: str) -> str:
    return "\n\n".join(f"--- {label} {index} ---\n{chunk}" for index, chunk in enumerate(chunks, start=1) if chunk)
