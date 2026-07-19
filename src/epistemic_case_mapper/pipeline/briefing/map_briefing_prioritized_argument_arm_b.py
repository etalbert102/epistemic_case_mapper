from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_section_synthesis import (
    run_parallel_memo_ready_section_generation,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_evidence_anchoring import (
    build_evidence_expression_contracts,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_synthesis_logic import (
    bounded_answer_required as _bounded_answer_required,
    build_synthesis_constraints as _synthesis_constraints,
    calibrated_bottom_line as _calibrated_bottom_line,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_arm_b_audit import (
    ARM_B_READER_QUESTIONS,
    ARM_B_SECTION_HEADINGS,
    ARM_B_SECTION_IDS,
    ARM_B_SECTION_JOBS,
    PromptCapture,
    arm_b_strict_section_prompt,
    audit_arm_b_section_packets,
    audit_prompt_submissions,
    build_warning_adjudication_report,
    prompt_manifest,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_evaluation import (
    LivePromptRecorder,
    build_arm_comparison_to_current,
    build_live_evaluation_aggregate_report,
    resolve_current_baseline,
)


def load_frozen_arm_b_inputs(briefing_dir: Path) -> dict[str, Any]:
    memo_ready_packet_path, memo_ready_packet = _load_usable_memo_ready_packet(briefing_dir)
    analyst_memo_ready_packet = _read_json(briefing_dir / "analyst_memo_ready_packet.json")
    return {
        "memo_ready_packet": memo_ready_packet,
        "memo_ready_packet_source": memo_ready_packet_path.name if memo_ready_packet_path else "",
        "analyst_memo_ready_packet": analyst_memo_ready_packet,
        "canonical_decision_writer_packet": _read_json(briefing_dir / "canonical_decision_writer_packet.json"),
        "analyst_decision_model": _read_json(briefing_dir / "analyst_decision_model.json"),
        "analyst_decision_model_verification_report": _read_json(
            briefing_dir / "analyst_decision_model_verification_report.json"
        ),
        "evidence_budget": _read_json(briefing_dir / "evidence_budget.json"),
        "evidence_accounting_report": _read_json(briefing_dir / "evidence_accounting_report.json"),
        "analyst_evidence_ledger": _read_json(briefing_dir / "analyst_evidence_ledger.json"),
    }


def build_arm_b_projection(inputs: dict[str, Any]) -> dict[str, Any]:
    memo_ready_packet = _dict(inputs.get("memo_ready_packet"))
    canonical = _dict(inputs.get("canonical_decision_writer_packet")) or _dict(
        memo_ready_packet.get("canonical_decision_writer_packet")
    )
    analyst_model = _dict(inputs.get("analyst_decision_model"))
    verifier = _dict(inputs.get("analyst_decision_model_verification_report"))
    evidence_budget = _dict(inputs.get("evidence_budget"))
    ledger = _dict(inputs.get("analyst_evidence_ledger"))
    issues = []
    warnings = []

    if not verifier.get("accepted"):
        issues.append("analyst_decision_model_verifier_not_accepted")
    question_report = _decision_question_report(memo_ready_packet, analyst_model, evidence_budget, ledger)
    if question_report["status"] != "pass":
        issues.append("decision_question_mismatch")

    contracts = build_evidence_expression_contracts(
        {**memo_ready_packet, "canonical_decision_writer_packet": canonical}
    )
    contracts_by_id: dict[str, dict[str, Any]] = {}
    duplicate_contract_ids = []
    for contract in contracts:
        evidence_id = str(contract.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        if evidence_id in contracts_by_id:
            duplicate_contract_ids.append(evidence_id)
            continue
        contracts_by_id[evidence_id] = contract
    if duplicate_contract_ids:
        issues.append("duplicate_contract_id")

    writer_items = [
        row for row in _list(memo_ready_packet.get("evidence_items")) if isinstance(row, dict)
    ]
    writer_ids = [str(row.get("item_id") or "").strip() for row in writer_items if str(row.get("item_id") or "").strip()]
    writer_id_uniqueness = {
        "count": len(writer_ids),
        "unique_count": len(set(writer_ids)),
        "status": "pass" if len(writer_ids) == len(set(writer_ids)) else "fail",
    }
    if writer_id_uniqueness["status"] != "pass":
        issues.append("duplicate_writer_evidence_id")

    lineage_index = _lineage_index(writer_items, contracts_by_id)
    lineage_fanout = {
        key: value for key, value in lineage_index.items() if len(value) > 1
    }
    decision_anchor = _decision_anchor(memo_ready_packet, analyst_model)
    contract_owner_candidates, resolver_issues = _owner_candidates(canonical, contracts_by_id, lineage_index)
    issues.extend(resolver_issues)
    mandatory_ids = _mandatory_writer_ids(writer_items, override=inputs.get("mandatory_evidence_ids_override"))
    ownership, ownership_issues = _resolve_ownership(contracts, contract_owner_candidates, mandatory_ids)
    issues.extend(ownership_issues)
    section_packets = _section_packets(
        ownership,
        contracts_by_id,
        canonical,
        decision_anchor=decision_anchor,
        mandatory_ids=mandatory_ids,
        known_source_ids=_known_source_ids(memo_ready_packet),
        known_source_aliases={},
    )
    packet_audit = audit_arm_b_section_packets(section_packets)
    if packet_audit["status"] != "pass":
        issues.extend(packet_audit["issues"])
    overlap_report = _overlap_report(section_packets)
    if overlap_report["required_intersection_count"]:
        issues.append("required_evidence_overlap")
    expected_report = _fixture_expectation_report(section_packets)
    if expected_report["status"] != "pass":
        warnings.append("frozen_fixture_expectation_not_met")

    projection_report = {
        "schema_id": "arm_b_projection_report_v1",
        "status": "pass" if not issues else "fail",
        "issues": _dedupe(issues),
        "warnings": _dedupe([*warnings, *_string_list(verifier.get("warnings"))]),
        "question_report": question_report,
        "analyst_verifier_status": verifier.get("status"),
        "analyst_verifier_accepted": bool(verifier.get("accepted")),
        "writer_id_uniqueness": writer_id_uniqueness,
        "lineage_fanout": lineage_fanout,
        "mandatory_evidence_ids": sorted(mandatory_ids),
        "ownership": ownership,
        "packet_audit": packet_audit,
        "overlap_report": overlap_report,
        "frozen_fixture_expectation_report": expected_report,
    }
    return {
        "schema_id": "arm_b_slim_existing_argument_projection_v1",
        "status": projection_report["status"],
        "section_plan": _section_plan(section_packets, decision_anchor),
        "section_packets": section_packets,
        "section_contract_overlap_report": overlap_report,
        "projection_evaluation_packet": projection_report,
    }


def run_arm_b_b0(
    *,
    briefing_dir: Path,
    output_dir: Path,
    force_retry: bool = True,
) -> dict[str, Any]:
    started = time.time()
    inputs = load_frozen_arm_b_inputs(briefing_dir)
    projection = build_arm_b_projection(inputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    _copy_frozen_inputs(briefing_dir, output_dir / "frozen_inputs")
    _write_json(output_dir / "section_synthesis_packets.json", projection["section_packets"])
    _write_json(output_dir / "section_contract_overlap_report.json", projection["section_contract_overlap_report"])
    _write_json(output_dir / "projection_evaluation_packet.json", projection["projection_evaluation_packet"])

    capture = PromptCapture(force_retry=force_retry)
    previous_attempts = None
    if force_retry:
        import os

        previous_attempts = os.environ.get("ECM_MODEL_STAGE_ATTEMPTS")
        os.environ["ECM_MODEL_STAGE_ATTEMPTS"] = "2"
    try:
        generation = run_parallel_memo_ready_section_generation(
            projection["section_plan"],
            memo_ready_packet=inputs["memo_ready_packet"],
            backend="fake-arm-b-b0",
            backend_timeout=30,
            backend_retries=0,
            whole_prompt="Arm B B0 deterministic projection prompt capture.",
            run_model=capture,
        )
    finally:
        if force_retry:
            import os

            if previous_attempts is None:
                os.environ.pop("ECM_MODEL_STAGE_ATTEMPTS", None)
            else:
                os.environ["ECM_MODEL_STAGE_ATTEMPTS"] = previous_attempts

    prompt_audit = audit_prompt_submissions(capture.records)
    _write_json(output_dir / "prompt_submission_audit.json", prompt_audit)
    _write_json(output_dir / "section_prompt_manifest.json", prompt_manifest(capture.records))
    warning_adjudication = build_warning_adjudication_report(
        baseline_report_path=_baseline_report_path(briefing_dir),
        arm_b_report=generation.get("report", {}),
    )
    _write_json(output_dir / "warning_adjudication_report.json", warning_adjudication)
    report = {
        "schema_id": "arm_b_b0_report_v1",
        "status": "pass"
        if projection["status"] == "pass" and prompt_audit["status"] == "pass"
        else "fail",
        "projection_status": projection["status"],
        "prompt_audit_status": prompt_audit["status"],
        "generation_status": _dict(generation.get("report")).get("status"),
        "section_count": len(_list(projection.get("section_packets"))),
        "elapsed_seconds": round(time.time() - started, 3),
        "issues": _dedupe(
            [
                *_string_list(_dict(projection.get("projection_evaluation_packet")).get("issues")),
                *_string_list(prompt_audit.get("issues")),
            ]
        ),
    }
    _write_json(output_dir / "report.json", report)
    if generation.get("memo"):
        (output_dir / "memo.md").write_text(str(generation["memo"]), encoding="utf-8")
    return {
        "projection": projection,
        "generation": generation,
        "prompt_submission_audit": prompt_audit,
        "warning_adjudication_report": warning_adjudication,
        "report": report,
    }


def run_arm_b_b1(
    *,
    briefing_dir: Path,
    output_dir: Path,
    backend: str,
    backend_timeout: int | None = 120,
    backend_retries: int = 0,
    samples: int = 1,
) -> dict[str, Any]:
    started = time.time()
    inputs = load_frozen_arm_b_inputs(briefing_dir)
    projection = build_arm_b_projection(inputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    _copy_frozen_inputs(briefing_dir, output_dir / "frozen_inputs")
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
            whole_prompt="Arm B B1 slim existing-argument section synthesis.",
            run_model=recorder,
        )
        elapsed = round(time.time() - sample_started, 3)
        prompt_audit = audit_prompt_submissions(recorder.records)
        baseline_resolution = resolve_current_baseline(briefing_dir)
        warning_adjudication = build_warning_adjudication_report(
            baseline_report_path=Path(str(baseline_resolution.get("report_path") or "__missing_baseline_report__.json")),
            arm_b_report=generation.get("report", {}),
        )
        comparison = build_arm_comparison_to_current(
            baseline_memo_path=Path(str(baseline_resolution.get("memo_path") or "__missing_baseline_memo__.md")),
            baseline_report_path=Path(str(baseline_resolution.get("report_path") or "__missing_baseline_report__.json")),
            candidate_memo=str(generation.get("memo") or ""),
            candidate_report=_dict(generation.get("report")),
            prompt_audit=prompt_audit,
            elapsed_seconds=elapsed,
            baseline_resolution=baseline_resolution,
        )
        _write_json(sample_dir / "prompt_submission_audit.json", prompt_audit)
        _write_json(sample_dir / "section_prompt_manifest.json", prompt_manifest(recorder.records))
        _write_json(sample_dir / "warning_adjudication_report.json", warning_adjudication)
        _write_json(sample_dir / "report.json", generation.get("report", {}))
        _write_json(sample_dir / "comparison_to_current.json", comparison)
        if generation.get("prompt"):
            (sample_dir / "prompt.txt").write_text(str(generation["prompt"]), encoding="utf-8")
        if generation.get("raw"):
            (sample_dir / "raw.md").write_text(str(generation["raw"]), encoding="utf-8")
        if generation.get("memo"):
            (sample_dir / "memo.md").write_text(str(generation["memo"]), encoding="utf-8")
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
    aggregate = build_arm_b_b1_aggregate_report(
        projection=projection,
        sample_runs=sample_runs,
        elapsed_seconds=round(time.time() - started, 3),
    )
    _write_json(output_dir / "comparison_to_current.json", aggregate)
    _write_json(output_dir / "report.json", aggregate)
    return {
        "projection": projection,
        "samples": sample_runs,
        "report": aggregate,
    }


def build_arm_b_comparison_to_current(
    *,
    baseline_memo_path: Path,
    baseline_report_path: Path,
    arm_b_memo: str,
    arm_b_report: dict[str, Any],
    prompt_audit: dict[str, Any],
    elapsed_seconds: float,
) -> dict[str, Any]:
    report = build_arm_comparison_to_current(
        baseline_memo_path=baseline_memo_path,
        baseline_report_path=baseline_report_path,
        candidate_memo=arm_b_memo,
        candidate_report=arm_b_report,
        prompt_audit=prompt_audit,
        elapsed_seconds=elapsed_seconds,
    )
    return {**report, "schema_id": "arm_b_comparison_to_current_v1", "arm_b": report.get("candidate", {})}


def build_arm_b_b1_aggregate_report(
    *,
    projection: dict[str, Any],
    sample_runs: list[dict[str, Any]],
    elapsed_seconds: float,
) -> dict[str, Any]:
    return build_live_evaluation_aggregate_report(
        schema_id="arm_b_b1_live_evaluation_report_v1",
        projection=projection,
        sample_runs=sample_runs,
        elapsed_seconds=elapsed_seconds,
    )


def _section_plan(section_packets: list[dict[str, Any]], decision_anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "arm_b_slim_section_synthesis_plan_v1",
        "status": "ready",
        "title": _short_decision_title(decision_anchor.get("decision_question")),
        "decision_question": decision_anchor.get("decision_question"),
        "bottom_line": _calibrated_bottom_line(decision_anchor),
        "confidence": decision_anchor.get("confidence"),
        "bounded_answer_required": _bounded_answer_required(decision_anchor),
        "evidence_contract_scope": "section_owned",
        "known_source_ids": _dedupe(
            source_id
            for packet in section_packets
            for contract in _list(packet.get("evidence_expression_contracts"))
            for source_id in _string_list(contract.get("citation_source_ids") or contract.get("source_ids"))
        ),
        "known_source_aliases": {},
        "sections": [
            {
                "section_id": packet["section_id"],
                "heading": packet["heading"],
                "packet": packet,
                "contracts": _list(packet.get("evidence_expression_contracts")),
                "prompt_mode": "arm_b_slim",
                "prompt": arm_b_strict_section_prompt(packet, _list(packet.get("evidence_expression_contracts"))),
            }
            for packet in section_packets
        ],
    }


def _section_packets(
    ownership: dict[str, str],
    contracts_by_id: dict[str, dict[str, Any]],
    canonical: dict[str, Any],
    *,
    decision_anchor: dict[str, Any],
    mandatory_ids: set[str],
    known_source_ids: list[str],
    known_source_aliases: dict[str, str],
) -> list[dict[str, Any]]:
    moves_by_section = _moves_by_section(canonical)
    synthesis_constraints = _synthesis_constraints(list(contracts_by_id.values()), decision_anchor)
    packets = []
    for section_id in ARM_B_SECTION_IDS:
        owned_contract_ids = [evidence_id for evidence_id, owner in ownership.items() if owner == section_id]
        contracts = [
            _contract_for_arm_b(contracts_by_id[evidence_id], required=evidence_id in mandatory_ids)
            for evidence_id in sorted(owned_contract_ids)
            if evidence_id in contracts_by_id
        ]
        owned_moves = [_compact_move(row) for row in moves_by_section.get(section_id, [])]
        packets.append(
            _drop_empty(
                {
                    "schema_id": "arm_b_slim_section_packet_v1",
                    "section_id": section_id,
                    "heading": ARM_B_SECTION_HEADINGS[section_id],
                    "section_job": ARM_B_SECTION_JOBS[section_id],
                    "reader_question": ARM_B_READER_QUESTIONS[section_id],
                    "decision_anchor": decision_anchor,
                    "calibration_limits": decision_anchor.get("do_not_overstate"),
                    "synthesis_constraints": synthesis_constraints,
                    "owned_moves": owned_moves,
                    "reference_moves": _reference_moves(section_id, moves_by_section),
                    "evidence_expression_contracts": contracts,
                    "section_local_evidence_jobs": _section_local_jobs(owned_moves, contracts),
                    "known_source_ids": known_source_ids,
                    "known_source_aliases": known_source_aliases,
                    "citation_mode": "evidence_tags" if contracts else "source_ids",
                }
            )
        )
    return packets


def _owner_candidates(
    canonical: dict[str, Any],
    contracts_by_id: dict[str, dict[str, Any]],
    lineage_index: dict[str, list[str]],
) -> tuple[dict[str, set[str]], list[str]]:
    candidates: dict[str, set[str]] = {}
    issues = []
    for move in _list(_dict(canonical.get("decision_argument_contract")).get("argument_moves")):
        if not isinstance(move, dict):
            continue
        section_id = str(move.get("section_id") or "").strip()
        if section_id not in ARM_B_SECTION_IDS:
            continue
        for reference in _string_list(move.get("evidence_item_ids")):
            resolved, reference_issues = _resolve_reference(reference, contracts_by_id, lineage_index)
            issues.extend(reference_issues)
            for evidence_id in resolved:
                candidates.setdefault(evidence_id, set()).add(section_id)
    return candidates, issues


def _resolve_reference(
    reference: str,
    contracts_by_id: dict[str, dict[str, Any]],
    lineage_index: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    reference = str(reference or "").strip()
    if reference in contracts_by_id:
        return [reference], []
    if reference.startswith(("claim:", "relation:")):
        resolved = lineage_index.get(reference, [])
        if not resolved:
            return [], [f"unknown_lineage_reference:{reference}"]
        return resolved, []
    return [], [f"unknown_evidence_id:{reference}"]


def _resolve_ownership(
    contracts: list[dict[str, Any]],
    candidates: dict[str, set[str]],
    mandatory_ids: set[str],
) -> tuple[dict[str, str], list[str]]:
    ownership: dict[str, str] = {}
    issues = []
    for contract in contracts:
        evidence_id = str(contract.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        candidate_sections = candidates.get(evidence_id, set())
        if not candidate_sections:
            if evidence_id in mandatory_ids:
                issues.append(f"unowned_mandatory_evidence:{evidence_id}")
            continue
        if len(candidate_sections) == 1:
            ownership[evidence_id] = next(iter(candidate_sections))
            continue
        primary = str(contract.get("primary_section") or "").strip()
        if primary in candidate_sections:
            ownership[evidence_id] = primary
            continue
        issues.append(f"ambiguous_owner:{evidence_id}:{','.join(sorted(candidate_sections))}")
    return ownership, issues


def _lineage_index(
    writer_items: list[dict[str, Any]],
    contracts_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for item in writer_items:
        writer_id = str(item.get("item_id") or "").strip()
        if not writer_id or writer_id not in contracts_by_id:
            continue
        for lineage_id in _string_list(_dict(item.get("lineage")).get("covered_evidence_item_ids")):
            index.setdefault(lineage_id, []).append(writer_id)
    return {key: _dedupe(values) for key, values in index.items()}


def _mandatory_writer_ids(writer_items: list[dict[str, Any]], *, override: Any = None) -> set[str]:
    override_ids = set(_string_list(override))
    if override_ids:
        return override_ids
    ids = set()
    for item in writer_items:
        writer_id = str(item.get("item_id") or "").strip()
        if not writer_id:
            continue
        if bool(item.get("must_use")) or str(item.get("obligation_level") or "") == "must_include":
            ids.add(writer_id)
            continue
        if any(_dict(row).get("must_retain") for row in _list(item.get("quantities"))):
            ids.add(writer_id)
    return ids


def _moves_by_section(canonical: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for move in _list(_dict(canonical.get("decision_argument_contract")).get("argument_moves")):
        if not isinstance(move, dict):
            continue
        section_id = str(move.get("section_id") or "").strip()
        if section_id in ARM_B_SECTION_IDS:
            rows.setdefault(section_id, []).append(move)
    return rows


def _reference_moves(section_id: str, moves_by_section: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
    if section_id != "practical_implication":
        return []
    rows = []
    for other_section, moves in moves_by_section.items():
        if other_section == section_id:
            continue
        for move in moves[:2]:
            point = _short_text(move.get("point"), 260)
            move_id = str(move.get("move_id") or "").strip()
            if move_id and point:
                rows.append({"move_id": move_id, "point": point})
    return rows[:4]


def _section_local_jobs(moves: list[dict[str, Any]], contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contract_ids = {str(row.get("evidence_id") or "") for row in contracts}
    jobs = []
    for move in moves:
        allowed = [evidence_id for evidence_id in _string_list(move.get("evidence_item_ids")) if evidence_id in contract_ids]
        if not allowed:
            continue
        jobs.append(
            _drop_empty(
                {
                    "job_id": move.get("move_id"),
                    "paragraph_job": move.get("writing_job") or move.get("point"),
                    "allowed_evidence_ids": allowed,
                    "required_quantities_by_evidence_id": {
                        evidence_id: _quantity_values(contracts, evidence_id)
                        for evidence_id in allowed
                        if _quantity_values(contracts, evidence_id)
                    },
                }
            )
        )
    return jobs


def _compact_move(move: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "move_id": move.get("move_id"),
            "move_type": move.get("move_type"),
            "point": _short_text(move.get("point"), 900),
            "writing_job": _short_text(move.get("writing_job"), 420),
            "section_id": move.get("section_id"),
            "evidence_item_ids": _string_list(move.get("evidence_item_ids")),
            "quantities": _string_list(move.get("quantities")),
            "disposition": _short_text(move.get("disposition"), 420),
            "would_change_if": _short_text(move.get("would_change_if"), 420),
        }
    )


def _contract_for_arm_b(contract: dict[str, Any], *, required: bool) -> dict[str, Any]:
    return _drop_empty(
        {
            **contract,
            "required": required,
        }
    )


def _overlap_report(section_packets: list[dict[str, Any]]) -> dict[str, Any]:
    required_by_section = {
        str(packet.get("section_id") or ""): {
            str(contract.get("evidence_id") or "")
            for contract in _list(packet.get("evidence_expression_contracts"))
            if isinstance(contract, dict) and contract.get("required")
        }
        for packet in section_packets
    }
    overlaps = []
    ids = list(required_by_section)
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            overlap = sorted(required_by_section[left].intersection(required_by_section[right]))
            if overlap:
                overlaps.append({"left": left, "right": right, "evidence_ids": overlap})
    return {
        "schema_id": "arm_b_section_contract_overlap_report_v1",
        "required_intersection_count": sum(len(row["evidence_ids"]) for row in overlaps),
        "overlaps": overlaps,
        "required_by_section": {key: sorted(value) for key, value in required_by_section.items()},
    }


def _fixture_expectation_report(section_packets: list[dict[str, Any]]) -> dict[str, Any]:
    required_by_section = _overlap_report(section_packets)["required_by_section"]
    expected = {
        "answer_evidence": [
            "decision_writer_item_001",
            "decision_writer_item_002",
            "decision_writer_item_003",
            "decision_writer_item_011",
        ],
        "counterweights": [
            "decision_writer_item_004",
            "decision_writer_item_005",
            "decision_writer_item_007",
            "decision_writer_item_008",
        ],
        "practical_implication": [],
    }
    mismatches = []
    for section_id, expected_ids in expected.items():
        actual = sorted(required_by_section.get(section_id, []))
        if actual != sorted(expected_ids):
            mismatches.append({"section_id": section_id, "expected": sorted(expected_ids), "actual": actual})
    return {
        "schema_id": "arm_b_frozen_fixture_expectation_report_v1",
        "status": "pass" if not mismatches else "warning",
        "mismatches": mismatches,
    }


def _decision_anchor(memo_ready_packet: dict[str, Any], analyst_model: dict[str, Any]) -> dict[str, Any]:
    logic = _dict(analyst_model.get("decision_logic"))
    return _drop_empty(
        {
            "decision_question": analyst_model.get("decision_question") or memo_ready_packet.get("decision_question"),
            "bounded_answer": analyst_model.get("direct_answer") or analyst_model.get("full_direct_answer"),
            "compact_answer": analyst_model.get("primary_answer"),
            "confidence": analyst_model.get("confidence"),
            "scope_boundaries": _string_list(logic.get("scope_boundaries")),
            "do_not_overstate": _string_list(logic.get("do_not_overstate")),
        }
    )


def _decision_question_report(
    memo_ready_packet: dict[str, Any],
    analyst_model: dict[str, Any],
    evidence_budget: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    rows = {
        "memo_ready_packet": memo_ready_packet.get("decision_question"),
        "analyst_decision_model": analyst_model.get("decision_question"),
        "evidence_budget": evidence_budget.get("decision_question"),
        "analyst_evidence_ledger": ledger.get("decision_question"),
    }
    values = [str(value).strip() for value in rows.values() if str(value or "").strip()]
    return {
        "schema_id": "arm_b_decision_question_report_v1",
        "status": "pass" if len(set(values)) <= 1 and values else "fail",
        "questions": rows,
    }


def _known_source_ids(memo_ready_packet: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *[
                source_id
                for row in _list(memo_ready_packet.get("source_trail"))
                if isinstance(row, dict)
                for source_id in _string_list(row.get("source_id"))
            ],
            *[
                source_id
                for item in _list(memo_ready_packet.get("evidence_items"))
                if isinstance(item, dict)
                for source_id in _string_list(item.get("source_ids"))
            ],
        ]
    )


def _quantity_values(contracts: list[dict[str, Any]], evidence_id: str) -> list[str]:
    for contract in contracts:
        if str(contract.get("evidence_id") or "") != evidence_id:
            continue
        return [str(row.get("value") or "").strip() for row in _list(contract.get("required_quantity_atoms")) if isinstance(row, dict) and row.get("value")]
    return []


def _copy_frozen_inputs(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "memo_ready_packet.json",
        "analyst_memo_ready_packet.json",
        "canonical_decision_writer_packet.json",
        "analyst_decision_model.json",
        "analyst_decision_model_verification_report.json",
        "evidence_budget.json",
        "evidence_accounting_report.json",
        "analyst_evidence_ledger.json",
    ):
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, target_dir / name)
    hashes = {path.name: _sha256_file(path) for path in sorted(target_dir.glob("*.json"))}
    _write_json(target_dir / "input_hashes.json", hashes)


def _load_usable_memo_ready_packet(briefing_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    first_path = briefing_dir / "memo_ready_packet.json"
    first_packet = _read_json(first_path)
    for path, packet in (
        (first_path, first_packet),
        (briefing_dir / "analyst_memo_ready_packet.json", _read_json(briefing_dir / "analyst_memo_ready_packet.json")),
    ):
        if _is_usable_memo_ready_packet(packet):
            return path, packet
    return (first_path if first_path.exists() else None), first_packet


def _is_usable_memo_ready_packet(packet: dict[str, Any]) -> bool:
    if not str(packet.get("decision_question") or "").strip():
        return False
    if not _list(packet.get("evidence_items")):
        return False
    return bool(
        _dict(packet.get("canonical_decision_writer_packet"))
        or _dict(packet.get("writer_packet"))
        or _dict(packet.get("answer_spine"))
        or _dict(packet.get("decision_usefulness_packet"))
    )


def _baseline_report_path(briefing_dir: Path) -> Path:
    return Path(str(resolve_current_baseline(briefing_dir).get("report_path") or "__missing_baseline_report__.json"))


def _short_decision_title(question: Any) -> str:
    text = re.sub(r"\s+", " ", str(question or "")).strip().rstrip("?")
    if not text:
        return "Decision Memo"
    return text[:80]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
