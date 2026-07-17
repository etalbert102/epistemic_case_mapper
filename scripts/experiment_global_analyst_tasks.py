#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from epistemic_case_mapper.model_backends import model_parallelism, run_model_backend, run_parallel


TASKS = ("answer_frame", "evidence_roles", "quantity_plan", "source_hierarchy", "argument_blueprint")


def main() -> int:
    args = _parse_args()
    context = _read_json(args.context)
    current_model = _read_json(args.current_model) if args.current_model else {}
    args.output_dir.mkdir(parents=True, exist_ok=True)

    packet = _compact_global_context(context)
    tasks = [
        _task_packet(task, _task_context(task, context) if args.context_mode == "task-specific" else packet)
        for task in TASKS
    ]
    started = time.monotonic()
    results = run_parallel(
        tasks,
        lambda task: _run_task(task, backend=args.backend, timeout=args.timeout, retries=args.retries),
        max_workers=args.parallelism or model_parallelism(args.backend),
    )
    summary = _build_summary(results, current_model=current_model, context=context)
    summary["wall_seconds"] = round(time.monotonic() - started, 3)
    summary["backend"] = args.backend
    summary["parallelism"] = args.parallelism or model_parallelism(args.backend)
    summary["context_mode"] = args.context_mode
    summary["context"] = {
        "evidence_row_count": len(_rows(context)),
        "source_count": len(_source_ids(context)),
        "decision_question": context.get("decision_question"),
    }

    _write_json(args.output_dir / "global_context_compact.json", packet)
    for result in results:
        stem = str(result["task_id"])
        (args.output_dir / f"{stem}_prompt.txt").write_text(str(result["prompt"]), encoding="utf-8")
        (args.output_dir / f"{stem}_raw.txt").write_text(str(result["raw"]), encoding="utf-8")
        _write_json(args.output_dir / f"{stem}_parsed.json", result.get("payload") or {})
        _write_json(args.output_dir / f"{stem}_report.json", _public_result(result))
    _write_json(args.output_dir / "global_analyst_task_experiment_summary.json", summary)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["parsed_count"] == len(TASKS) else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Experiment with global-question parallel analyst decision model calls.")
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--current-model", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backend", default="ollama:gemma4:12b-mlx")
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--parallelism", type=int, default=0)
    parser.add_argument("--context-mode", choices=["full", "task-specific"], default="full")
    return parser.parse_args()


def _run_task(task: dict[str, Any], *, backend: str, timeout: int, retries: int) -> dict[str, Any]:
    prompt = _prompt(task)
    started = time.monotonic()
    raw = ""
    payload: Any = {}
    error = ""
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=timeout,
            max_retries=retries,
            num_predict=_num_predict(task["task_id"]),
            json_mode=True,
        )
        raw = result.text
        payload = _extract_json(raw)
    except Exception as exc:  # noqa: BLE001 - experiment report should preserve backend failures.
        error = str(exc)
    status = "parsed" if isinstance(payload, dict) and payload.get("schema_id") else "failed"
    return {
        "task_id": task["task_id"],
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 3),
        "prompt": prompt,
        "raw": raw,
        "payload": payload if isinstance(payload, dict) else {},
        "error": error,
        "prompt_chars": len(prompt),
        "raw_chars": len(raw),
    }


