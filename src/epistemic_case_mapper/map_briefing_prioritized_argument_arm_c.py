from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_ready_section_synthesis import (
    run_parallel_memo_ready_section_generation,
)
from epistemic_case_mapper.map_briefing_prioritized_argument_arm_b import (
    _copy_frozen_inputs,
    _write_json,
    build_arm_b_projection,
    load_frozen_arm_b_inputs,
)
from epistemic_case_mapper.map_briefing_prioritized_argument_arm_b_audit import (
    audit_prompt_submissions,
    build_warning_adjudication_report,
    prompt_manifest,
)
from epistemic_case_mapper.map_briefing_prioritized_argument_evaluation import (
    LivePromptRecorder,
    build_arm_comparison_to_current,
    build_live_evaluation_aggregate_report,
)
from epistemic_case_mapper.model_backends import run_model_backend


class ArmCPrioritizedMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    move_id: str
    primary_section: Literal["answer_evidence", "counterweights", "practical_implication"]
    move_type: str = ""
    proposition: str = Field(min_length=1)
    warrant: str = Field(min_length=1)
    decision_effect: str = Field(min_length=1)
    evidence_item_ids: list[str] = Field(default_factory=list)
    required: bool = True
    depends_on_move_ids: list[str] = Field(default_factory=list)
    alternatives_discriminated: list[str] = Field(default_factory=list)
    counterweight_disposition: str = ""
    limitations: list[str] = Field(default_factory=list)

    @field_validator(
        "move_id",
        "primary_section",
        "move_type",
        "proposition",
        "warrant",
        "decision_effect",
        "counterweight_disposition",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("evidence_item_ids", "depends_on_move_ids", "alternatives_discriminated", "limitations", mode="before")
    @classmethod
    def _list_field(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []


class ArmCEvidenceAccounting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item_id: str
    disposition: Literal["owned", "appendix", "demoted", "background"]
    rationale: str = Field(min_length=1)

    @field_validator("evidence_item_id", "disposition", "rationale", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()


class ArmCPrioritizedArgument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["arm_c_prioritized_argument_v1"] = "arm_c_prioritized_argument_v1"
    decision_question: str
    frozen_direct_answer: str
    confidence: Literal["low", "medium", "high", "not_specified"] = "not_specified"
    argument_thesis: str = Field(min_length=1)
    moves: list[ArmCPrioritizedMove] = Field(min_length=1)
    evidence_accounting: list[ArmCEvidenceAccounting] = Field(default_factory=list)
    planning_gaps: list[str] = Field(default_factory=list)

    @field_validator(
        "decision_question",
        "frozen_direct_answer",
        "confidence",
        "argument_thesis",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("planning_gaps", mode="before")
    @classmethod
    def _list_field(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @model_validator(mode="after")
    def _unique_move_ids(self) -> "ArmCPrioritizedArgument":
        move_ids = [move.move_id for move in self.moves]
        if len(move_ids) != len(set(move_ids)):
            raise ValueError("moves must have unique move_id values")
        return self


def run_arm_c(
    *,
    briefing_dir: Path,
    output_dir: Path,
    backend: str,
    backend_timeout: int | None = 180,
    backend_retries: int = 0,
    samples: int = 1,
) -> dict[str, Any]:
    started = time.time()
    inputs = load_frozen_arm_b_inputs(briefing_dir)
    argument_run = run_arm_c_prioritization(
        inputs,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _copy_frozen_inputs(briefing_dir, output_dir / "frozen_inputs")
    _write_json(output_dir / "prioritized_evidence_argument.json", argument_run.get("prioritized_argument", {}))
    _write_json(output_dir / "prioritized_argument_verification_projection_report.json", argument_run.get("report", {}))
    if argument_run.get("prompt"):
        (output_dir / "prioritized_argument_prompt.txt").write_text(str(argument_run["prompt"]), encoding="utf-8")
    if argument_run.get("raw"):
        (output_dir / "prioritized_argument_raw.txt").write_text(str(argument_run["raw"]), encoding="utf-8")
    if not argument_run.get("accepted"):
        report = {
            "schema_id": "arm_c_live_evaluation_report_v1",
            "status": "fail",
            "accepted": False,
            "prioritization_status": _dict(argument_run.get("report")).get("status"),
            "elapsed_seconds": round(time.time() - started, 3),
            "issues": ["prioritized_argument_failed"],
        }
        _write_json(output_dir / "report.json", report)
        return {"prioritized_argument_run": argument_run, "report": report}

    projection = build_arm_c_projection(inputs, _dict(argument_run.get("prioritized_argument")))
    _write_json(output_dir / "section_synthesis_packets.json", projection["section_packets"])
    _write_json(output_dir / "section_contract_overlap_report.json", projection["section_contract_overlap_report"])
    _write_json(output_dir / "projection_evaluation_packet.json", projection["projection_evaluation_packet"])
    sample_runs = []
    for sample_index in range(1, max(1, samples) + 1):
        sample_dir = output_dir / f"sample_{sample_index:02d}"
        sample_dir.mkdir(parents=True, exist_ok=True)
        recorder = LivePromptRecorder()
        sample_started = time.time()
        generation = run_parallel_memo_ready_section_generation(
            projection["section_plan"],
            memo_ready_packet=inputs["memo_ready_packet"],
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            whole_prompt="Arm C prioritized-argument section synthesis.",
            run_model=recorder,
        )
        elapsed = round(time.time() - sample_started, 3)
        prompt_audit = audit_prompt_submissions(recorder.records)
        warning_adjudication = build_warning_adjudication_report(
            baseline_report_path=briefing_dir.parent / "replay_after_section_contract_fix_v3" / "report.json",
            arm_b_report=generation.get("report", {}),
        )
        comparison = build_arm_comparison_to_current(
            baseline_memo_path=briefing_dir.parent / "replay_after_section_contract_fix_v3" / "memo.md",
            baseline_report_path=briefing_dir.parent / "replay_after_section_contract_fix_v3" / "report.json",
            candidate_memo=str(generation.get("memo") or ""),
            candidate_report=_dict(generation.get("report")),
            prompt_audit=prompt_audit,
            elapsed_seconds=elapsed,
        )
        _write_json(sample_dir / "prompt_submission_audit.json", prompt_audit)
        _write_json(sample_dir / "section_prompt_manifest.json", prompt_manifest(recorder.records))
        _write_json(sample_dir / "warning_adjudication_report.json", warning_adjudication)
        _write_json(sample_dir / "report.json", generation.get("report", {}))
        _write_json(sample_dir / "comparison_to_current.json", comparison)
        if generation.get("memo"):
            (sample_dir / "memo.md").write_text(str(generation["memo"]), encoding="utf-8")
        if generation.get("prompt"):
            (sample_dir / "prompt.txt").write_text(str(generation["prompt"]), encoding="utf-8")
        if generation.get("raw"):
            (sample_dir / "raw.md").write_text(str(generation["raw"]), encoding="utf-8")
        sample_runs.append(
            {
                "sample": sample_index,
                "elapsed_seconds": elapsed,
                "generation_status": _dict(generation.get("report")).get("status"),
                "accepted": bool(_dict(generation.get("report")).get("accepted")),
                "prompt_audit_status": prompt_audit.get("status"),
                "warning_adjudication_status": warning_adjudication.get("status"),
                "comparison_status": comparison.get("status"),
                "quality_assessment": comparison.get("quality_assessment"),
                "artifact_dir": str(sample_dir),
            }
        )
    report = build_live_evaluation_aggregate_report(
        schema_id="arm_c_live_evaluation_report_v1",
        projection=projection,
        sample_runs=sample_runs,
        elapsed_seconds=round(time.time() - started, 3),
        extra={"prioritization_status": _dict(argument_run.get("report")).get("status")},
    )
    _write_json(output_dir / "comparison_to_current.json", report)
    _write_json(output_dir / "report.json", report)
    return {
        "prioritized_argument_run": argument_run,
        "projection": projection,
        "samples": sample_runs,
        "report": report,
    }


def run_arm_c_prioritization(
    inputs: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_arm_c_prioritization_prompt(inputs)
    if backend.strip() == "prompt":
        payload = _deterministic_arm_c_scaffold(inputs)
        raw = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            response_schema=ArmCPrioritizedArgument.model_json_schema(),
            num_predict=4096,
            json_mode=True,
        )
        raw = result.text
        payload = _extract_json(raw)
    report = verify_arm_c_prioritized_argument(inputs, payload)
    return {
        "accepted": report.get("status") == "pass",
        "prioritized_argument": payload if isinstance(payload, dict) else {},
        "prompt": prompt,
        "raw": raw,
        "report": report,
    }


def build_arm_c_prioritization_prompt(inputs: dict[str, Any]) -> str:
    analyst = _dict(inputs.get("analyst_decision_model"))
    packet = _dict(inputs.get("memo_ready_packet"))
    prompt_packet = {
        "decision_question": analyst.get("decision_question") or packet.get("decision_question"),
        "frozen_direct_answer": analyst.get("direct_answer") or analyst.get("full_direct_answer"),
        "confidence": analyst.get("confidence") or "not_specified",
        "decision_logic": _drop_empty(
            {
                "scope_boundaries": _string_list(_dict(analyst.get("decision_logic")).get("scope_boundaries")),
                "do_not_overstate": _string_list(_dict(analyst.get("decision_logic")).get("do_not_overstate")),
                "counterweight_weighting": _dict(analyst.get("decision_logic")).get("counterweight_weighting"),
                "what_would_change_the_answer": analyst.get("what_would_change_the_answer"),
            }
        ),
        "source_hierarchy": analyst.get("source_hierarchy"),
        "source_weight_judgments": analyst.get("source_weight_judgments"),
        "evidence_items": _arm_c_evidence_records(packet),
        "evidence_budget": _compact_evidence_budget(_dict(inputs.get("evidence_budget"))),
    }
    return (
        "You are creating a prioritized argument plan for a source-grounded decision memo.\n"
        "The direct answer, confidence, and decision question are frozen. Your job is only to decide which verified evidence items carry the answer, which items bound or challenge it, and what warrant connects them.\n\n"
        "Return JSON matching this schema:\n"
        f"{json.dumps(ArmCPrioritizedArgument.model_json_schema(), indent=2, ensure_ascii=False)}\n\n"
        "Planning rules:\n"
        "- Use only evidence_item_ids listed in the input.\n"
        "- Keep the frozen_direct_answer exactly as provided.\n"
        "- Create a small set of ordered moves that would help a writer answer the decision question directly.\n"
        "- Each move should explain its proposition, warrant, and decision_effect.\n"
        "- Put primary support in answer_evidence, limits and contrary evidence in counterweights, and action guidance in practical_implication.\n"
        "- Account for important foreground and counterweight evidence as owned, appendix, demoted, or background.\n\n"
        "### Input\n"
        f"{json.dumps(prompt_packet, indent=2, ensure_ascii=False)}\n"
    )


def verify_arm_c_prioritized_argument(inputs: dict[str, Any], payload: Any) -> dict[str, Any]:
    issues = []
    try:
        parsed = ArmCPrioritizedArgument.model_validate(payload).model_dump()
    except ValidationError as exc:
        return {
            "schema_id": "arm_c_prioritized_argument_verification_report_v1",
            "status": "fail",
            "issues": ["schema_validation_failed", _short_text(str(exc), 1200)],
        }
    analyst = _dict(inputs.get("analyst_decision_model"))
    packet = _dict(inputs.get("memo_ready_packet"))
    known_ids = _writer_evidence_ids(packet)
    if parsed.get("decision_question") != (analyst.get("decision_question") or packet.get("decision_question")):
        issues.append("decision_question_drift")
    if parsed.get("frozen_direct_answer") != (analyst.get("direct_answer") or analyst.get("full_direct_answer")):
        issues.append("frozen_answer_drift")
    if parsed.get("confidence") != (analyst.get("confidence") or "not_specified"):
        issues.append("confidence_drift")
    move_ids = {str(row.get("move_id") or "") for row in _list(parsed.get("moves")) if isinstance(row, dict)}
    referenced_ids = [
        evidence_id
        for move in _list(parsed.get("moves"))
        if isinstance(move, dict)
        for evidence_id in _string_list(move.get("evidence_item_ids"))
    ]
    unknown_evidence = sorted({evidence_id for evidence_id in referenced_ids if evidence_id not in known_ids})
    if unknown_evidence:
        issues.append(f"unknown_evidence_ids:{', '.join(unknown_evidence)}")
    unknown_dependencies = sorted(
        {
            dependency
            for move in _list(parsed.get("moves"))
            if isinstance(move, dict)
            for dependency in _string_list(move.get("depends_on_move_ids"))
            if dependency not in move_ids
        }
    )
    if unknown_dependencies:
        issues.append(f"unknown_dependencies:{', '.join(unknown_dependencies)}")
    if _has_dependency_cycle(_list(parsed.get("moves"))):
        issues.append("dependency_cycle")
    required_ids = {
        evidence_id
        for move in _list(parsed.get("moves"))
        if isinstance(move, dict) and move.get("required")
        for evidence_id in _string_list(move.get("evidence_item_ids"))
    }
    if not required_ids:
        issues.append("no_required_evidence")
    accounted_ids = {
        str(row.get("evidence_item_id") or "").strip()
        for row in _list(parsed.get("evidence_accounting"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    foreground_ids = _foreground_and_counterweight_writer_ids(inputs)
    missing_accounting = sorted(foreground_ids - accounted_ids - required_ids)
    return {
        "schema_id": "arm_c_prioritized_argument_verification_report_v1",
        "status": "pass" if not issues else "fail",
        "known_evidence_id_count": len(known_ids),
        "move_count": len(_list(parsed.get("moves"))),
        "required_evidence_count": len(required_ids),
        "unknown_evidence_ids": unknown_evidence,
        "missing_foreground_accounting_ids": missing_accounting,
        "warnings": [f"missing_foreground_accounting:{', '.join(missing_accounting)}"] if missing_accounting else [],
        "issues": _dedupe(issues),
    }


def build_arm_c_projection(inputs: dict[str, Any], prioritized_argument: dict[str, Any]) -> dict[str, Any]:
    original_canonical = _dict(inputs.get("canonical_decision_writer_packet")) or _dict(
        _dict(inputs.get("memo_ready_packet")).get("canonical_decision_writer_packet")
    )
    moves = [_arm_c_move_to_argument_move(row) for row in _list(prioritized_argument.get("moves"))]
    canonical = {
        **original_canonical,
        "decision_argument_contract": {
            "schema_id": "decision_argument_contract_v1",
            "argument_moves": moves,
        },
    }
    projection = build_arm_b_projection({**inputs, "canonical_decision_writer_packet": canonical})
    projection["schema_id"] = "arm_c_prioritized_argument_projection_v1"
    projection["prioritized_argument_id"] = prioritized_argument.get("schema_id")
    projection_report = _dict(projection.get("projection_evaluation_packet"))
    projection["projection_evaluation_packet"] = {
        **projection_report,
        "schema_id": "arm_c_prioritized_argument_verification_projection_report_v1",
        "prioritized_argument_status": "pass",
    }
    return projection


def _arm_c_evidence_records(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": item.get("item_id"),
                    "reader_claim": _short_text(item.get("reader_claim") or item.get("claim"), 600),
                    "natural_bottom_line": _short_text(item.get("natural_bottom_line"), 500),
                    "role": item.get("role"),
                    "memo_function": item.get("memo_function"),
                    "memo_inclusion": item.get("memo_inclusion"),
                    "importance_rank": item.get("importance_rank"),
                    "decision_diagnosticity": _dict(item.get("decision_diagnosticity")).get("score"),
                    "answer_relation": item.get("answer_relation"),
                    "decision_relevance": _short_text(item.get("decision_relevance"), 320),
                    "include_reason": _short_text(item.get("include_reason"), 360),
                    "source_ids": _string_list(item.get("source_ids")),
                    "source_appraisal": item.get("source_appraisal"),
                    "quantities": _quantity_values_from_item(item),
                    "claim_context": _compact_claim_context(_dict(item.get("claim_context"))),
                    "must_use": item.get("must_use"),
                    "obligation_level": item.get("obligation_level"),
                    "must_preserve_terms": _string_list(item.get("must_preserve_terms")),
                    "caveat": _short_text(item.get("caveat"), 300),
                }
            )
        )
    return rows


def _compact_evidence_budget(evidence_budget: dict[str, Any]) -> dict[str, Any]:
    return {
        "foreground_evidence_item_ids": _string_list(evidence_budget.get("foreground_evidence_item_ids")),
        "counterweight_evidence_item_ids": _string_list(evidence_budget.get("counterweight_evidence_item_ids")),
        "scope_or_crux_evidence_item_ids": _string_list(evidence_budget.get("scope_or_crux_evidence_item_ids")),
        "rows": [
            _drop_empty(
                {
                    "evidence_item_id": row.get("evidence_item_id"),
                    "budget_class": row.get("budget_class"),
                    "memo_role": row.get("memo_role"),
                    "group_id": row.get("group_id"),
                    "rationale": _short_text(row.get("rationale"), 300),
                    "quantity_values": _string_list(row.get("quantity_values")),
                    "source_ids": _string_list(row.get("source_ids")),
                }
            )
            for row in _list(evidence_budget.get("rows"))
            if isinstance(row, dict)
        ],
    }


def _arm_c_move_to_argument_move(move: dict[str, Any]) -> dict[str, Any]:
    point = str(move.get("proposition") or "").strip()
    warrant = str(move.get("warrant") or "").strip()
    effect = str(move.get("decision_effect") or "").strip()
    disposition = str(move.get("counterweight_disposition") or "").strip()
    limitations = _string_list(move.get("limitations"))
    return _drop_empty(
        {
            "move_id": move.get("move_id"),
            "move_type": move.get("move_type") or move.get("primary_section"),
            "point": point,
            "writing_job": _short_text(" ".join(part for part in [warrant, effect] if part), 900),
            "section_id": move.get("primary_section"),
            "evidence_item_ids": _string_list(move.get("evidence_item_ids")),
            "disposition": disposition,
            "would_change_if": "; ".join(limitations),
            "required": bool(move.get("required", True)),
        }
    )


def _deterministic_arm_c_scaffold(inputs: dict[str, Any]) -> dict[str, Any]:
    analyst = _dict(inputs.get("analyst_decision_model"))
    items = _list(_dict(inputs.get("memo_ready_packet")).get("evidence_items"))
    answer_ids = [
        str(item.get("item_id") or "")
        for item in items
        if str(item.get("memo_function") or item.get("role") or "").lower() in {"answer_anchor", "strongest_support"}
    ][:4]
    counter_ids = [
        str(item.get("item_id") or "")
        for item in items
        if "counter" in str(item.get("role") or item.get("memo_function") or "").lower()
        or "boundary" in str(item.get("role") or item.get("memo_function") or "").lower()
    ][:5]
    scope_ids = [
        str(item.get("item_id") or "")
        for item in items
        if "scope" in str(item.get("role") or item.get("memo_function") or "").lower()
    ][:2]
    owned_ids = set(answer_ids + counter_ids + scope_ids)
    return {
        "schema_id": "arm_c_prioritized_argument_v1",
        "decision_question": analyst.get("decision_question"),
        "frozen_direct_answer": analyst.get("direct_answer") or analyst.get("full_direct_answer"),
        "confidence": analyst.get("confidence") or "not_specified",
        "argument_thesis": analyst.get("direct_answer") or analyst.get("full_direct_answer"),
        "moves": [
            {
                "move_id": "primary_support",
                "primary_section": "answer_evidence",
                "move_type": "primary_support",
                "proposition": "Establish the best current read from the strongest answer-carrying evidence.",
                "warrant": "The answer should be driven by evidence tied directly to the decision question.",
                "decision_effect": "Supports the frozen bounded answer.",
                "evidence_item_ids": answer_ids,
                "required": True,
            },
            {
                "move_id": "counterweight_bounds",
                "primary_section": "counterweights",
                "move_type": "counterweight_disposition",
                "proposition": "Show which evidence bounds the answer or makes it conditional.",
                "warrant": "Counterweights should calibrate scope and confidence rather than be generic caveats.",
                "decision_effect": "Defines where the frozen answer would be too broad.",
                "evidence_item_ids": counter_ids,
                "required": True,
            },
            {
                "move_id": "practical_action",
                "primary_section": "practical_implication",
                "move_type": "practical_implication",
                "proposition": "Translate the frozen answer and boundaries into reader action.",
                "warrant": "Action guidance should follow from the answer plus named boundaries.",
                "decision_effect": "Tells the reader what to do and when to update.",
                "evidence_item_ids": scope_ids,
                "required": False,
            },
        ],
        "evidence_accounting": [
            {
                "evidence_item_id": str(item.get("item_id") or ""),
                "disposition": "owned",
                "rationale": "Selected by deterministic prompt-backend scaffold.",
            }
            for item in items
            if str(item.get("item_id") or "") in owned_ids
        ],
        "planning_gaps": [],
    }


def _writer_evidence_ids(packet: dict[str, Any]) -> set[str]:
    return {
        str(item.get("item_id") or "").strip()
        for item in _list(packet.get("evidence_items"))
        if isinstance(item, dict) and str(item.get("item_id") or "").strip()
    }


def _foreground_and_counterweight_writer_ids(inputs: dict[str, Any]) -> set[str]:
    budget_ids = set(
        _string_list(_dict(inputs.get("evidence_budget")).get("foreground_evidence_item_ids"))
        + _string_list(_dict(inputs.get("evidence_budget")).get("counterweight_evidence_item_ids"))
    )
    rows = set()
    for item in _list(_dict(inputs.get("memo_ready_packet")).get("evidence_items")):
        if not isinstance(item, dict):
            continue
        writer_id = str(item.get("item_id") or "").strip()
        lineage = set(_string_list(_dict(item.get("lineage")).get("covered_evidence_item_ids")))
        if writer_id and (writer_id in budget_ids or lineage.intersection(budget_ids)):
            rows.add(writer_id)
    return rows


def _has_dependency_cycle(moves: list[dict[str, Any]]) -> bool:
    graph = {
        str(move.get("move_id") or "").strip(): _string_list(move.get("depends_on_move_ids"))
        for move in moves
        if isinstance(move, dict) and str(move.get("move_id") or "").strip()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in graph.get(node, []):
            if child in graph and visit(child):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def _quantity_values_from_item(item: dict[str, Any]) -> list[str]:
    values = []
    for quantity in _list(item.get("quantities")):
        if isinstance(quantity, dict):
            values.append(str(quantity.get("value") or quantity.get("quantity_text") or "").strip())
        else:
            values.append(str(quantity or "").strip())
    return [value for value in values if value]


def _compact_claim_context(context: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "population": context.get("population"),
            "exposure_or_option": context.get("exposure_or_option"),
            "outcome_or_endpoint": context.get("outcome_or_endpoint"),
            "stated_dose_or_threshold": context.get("stated_dose_or_threshold"),
            "evidence_design": context.get("evidence_design"),
            "stated_limitations": context.get("stated_limitations"),
        }
    )


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}
    candidates = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE))
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


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
