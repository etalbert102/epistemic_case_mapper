#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json
from epistemic_case_mapper.map_briefing_memo_ready_section_synthesis import run_parallel_memo_ready_section_generation
from epistemic_case_mapper.map_briefing_prioritized_argument_arm_b import load_frozen_arm_b_inputs
from epistemic_case_mapper.map_briefing_prioritized_argument_arm_c import (
    ArmCPrioritizedArgument,
    build_arm_c_projection,
    normalize_arm_c_prioritized_argument_ids,
    verify_arm_c_prioritized_argument,
)
from epistemic_case_mapper.map_briefing_prioritized_argument_evaluation import (
    build_arm_comparison_to_current,
    resolve_current_baseline,
)
from epistemic_case_mapper.model_backends import run_model_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment with a richer Arm C prioritized argument prompt.")
    parser.add_argument("--briefing-dir", required=True, help="Directory containing frozen memo-ready briefing artifacts.")
    parser.add_argument("--out", required=True, help="Output directory for experiment artifacts.")
    parser.add_argument("--backend", default="ollama:gemma4:12b-mlx")
    parser.add_argument("--backend-timeout", type=int, default=240)
    parser.add_argument("--backend-retries", type=int, default=0)
    parser.add_argument(
        "--quantity-plan",
        help="Optional quantity_obligation_plan.json. Defaults to BRIEFING_DIR/quantity_obligation_plan.json when present.",
    )
    args = parser.parse_args()

    started = time.time()
    briefing_dir = Path(args.briefing_dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    inputs = load_frozen_arm_b_inputs(briefing_dir)
    quantity_plan_path = Path(args.quantity_plan) if args.quantity_plan else briefing_dir / "quantity_obligation_plan.json"
    if quantity_plan_path.exists():
        inputs = {**inputs, "quantity_obligation_plan": _read_json(quantity_plan_path)}

    prompt = build_richer_prioritized_argument_prompt(inputs)
    (out / "prioritized_argument_prompt.txt").write_text(prompt, encoding="utf-8")
    result = run_model_backend(
        prompt,
        args.backend,
        timeout_seconds=args.backend_timeout,
        max_retries=args.backend_retries,
        response_schema=ArmCPrioritizedArgument.model_json_schema(),
        num_predict=6144,
        json_mode=True,
    )
    raw = result.text
    (out / "prioritized_argument_raw.txt").write_text(raw, encoding="utf-8")
    payload = _extract_json(raw)
    normalized, id_report = normalize_arm_c_prioritized_argument_ids(inputs, payload)
    quantity_context = _quantity_context(inputs)
    normalized, quantity_carry_report = _attach_selected_quantity_anchors(normalized, quantity_context)
    verification = {
        **verify_arm_c_prioritized_argument(inputs, normalized),
        "id_normalization_report": id_report,
        "quantity_carry_report": quantity_carry_report,
    }
    write_json(out / "prioritized_evidence_argument.json", normalized if isinstance(normalized, dict) else {})
    write_json(out / "prioritized_argument_verification_projection_report.json", verification)
    if verification.get("status") != "pass":
        write_json(
            out / "report.json",
            {
                "schema_id": "richer_prioritized_argument_experiment_report_v1",
                "status": "prioritization_failed",
                "accepted": False,
                "verification": verification,
                "elapsed_seconds": round(time.time() - started, 3),
            },
        )
        print(json.dumps({"status": "prioritization_failed", "out": str(out)}, indent=2))
        return

    projection = build_arm_c_projection(inputs, normalized)
    write_json(out / "section_synthesis_packets.json", projection.get("section_packets", []))
    write_json(out / "projection_evaluation_packet.json", projection.get("projection_evaluation_packet", {}))
    if projection.get("status") != "pass":
        write_json(
            out / "report.json",
            {
                "schema_id": "richer_prioritized_argument_experiment_report_v1",
                "status": "projection_failed",
                "accepted": False,
                "verification": verification,
                "projection": projection.get("projection_evaluation_packet", {}),
                "elapsed_seconds": round(time.time() - started, 3),
            },
        )
        print(json.dumps({"status": "projection_failed", "out": str(out)}, indent=2))
        return

    generation = run_parallel_memo_ready_section_generation(
        projection["section_plan"],
        memo_ready_packet=inputs["memo_ready_packet"],
        backend=args.backend,
        backend_timeout=args.backend_timeout,
        backend_retries=args.backend_retries,
        whole_prompt="Richer prioritized evidence argument section synthesis.",
    )
    if generation.get("memo"):
        (out / "memo.md").write_text(str(generation["memo"]), encoding="utf-8")
    if generation.get("prompt"):
        (out / "section_prompts.txt").write_text(str(generation["prompt"]), encoding="utf-8")
    if generation.get("raw"):
        (out / "section_raw.md").write_text(str(generation["raw"]), encoding="utf-8")
    write_json(out / "section_generation_report.json", generation.get("report", {}))
    baseline = resolve_current_baseline(briefing_dir)
    comparison = build_arm_comparison_to_current(
        baseline_memo_path=Path(str(baseline.get("memo_path") or "__missing_baseline_memo__.md")),
        baseline_report_path=Path(str(baseline.get("report_path") or "__missing_baseline_report__.json")),
        candidate_memo=str(generation.get("memo") or ""),
        candidate_report=generation.get("report", {}),
        prompt_audit={"schema_id": "not_run", "status": "not_run"},
        elapsed_seconds=round(time.time() - started, 3),
        baseline_resolution=baseline,
    )
    report = {
        "schema_id": "richer_prioritized_argument_experiment_report_v1",
        "status": "accepted" if generation.get("report", {}).get("accepted") else "section_generation_failed",
        "accepted": bool(generation.get("report", {}).get("accepted")),
        "move_count": len(normalized.get("moves", [])) if isinstance(normalized, dict) else 0,
        "required_evidence_count": verification.get("required_evidence_count"),
        "verification_status": verification.get("status"),
        "projection_status": projection.get("status"),
        "section_generation_status": generation.get("report", {}).get("status"),
        "comparison": comparison,
        "elapsed_seconds": round(time.time() - started, 3),
        "issues": generation.get("report", {}).get("issues", []),
    }
    write_json(out / "comparison_to_current.json", comparison)
    write_json(out / "report.json", report)
    print(json.dumps({"status": report["status"], "accepted": report["accepted"], "memo": str(out / "memo.md"), "out": str(out)}, indent=2))


def build_richer_prioritized_argument_prompt(inputs: dict[str, Any]) -> str:
    from epistemic_case_mapper.map_briefing_prioritized_argument_arm_c import (
        _arm_c_evidence_records,
        _compact_evidence_budget,
        _dict,
        _drop_empty,
        _must_account_writer_evidence_ids,
        _string_list,
    )

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
        "quantity_context": _quantity_context(inputs),
        "must_account_writer_evidence_item_ids": _must_account_writer_evidence_ids(inputs),
        "evidence_budget": _compact_evidence_budget(_dict(inputs.get("evidence_budget")), packet),
    }
    return (
        "You are an expert decision analyst building the argument plan for a source-grounded memo.\n"
        "The decision question, direct answer, and confidence are fixed. Your job is to turn verified evidence into a prioritized chain of reasoning that a writer can render as a crisp decision memo.\n\n"
        "Return JSON matching this schema:\n"
        f"{json.dumps(ArmCPrioritizedArgument.model_json_schema(), indent=2, ensure_ascii=False)}\n\n"
        "What good output looks like:\n"
        "- Create 4 to 7 inference-level moves, not one move per memo section.\n"
        "- Each move should make a specific analytical claim: source-weight rationale, quantitative calibration, counterweight force, scope boundary, or practical update rule.\n"
        "- Use `proposition` for the reader-facing claim the memo should make.\n"
        "- Use `warrant` to explain why the selected evidence has that force relative to alternatives or counterevidence.\n"
        "- Use `decision_effect` to state how this move changes advice, confidence, scope, or updating.\n"
        "- In counterweight moves, state whether the evidence reverses the answer, narrows its scope, lowers confidence, or is only background.\n"
        "- Prefer a small load-bearing set. Demote redundant/background evidence with a rationale instead of making every item required.\n"
        "- If two sources appear to conflict, explain the discriminating feature: population, dose, endpoint, study design, measurement, mechanism, or authority.\n"
        "- Tie quantitative evidence to its interpretive role: estimate, interval, threshold, dose-response boundary, or mechanistic magnitude.\n"
        "- When quantity_context contains decision-relevant quantities, place the important numbers inside proposition, warrant, decision_effect, or limitations so the section writer can use them naturally.\n"
        "- Make the practical implication depend on the earlier moves rather than restating them.\n\n"
        "ID rules:\n"
        "- Use only writer evidence item IDs from input evidence_items[].evidence_item_id in moves and evidence_accounting.\n"
        "- Treat upstream claim/relation IDs as lineage only; do not return them as evidence_item_ids.\n"
        "- Keep frozen_direct_answer exactly as provided.\n"
        "- Every ID in must_account_writer_evidence_item_ids should appear in a move or in evidence_accounting.\n\n"
        "### Input\n"
        f"{json.dumps(prompt_packet, indent=2, ensure_ascii=False)}\n"
    )


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}
    candidates = [text]
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