def _prompt(task: dict[str, Any]) -> str:
    packet = {
        "task": task["instruction"],
        "decision_question": task["context"]["decision_question"],
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


def _task_packet(task_id: str, context: dict[str, Any]) -> dict[str, Any]:
    schemas = {
        "answer_frame": {
            "schema_id": "global_answer_frame_experiment_v1",
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
            "schema_id": "global_evidence_roles_experiment_v1",
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
            "schema_id": "global_quantity_plan_experiment_v1",
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
        "source_hierarchy": {
            "schema_id": "global_source_hierarchy_experiment_v1",
            "hierarchy_thesis": "comparative source hierarchy for the decision",
            "source_roles": [
                {
                    "source_id": "source_id",
                    "primary_role": "answer_driver | calibrator | counterweight | scope_boundary | context",
                    "evidence_item_ids": ["evidence_id"],
                    "rationale": "why this source has that marginal role",
                }
            ],
        },
        "argument_blueprint": {
            "schema_id": "global_argument_blueprint_experiment_v1",
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
    instructions = {
        "answer_frame": "Create the global answer frame: best answer, confidence, main answer drivers, main counterweights, scope, and practical implication.",
        "evidence_roles": "Classify every evidence row's whole-case decision role and memo inclusion.",
        "quantity_plan": "Decide which quantities must survive in the memo and how to word them safely.",
        "source_hierarchy": "Create a global comparative source hierarchy by marginal decision role.",
        "argument_blueprint": "Create the reader-facing argument blueprint that should control memo synthesis.",
    }
    return {
        "task_id": task_id,
        "instruction": instructions[task_id],
        "schema": schemas[task_id],
        "context": context,
    }


def _compact_global_context(context: dict[str, Any]) -> dict[str, Any]:
    rows = [_compact_row(row) for row in _rows(context)]
    return {
        "schema_id": "global_analyst_experiment_context_v1",
        "decision_question": context.get("decision_question"),
        "stable_final_answer_frame": _compact_answer_frame(context.get("stable_final_answer_frame")),
        "source_inventory": _source_inventory(rows),
        "evidence_rows": rows,
        "retention_obligations": _trim_list(context.get("retention_obligations"), 40),
        "obligation_group_skeleton": _trim_list(context.get("obligation_group_skeleton"), 30),
    }


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
        return {
            **common,
            "evidence_rows": [_role_row(row) for row in rows],
            "source_lane_hints": _source_lane_hints(rows),
        }
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
    keys = [
        "evidence_item_id",
        "claim",
        "source_ids",
        "source_labels",
        "source_quality",
        "source_weight_note",
        "source_bottom_lines",
        "adjudicated_memo_use",
        "adjudicated_answer_relation",
        "effect_on_final_answer",
        "target_answer_option",
        "decision_contribution",
        "use_in_reasoning",
        "key_qualifier",
        "if_omitted",
        "misuse_warning",
        "quantity_values",
        "tension_type",
    ]
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "", [], {})}


def _role_row(row: dict[str, Any]) -> dict[str, Any]:
    return _keep(
        row,
        [
            "evidence_item_id",
            "claim",
            "source_ids",
            "adjudicated_memo_use",
            "adjudicated_answer_relation",
            "effect_on_final_answer",
            "target_answer_option",
            "decision_contribution",
            "use_in_reasoning",
            "key_qualifier",
            "if_omitted",
            "misuse_warning",
            "quantity_values",
            "tension_type",
            "source_weight_note",
        ],
    )


def _quantity_row(row: dict[str, Any]) -> dict[str, Any]:
    return _keep(
        row,
        [
            "evidence_item_id",
            "claim",
            "source_ids",
            "adjudicated_memo_use",
            "adjudicated_answer_relation",
            "effect_on_final_answer",
            "decision_contribution",
            "use_in_reasoning",
            "key_qualifier",
            "quantity_values",
            "source_weight_note",
        ],
    )


def _blueprint_row(row: dict[str, Any]) -> dict[str, Any]:
    return _keep(
        row,
        [
            "evidence_item_id",
            "claim",
            "source_ids",
            "adjudicated_memo_use",
            "adjudicated_answer_relation",
            "effect_on_final_answer",
            "target_answer_option",
            "decision_contribution",
            "use_in_reasoning",
            "key_qualifier",
            "if_omitted",
            "misuse_warning",
            "quantity_values",
            "source_weight_note",
        ],
    )


def _summary_row(row: dict[str, Any]) -> dict[str, Any]:
    return _keep(
        row,
        [
            "evidence_item_id",
            "claim",
            "source_ids",
            "adjudicated_memo_use",
            "adjudicated_answer_relation",
            "effect_on_final_answer",
            "quantity_values",
            "source_weight_note",
        ],
    )


def _keep(row: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if row.get(key) not in (None, "", [], {})}


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


def _source_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        for source_id in _string_list(row.get("source_ids")):
            entry = by_source.setdefault(
                source_id,
                {"source_id": source_id, "source_labels": [], "evidence_item_ids": [], "claims": [], "qualities": [], "quantities": []},
            )
            entry["source_labels"].extend(_string_list(row.get("source_labels")))
            entry["evidence_item_ids"].append(str(row.get("evidence_item_id") or ""))
            entry["claims"].append(_short(str(row.get("claim") or ""), 220))
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
    text = " ".join(
        str(row.get(key) or "")
        for key in (
            "adjudicated_memo_use",
            "current_role",
            "use_in_reasoning",
            "decision_contribution",
            "adjudicated_answer_relation",
            "effect_on_final_answer",
            "source_weight_note",
        )
    ).lower()
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
    return (score, _rank_value(row), str(row.get("evidence_item_id") or ""))


def _rank_value(row: dict[str, Any]) -> int:
    for key in ("adjudicated_importance_rank", "importance_rank", "current_priority"):
        value = row.get(key)
        if value is None:
            continue
        match = re.search(r"\d+", str(value))
        if match:
            return int(match.group(0))
    return 100


def _source_lane_hints(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hints: dict[str, dict[str, Any]] = {}
    for row in rows:
        for source_id in _string_list(row.get("source_ids")):
            hint = hints.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "memo_uses": [],
                    "answer_relations": [],
                    "evidence_item_ids": [],
                    "source_weight_notes": [],
                },
            )
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


def _compact_obligations(value: Any, selected_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_ids = {str(row.get("evidence_item_id") or "") for row in selected_rows}
    compacted = []
    for row in _trim_list(value, 80):
        if not isinstance(row, dict):
            continue
        evidence_ids = [
            evidence_id
            for evidence_id in _string_list(row.get("evidence_item_ids") or row.get("covered_evidence_item_ids") or row.get("evidence_item_id"))
            if not selected_ids or evidence_id in selected_ids
        ]
        if not evidence_ids and selected_ids:
            continue
        compacted.append(
            {
                key: row.get(key)
                for key in (
                    "obligation_id",
                    "skeleton_group_id",
                    "target_memo_role",
                    "primary_obligation_type",
                    "role",
                    "statement",
                    "claim",
                    "prose_instruction",
                    "evidence_item_ids",
                    "covered_evidence_item_ids",
                )
                if row.get(key) not in (None, "", [], {})
            }
        )
    return compacted[:24]


def _build_summary(results: list[dict[str, Any]], *, current_model: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    payloads = {str(result["task_id"]): result.get("payload") or {} for result in results}
    evidence_roles = payloads.get("evidence_roles", {}).get("evidence_roles", [])
    quantity_decisions = payloads.get("quantity_plan", {}).get("quantity_decisions", [])
    source_roles = payloads.get("source_hierarchy", {}).get("source_roles", [])
    section_plan = payloads.get("argument_blueprint", {}).get("section_plan", [])
    role_counts = Counter(str(row.get("decision_role") or "") for row in evidence_roles if isinstance(row, dict))
    inclusion_counts = Counter(str(row.get("memo_inclusion") or "") for row in evidence_roles if isinstance(row, dict))
    current_groups = current_model.get("evidence_groups", []) if isinstance(current_model, dict) else []
    return {
        "schema_id": "global_analyst_task_experiment_summary_v1",
        "task_statuses": {str(result["task_id"]): result["status"] for result in results},
        "parsed_count": sum(1 for result in results if result["status"] == "parsed"),
        "task_reports": [_public_result(result) for result in results],
        "experiment_readout": {
            "answer_frame_best_answer": payloads.get("answer_frame", {}).get("best_answer", ""),
            "answer_frame_confidence": payloads.get("answer_frame", {}).get("confidence", ""),
            "main_driver_count": len(payloads.get("answer_frame", {}).get("main_answer_drivers", []) or []),
            "counterweight_count": len(payloads.get("answer_frame", {}).get("main_counterweights", []) or []),
            "evidence_role_count": len(evidence_roles) if isinstance(evidence_roles, list) else 0,
            "evidence_role_coverage": _coverage(evidence_roles, context),
            "evidence_role_counts": dict(role_counts),
            "memo_inclusion_counts": dict(inclusion_counts),
            "must_use_quantity_count": sum(1 for row in quantity_decisions if isinstance(row, dict) and row.get("memo_inclusion") == "must_use"),
            "source_role_count": len(source_roles) if isinstance(source_roles, list) else 0,
            "argument_section_count": len(section_plan) if isinstance(section_plan, list) else 0,
            "argument_blueprint_headings": [row.get("heading") for row in section_plan if isinstance(row, dict)],
        },
        "current_row_sharded_readout": {
            "direct_answer": current_model.get("direct_answer", ""),
            "group_count": len(current_groups) if isinstance(current_groups, list) else 0,
            "argument_plan_count": len(current_model.get("argument_plan", []) or []),
            "source_hierarchy_thesis": (current_model.get("source_hierarchy", {}) or {}).get("hierarchy_thesis", ""),
        },
        "preliminary_judgment": _preliminary_judgment(payloads, context),
    }


def _preliminary_judgment(payloads: dict[str, dict[str, Any]], context: dict[str, Any]) -> list[str]:
    notes = []
    role_coverage = _coverage(payloads.get("evidence_roles", {}).get("evidence_roles", []), context)
    if role_coverage.get("missing_count", 0) == 0:
        notes.append("global evidence role task covered every routed evidence row")
    else:
        notes.append(f"global evidence role task missed {role_coverage.get('missing_count')} routed rows")
    if payloads.get("argument_blueprint", {}).get("section_plan"):
        notes.append("argument blueprint produced a reader-facing memo plan from global context")
    if payloads.get("source_hierarchy", {}).get("source_roles"):
        notes.append("source hierarchy produced source-level marginal roles from global context")
    if payloads.get("answer_frame", {}).get("main_answer_drivers") and payloads.get("answer_frame", {}).get("main_counterweights"):
        notes.append("answer frame separated drivers from counterweights")
    return notes


def _coverage(rows: Any, context: dict[str, Any]) -> dict[str, Any]:
    expected = {str(row.get("evidence_item_id") or "") for row in _rows(context)}
    seen = {str(row.get("evidence_item_id") or "") for row in rows if isinstance(row, dict)}
    missing = sorted(evidence_id for evidence_id in expected if evidence_id and evidence_id not in seen)
    extra = sorted(evidence_id for evidence_id in seen if evidence_id and evidence_id not in expected)
    return {"expected_count": len(expected), "seen_count": len(seen), "missing_count": len(missing), "extra_count": len(extra), "missing": missing[:20], "extra": extra[:20]}


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": result.get("task_id"),
        "status": result.get("status"),
        "duration_seconds": result.get("duration_seconds"),
        "prompt_chars": result.get("prompt_chars"),
        "raw_chars": result.get("raw_chars"),
        "error": result.get("error"),
    }


def _extract_json(text: str) -> Any:
    text = text.strip()
    if not text:
        return {}
    candidates = [text]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates.extend(fenced)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {}


def _num_predict(task_id: str) -> int:
    return {
        "answer_frame": 4096,
        "evidence_roles": 8192,
        "quantity_plan": 6144,
        "source_hierarchy": 4096,
        "argument_blueprint": 6144,
    }[task_id]


def _rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in context.get("evidence_rows", []) if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()]


def _source_ids(context: dict[str, Any]) -> list[str]:
    return _dedupe(source_id for row in _rows(context) for source_id in _string_list(row.get("source_ids")))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _trim_list(value: Any, limit: int) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []


def _short(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "..."


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
