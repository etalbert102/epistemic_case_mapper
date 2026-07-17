from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_source_hierarchy import source_hierarchy_schema

GLOBAL_ANALYST_TASKS: tuple[str, ...] = (
    "answer_frame",
    "evidence_roles",
    "quantity_plan",
    "source_hierarchy",
    "argument_blueprint",
)


def build_global_analyst_tasks(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [_global_task_packet(task_id, _task_context(task_id, context)) for task_id in GLOBAL_ANALYST_TASKS]


def build_global_analyst_task_prompt(task: dict[str, Any]) -> str:
    packet = {
        "task": task["instruction"],
        "decision_question": task["context"].get("decision_question"),
        "instructions": [
            "Answer the assigned global question using the supplied task-specific context.",
            "Use only supplied evidence_item_ids, source_ids, quantities, and source labels.",
            "Make source weighting explicit: distinguish answer drivers, calibrators, counterweights, boundaries, and context.",
            "Return strict JSON only in the required schema.",
        ],
        "required_output_schema": task["schema"],
        "context": task["context"],
    }
    return json.dumps(packet, indent=2, ensure_ascii=False)


def _global_task_packet(task_id: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "instruction": _task_instruction(task_id),
        "schema": _task_schema(task_id),
        "context": context,
    }


def _task_instruction(task_id: str) -> str:
    return {
        "answer_frame": "Create the global answer frame: best answer, confidence, main answer drivers, main counterweights, scope, and practical implication.",
        "evidence_roles": "Classify every evidence row's whole-case decision role and memo inclusion.",
        "quantity_plan": "Decide which quantities must survive in the memo and how to word them safely.",
        "source_hierarchy": "Create a global comparative source hierarchy by marginal decision role.",
        "argument_blueprint": "Create the reader-facing argument blueprint that should control memo synthesis.",
    }[task_id]


def _task_schema(task_id: str) -> dict[str, Any]:
    if task_id == "source_hierarchy":
        return source_hierarchy_schema()
    schemas: dict[str, dict[str, Any]] = {
        "answer_frame": {
            "schema_id": "global_answer_frame_v1",
            "best_answer": "bounded direct answer",
            "confidence": "low | medium | high",
            "confidence_basis": "why this confidence is warranted",
            "main_answer_drivers": [{"source_ids": ["source_id"], "evidence_item_ids": ["evidence_id"], "reason": "why this drives the answer"}],
            "main_counterweights": [{"source_ids": ["source_id"], "evidence_item_ids": ["evidence_id"], "reason": "how this weakens or bounds the answer"}],
            "scope_boundaries": ["where the answer applies or stops applying"],
            "practical_implication": "what a decision maker should do with the answer",
            "do_not_overstate": ["unsupported stronger claims"],
        },
        "evidence_roles": {
            "schema_id": "global_evidence_roles_v1",
            "evidence_roles": [
                {
                    "evidence_item_id": "evidence_id",
                    "memo_inclusion": "memo_spine | supporting_context | trace_only | exclude",
                    "decision_role": "answer_driver | calibrator | counterweight | scope_boundary | crux | context",
                    "answer_relation": "supports_answer | challenges_answer | bounds_scope | identifies_crux | contextualizes_answer",
                    "priority_rank": "integer, 1 is most decision-diagnostic",
                    "rationale": "why this role is correct in the whole evidence set",
                }
            ],
        },
        "quantity_plan": {
            "schema_id": "global_quantity_plan_v1",
            "quantity_decisions": [
                {
                    "evidence_item_id": "evidence_id",
                    "quantity_value": "exact supplied quantity",
                    "memo_inclusion": "must_use | supporting_context | trace_only | exclude",
                    "quantity_role": "decision_anchor | supporting_detail | study_descriptor | statistical_detail | audit_only",
                    "retention_phrase": "reader-facing phrase if used",
                    "rationale": "why this quantity matters or does not matter",
                }
            ],
        },
        "argument_blueprint": {
            "schema_id": "global_argument_blueprint_v1",
            "memo_thesis": "one paragraph thesis for the memo",
            "section_plan": [
                {
                    "section_id": "stable section id",
                    "heading": "reader-facing heading",
                    "section_job": "what this section must accomplish",
                    "core_claim": "main sentence this section should establish",
                    "must_use_evidence_item_ids": ["evidence_id"],
                    "must_use_quantities": ["quantity phrase"],
                    "source_weighting_move": "how source roles should be explained",
                    "transition": "how this section connects to the prior one",
                }
            ],
            "footnote_or_appendix_material": [{"evidence_item_id": "evidence_id", "reason": "why it should not be in main prose"}],
        },
    }
    return schemas[task_id]


def _task_context(task_id: str, context: dict[str, Any]) -> dict[str, Any]:
    rows = [_compact_row(row) for row in _rows(context)]
    common = {
        "schema_id": "global_analyst_task_specific_context_v1",
        "context_policy": "Contains only the information needed for this global analyst task.",
        "task_id": task_id,
        "decision_question": context.get("decision_question"),
        "stable_final_answer_frame": _compact_answer_frame(context.get("stable_final_answer_frame")),
    }
    if task_id == "answer_frame":
        selected = _select_decision_rows(rows, limit=24)
        return {
            **common,
            "source_inventory": _source_inventory(selected),
            "decision_diagnostic_evidence_rows": selected,
            "selection_note": "Rows selected because upstream routing marked them as answer drivers, counterweights, calibrators, scope boundaries, cruxes, or quantity-bearing evidence.",
        }
    if task_id == "evidence_roles":
        return {**common, "evidence_rows": [_role_row(row) for row in rows], "source_lane_hints": _source_lane_hints(rows)}
    if task_id == "quantity_plan":
        quantity_rows = [row for row in rows if _string_list(row.get("quantity_values"))]
        return {
            **common,
            "quantity_bearing_evidence_rows": [_quantity_row(row) for row in quantity_rows],
            "source_lane_hints": _source_lane_hints(quantity_rows),
            "decision_diagnostic_evidence_summary": [_summary_row(row) for row in _select_decision_rows(rows, limit=12)],
        }
    if task_id == "source_hierarchy":
        return {
            **common,
            "source_inventory": _source_inventory(rows),
            "source_lane_hints": _source_lane_hints(rows),
            "top_decision_evidence": [_summary_row(row) for row in _select_decision_rows(rows, limit=18)],
        }
    if task_id == "argument_blueprint":
        selected = _select_decision_rows(rows, limit=24)
        return {
            **common,
            "source_inventory": _source_inventory(selected),
            "decision_diagnostic_evidence_rows": [_blueprint_row(row) for row in selected],
            "retention_obligations": _compact_obligations(context.get("retention_obligations"), selected),
            "obligation_group_skeleton": _compact_obligations(context.get("obligation_group_skeleton"), selected),
        }
    return {**common, "evidence_rows": rows}


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
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
        "decision_contribution": _short_text(row.get("decision_contribution"), 260),
        "use_in_reasoning": _short_text(row.get("use_in_reasoning"), 100),
        "key_qualifier": _short_text(row.get("key_qualifier"), 160),
        "quantity_takeaway": _short_text(row.get("quantity_takeaway"), 180),
        "source_weight_note": _short_text(row.get("source_weight_note"), 160),
        "misuse_warning": _short_text(row.get("misuse_warning"), 180),
        "if_omitted": _short_text(row.get("if_omitted"), 180),
        "source_ids": _string_list(row.get("source_ids"))[:4],
        "source_labels": _string_list(row.get("source_labels"))[:4],
        "source_quality": row.get("source_quality") if isinstance(row.get("source_quality"), dict) else {},
        "claim": _short_text(row.get("claim"), 320),
        "source_bottom_lines": _source_bottom_lines(row.get("source_bottom_lines")),
        "source_bottom_line_signals": _string_list(row.get("source_bottom_line_signals"))[:4],
        "quantity_values": _string_list(row.get("quantity_values"))[:6],
        "why_it_matters": _short_text(row.get("why_it_matters"), 160),
        "failure_condition": _short_text(row.get("failure_condition"), 120),
        "existing_warning_codes": _string_list(row.get("existing_warning_codes"))[:4],
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _source_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        for source_id in _string_list(row.get("source_ids")):
            entry = by_source.setdefault(source_id, {"source_id": source_id, "source_labels": [], "evidence_item_ids": [], "claims": [], "qualities": [], "quantities": []})
            entry["source_labels"].extend(_string_list(row.get("source_labels")))
            entry["evidence_item_ids"].append(str(row.get("evidence_item_id") or ""))
            entry["claims"].append(_short_text(row.get("claim"), 220))
            if isinstance(row.get("source_quality"), dict):
                entry["qualities"].append(row.get("source_quality"))
            entry["quantities"].extend(_string_list(row.get("quantity_values")))
    return [
        {
            "source_id": source_id,
            "source_labels": _dedupe(entry["source_labels"])[:4],
            "evidence_item_ids": _dedupe(entry["evidence_item_ids"])[:20],
            "claim_count": len(_dedupe(entry["claims"])),
            "representative_claims": _dedupe(entry["claims"])[:8],
            "quantities": _dedupe(entry["quantities"])[:12],
            "source_quality": entry["qualities"][0] if entry["qualities"] else {},
        }
        for source_id, entry in sorted(by_source.items())
    ]


def _select_decision_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return sorted(rows, key=_decision_row_sort_key)[:limit]


def _decision_row_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    text = " ".join(str(row.get(key) or "") for key in ("adjudicated_memo_use", "current_role", "use_in_reasoning", "decision_contribution", "adjudicated_answer_relation", "effect_on_final_answer", "source_weight_note")).lower()
    score = 50
    if any(token in text for token in ("primary", "driver", "memo_spine", "load_bearing")):
        score -= 18
    if any(token in text for token in ("counterweight", "challenges", "weakens", "risk", "harm")):
        score -= 16
    if any(token in text for token in ("scope", "boundary", "subgroup", "applicability", "crux")):
        score -= 12
    if any(token in text for token in ("calibrator", "quantitative", "threshold", "dose")):
        score -= 10
    if _string_list(row.get("quantity_values")):
        score -= 7
    if any(token in text for token in ("context", "background", "trace")):
        score += 8
    return (score, _rank(row.get("adjudicated_importance_rank") or row.get("importance_rank") or row.get("current_priority")), str(row.get("evidence_item_id") or ""))


def _source_lane_hints(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hints: dict[str, dict[str, Any]] = {}
    for row in rows:
        for source_id in _string_list(row.get("source_ids")):
            hint = hints.setdefault(source_id, {"source_id": source_id, "memo_uses": [], "answer_relations": [], "evidence_item_ids": [], "source_weight_notes": []})
            hint["memo_uses"].extend(_string_list(row.get("adjudicated_memo_use")))
            hint["answer_relations"].extend(_string_list(row.get("adjudicated_answer_relation")))
            hint["evidence_item_ids"].append(str(row.get("evidence_item_id") or ""))
            hint["source_weight_notes"].extend(_string_list(row.get("source_weight_note")))
    return [
        {
            "source_id": source_id,
            "memo_uses": _dedupe(hint["memo_uses"])[:8],
            "answer_relations": _dedupe(hint["answer_relations"])[:8],
            "evidence_item_ids": _dedupe(hint["evidence_item_ids"])[:16],
            "source_weight_notes": _dedupe(hint["source_weight_notes"])[:4],
        }
        for source_id, hint in sorted(hints.items())
    ]


def _role_row(row: dict[str, Any]) -> dict[str, Any]:
    return _keep(row, ["evidence_item_id", "claim", "source_ids", "adjudicated_memo_use", "adjudicated_answer_relation", "effect_on_final_answer", "target_answer_option", "decision_contribution", "use_in_reasoning", "key_qualifier", "if_omitted", "misuse_warning", "quantity_values", "tension_type", "source_weight_note"])


def _quantity_row(row: dict[str, Any]) -> dict[str, Any]:
    return _keep(row, ["evidence_item_id", "claim", "source_ids", "adjudicated_memo_use", "adjudicated_answer_relation", "effect_on_final_answer", "decision_contribution", "use_in_reasoning", "key_qualifier", "quantity_values", "source_weight_note"])


def _blueprint_row(row: dict[str, Any]) -> dict[str, Any]:
    return _keep(row, ["evidence_item_id", "claim", "source_ids", "adjudicated_memo_use", "adjudicated_answer_relation", "effect_on_final_answer", "target_answer_option", "decision_contribution", "use_in_reasoning", "key_qualifier", "if_omitted", "misuse_warning", "quantity_values", "source_weight_note"])


def _summary_row(row: dict[str, Any]) -> dict[str, Any]:
    return _keep(row, ["evidence_item_id", "claim", "source_ids", "adjudicated_memo_use", "adjudicated_answer_relation", "effect_on_final_answer", "quantity_values", "source_weight_note"])


def _compact_obligations(value: Any, selected_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_ids = {str(row.get("evidence_item_id") or "") for row in selected_rows}
    compacted = []
    for row in _list(value)[:80]:
        if not isinstance(row, dict):
            continue
        evidence_ids = [
            evidence_id
            for evidence_id in _string_list(row.get("evidence_item_ids") or row.get("covered_evidence_item_ids") or row.get("evidence_item_id"))
            if not selected_ids or evidence_id in selected_ids
        ]
        if evidence_ids or not selected_ids:
            compacted.append({key: row.get(key) for key in ("obligation_id", "skeleton_group_id", "target_memo_role", "primary_obligation_type", "role", "statement", "claim", "prose_instruction", "evidence_item_ids", "covered_evidence_item_ids") if row.get(key) not in (None, "", [], {})})
    return compacted[:24]


def _compact_answer_frame(value: Any) -> dict[str, Any]:
    frame = value if isinstance(value, dict) else {}
    return {
        "answer_status": frame.get("answer_status"),
        "current_best_answer": frame.get("current_best_answer"),
        "confidence": frame.get("confidence"),
        "classification_rule": frame.get("classification_rule"),
        "classification_target_policy": frame.get("classification_target_policy"),
        "live_answer_options": frame.get("live_answer_options"),
    }


def _source_bottom_lines(value: Any) -> list[dict[str, str]]:
    rows = []
    for row in _list(value):
        if isinstance(row, dict):
            rows.append({key: field for key, field in {"source_id": str(row.get("source_id") or ""), "source_bottom_line": _short_text(row.get("source_bottom_line"), 260), "polarity_signal": str(row.get("polarity_signal") or "")}.items() if field})
    return rows[:4]


def _keep(row: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "", [], {})}


def _rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(context.get("evidence_rows")) if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()]


def _rank(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 100