def _quantity_context(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    packet = inputs.get("memo_ready_packet") if isinstance(inputs.get("memo_ready_packet"), dict) else {}
    upstream_to_writer = _upstream_to_writer_id_map(packet)
    rows: list[dict[str, Any]] = []
    for row in _list(_dict(inputs.get("evidence_budget")).get("rows")):
        if not isinstance(row, dict):
            continue
        values = _string_list(row.get("quantity_values"))
        if not values:
            continue
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        rows.append(
            _drop_empty(
                {
                    "upstream_evidence_id": evidence_id,
                    "writer_evidence_item_ids": upstream_to_writer.get(evidence_id, []),
                    "quantity_values": values[:8],
                    "budget_class": row.get("budget_class"),
                    "memo_role": row.get("memo_role"),
                    "rationale": row.get("rationale"),
                    "source_ids": _string_list(row.get("source_ids")),
                    "source": "evidence_budget",
                }
            )
        )
    obligation_values: dict[str, list[str]] = {}
    obligation_rationales: dict[str, list[str]] = {}
    for row in _list(_dict(inputs.get("quantity_obligation_plan")).get("rows")):
        if not isinstance(row, dict):
            continue
        relevance = _dict(row.get("analyst_quantity_relevance"))
        evidence_id = str(relevance.get("evidence_item_id") or row.get("evidence_item_id") or "").strip()
        value = str(row.get("value") or row.get("quantity_text") or "").strip()
        if not evidence_id or not value:
            continue
        obligation_values.setdefault(evidence_id, [])
        if value not in obligation_values[evidence_id]:
            obligation_values[evidence_id].append(value)
        rationale = str(relevance.get("rationale") or "").strip()
        if rationale:
            obligation_rationales.setdefault(evidence_id, [])
            if rationale not in obligation_rationales[evidence_id]:
                obligation_rationales[evidence_id].append(rationale)
    for evidence_id, values in obligation_values.items():
        rows.append(
            _drop_empty(
                {
                    "upstream_evidence_id": evidence_id,
                    "writer_evidence_item_ids": upstream_to_writer.get(evidence_id, []),
                    "quantity_values": values[:8],
                    "rationale": "; ".join(obligation_rationales.get(evidence_id, [])[:2]),
                    "source": "quantity_obligation_plan",
                }
            )
        )
    return _dedupe_quantity_rows(rows)[:18]


def _upstream_to_writer_id_map(packet: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        writer_id = str(item.get("item_id") or "").strip()
        if not writer_id:
            continue
        mapping.setdefault(writer_id, [])
        if writer_id not in mapping[writer_id]:
            mapping[writer_id].append(writer_id)
        for upstream_id in _string_list(_dict(item.get("lineage")).get("covered_evidence_item_ids")):
            mapping.setdefault(upstream_id, [])
            if writer_id not in mapping[upstream_id]:
                mapping[upstream_id].append(writer_id)
    return mapping


def _dedupe_quantity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for row in rows:
        key = (
            str(row.get("upstream_evidence_id") or ""),
            tuple(_string_list(row.get("writer_evidence_item_ids"))),
            tuple(_string_list(row.get("quantity_values"))),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _attach_selected_quantity_anchors(payload: Any, quantity_context: list[dict[str, Any]]) -> tuple[Any, dict[str, Any]]:
    if not isinstance(payload, dict):
        return payload, {
            "schema_id": "selected_quantity_anchor_carry_report_v1",
            "status": "not_available",
            "move_count": 0,
            "augmented_move_count": 0,
            "issues": ["payload_not_dict"],
        }
    by_writer_id: dict[str, list[str]] = {}
    for row in quantity_context:
        values = _string_list(row.get("quantity_values"))
        if not values:
            continue
        rationale = str(row.get("rationale") or "").strip()
        value_text = ", ".join(values[:4])
        anchor = f"{value_text}" + (f" ({rationale})" if rationale else "")
        for writer_id in _string_list(row.get("writer_evidence_item_ids")):
            by_writer_id.setdefault(writer_id, [])
            if anchor not in by_writer_id[writer_id]:
                by_writer_id[writer_id].append(anchor)
    updated = json.loads(json.dumps(payload))
    augmented = []
    for move in _list(updated.get("moves")):
        if not isinstance(move, dict):
            continue
        anchors = []
        for evidence_id in _string_list(move.get("evidence_item_ids")):
            anchors.extend(by_writer_id.get(evidence_id, [])[:2])
        anchors = _dedupe_strings(anchors)[:4]
        if not anchors:
            continue
        anchor_text = "Quantitative anchors from selected evidence: " + "; ".join(anchors) + ". "
        warrant = str(move.get("warrant") or "").strip()
        if "Quantitative anchors from selected evidence:" not in warrant:
            move["warrant"] = (anchor_text + warrant).strip()
            augmented.append(
                {
                    "move_id": move.get("move_id"),
                    "evidence_item_ids": _string_list(move.get("evidence_item_ids")),
                    "anchor_count": len(anchors),
                }
            )
    return updated, {
        "schema_id": "selected_quantity_anchor_carry_report_v1",
        "status": "ready",
        "move_count": len(_list(updated.get("moves"))),
        "augmented_move_count": len(augmented),
        "augmented_moves": augmented,
        "issues": [],
    }


def _dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}


if __name__ == "__main__":
    main()
