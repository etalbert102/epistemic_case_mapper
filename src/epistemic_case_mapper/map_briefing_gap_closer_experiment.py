from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.map_briefing_memo_polish_diagnostics import prose_quality_diagnostics
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_validated_final_polish_validation_report,
    run_memo_ready_final_polish,
)
from epistemic_case_mapper.map_briefing_memo_ready_output_limits import memo_ready_section_num_predict
from epistemic_case_mapper.map_briefing_memo_ready_prompt import (
    build_memo_ready_packet_synthesis_prompt,
    build_memo_ready_section_synthesis_plan,
    build_memo_ready_section_synthesis_prompt,
)
from epistemic_case_mapper.map_briefing_memo_ready_section_synthesis import run_parallel_memo_ready_section_generation
from epistemic_case_mapper.map_briefing_priority_quantity_contracts import (
    build_priority_quantity_contract_coverage_report,
    build_priority_quantity_contracts,
)
from epistemic_case_mapper.map_briefing_reader_judgment_packet import build_reader_judgment_surface_report
from epistemic_case_mapper.map_briefing_source_bound_evidence import build_source_binding_report
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


VARIANT_IDS = ("baseline", "richer_bluf", "source_weighted_theses", "combined")


def build_gap_closer_experiment_variants(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build packet/section-plan variants for memo-quality gap-closing experiments."""

    baseline = _variant("baseline", packet, "Current production packet and section plan.")
    richer_bluf = _variant(
        "richer_bluf",
        _with_richer_bluf(packet),
        "Use existing answer-frame fields to make the assembled bottom line more decision-grade.",
    )
    source_weighted = _variant(
        "source_weighted_theses",
        packet,
        "Inject source-weighted thesis constraints into section-local prompts through existing analyst-move and top-context channels.",
        mutate_section_plan=True,
    )
    combined = _variant(
        "combined",
        _with_richer_bluf(packet),
        "Combine the richer BLUF with source-weighted section thesis constraints.",
        mutate_section_plan=True,
    )
    return {row["variant_id"]: row for row in (baseline, richer_bluf, source_weighted, combined)}


def write_gap_closer_experiment_inputs(packet: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    variants = build_gap_closer_experiment_variants(packet)
    summary = {
        "schema_id": "memo_gap_closer_experiment_inputs_v1",
        "variant_count": len(variants),
        "variants": {},
    }
    for variant_id, variant in variants.items():
        variant_dir = out_dir / variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        packet_variant = _dict(variant.get("packet"))
        section_plan = _dict(variant.get("section_plan"))
        (variant_dir / "memo_ready_packet.json").write_text(json.dumps(packet_variant, indent=2, ensure_ascii=False), encoding="utf-8")
        (variant_dir / "section_synthesis_plan.json").write_text(json.dumps(section_plan, indent=2, ensure_ascii=False), encoding="utf-8")
        (variant_dir / "whole_prompt.md").write_text(build_memo_ready_packet_synthesis_prompt(packet_variant), encoding="utf-8")
        for section in _list(section_plan.get("sections")):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("section_id") or "section").strip() or "section"
            (variant_dir / f"section_prompt_{section_id}.md").write_text(str(section.get("prompt") or ""), encoding="utf-8")
        summary["variants"][variant_id] = {
            "description": variant.get("description"),
            "bottom_line": section_plan.get("bottom_line"),
            "section_count": len(_list(section_plan.get("sections"))),
            "prompt_dir": str(variant_dir),
            "input_changes": variant.get("input_changes", []),
        }
    (out_dir / "experiment_inputs_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def run_gap_closer_live_experiment(
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    out_dir: Path,
    variants: list[str] | None = None,
    run_polish: bool = True,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    built = build_gap_closer_experiment_variants(packet)
    requested = variants or list(VARIANT_IDS)
    rows = []
    baseline_score: dict[str, Any] | None = None
    for variant_id in requested:
        if variant_id not in built:
            raise ValueError(f"unknown variant_id={variant_id!r}; expected one of {', '.join(VARIANT_IDS)}")
        variant = built[variant_id]
        variant_dir = out_dir / variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        packet_variant = _dict(variant.get("packet"))
        section_plan = _dict(variant.get("section_plan"))
        whole_prompt = build_memo_ready_packet_synthesis_prompt(packet_variant)
        synthesis = run_parallel_memo_ready_section_generation(
            section_plan,
            memo_ready_packet=packet_variant,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            whole_prompt=whole_prompt,
        )
        draft_memo = str(synthesis.get("memo") or "")
        polish = {"memo": draft_memo, "report": {"status": "skipped", "accepted": False, "applied": False}}
        final_memo = draft_memo
        if run_polish and draft_memo:
            polish = run_memo_ready_final_polish(
                draft_memo,
                packet_variant,
                backend=backend,
                backend_timeout=backend_timeout,
                backend_retries=backend_retries,
            )
            final_memo = str(polish.get("memo") or draft_memo)
        score = score_gap_closer_memo(final_memo, packet_variant, original_memo=draft_memo)
        if variant_id == "baseline":
            baseline_score = score
        delta = _score_delta(score, baseline_score) if baseline_score else {}
        _write_variant_outputs(
            variant_dir,
            variant=variant,
            synthesis=synthesis,
            polish=polish,
            final_memo=final_memo,
            score=score,
            delta=delta,
        )
        rows.append(
            {
                "variant_id": variant_id,
                "description": variant.get("description"),
                "synthesis_status": _dict(synthesis.get("report")).get("status"),
                "synthesis_accepted": bool(_dict(synthesis.get("report")).get("accepted")),
                "polish_status": _dict(polish.get("report")).get("status"),
                "polish_applied": bool(_dict(polish.get("report")).get("applied")),
                "score": score.get("headline"),
                "delta_vs_baseline": delta,
                "final_memo_path": str(variant_dir / "final_memo.md"),
            }
        )
    report = {
        "schema_id": "memo_gap_closer_live_experiment_report_v1",
        "backend": backend,
        "backend_timeout": backend_timeout,
        "backend_retries": backend_retries,
        "section_num_predict": memo_ready_section_num_predict(),
        "variant_count": len(rows),
        "variants": rows,
        "winner_by_proxy": _winner(rows),
    }
    (out_dir / "live_experiment_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def score_gap_closer_memo(memo: str, packet: dict[str, Any], *, original_memo: str | None = None) -> dict[str, Any]:
    original = original_memo if original_memo is not None else memo
    validation = build_validated_final_polish_validation_report(memo, packet, original_memo=original)
    source_binding = build_source_binding_report(memo, packet)
    quantity_coverage = build_priority_quantity_contract_coverage_report(memo, build_priority_quantity_contracts(packet))
    reader_judgments = build_reader_judgment_surface_report(memo, packet)
    prose = prose_quality_diagnostics(memo)
    decision = _decision_usefulness_proxies(memo)
    headline = {
        "word_count": len(memo.split()),
        "validation_warning_count": int(validation.get("warning_count", 0) or 0),
        "source_binding_warning_count": int(source_binding.get("warning_count", 0) or 0),
        "missing_priority_quantity_count": int(quantity_coverage.get("missing_contract_count", 0) or 0),
        "missing_reader_judgment_count": int(reader_judgments.get("missing_count", 0) or 0),
        "prose_warning_count": int(prose.get("warning_count", 0) or 0),
        "decision_proxy_score": decision["score"],
    }
    headline["lower_is_better_total"] = (
        headline["validation_warning_count"]
        + headline["source_binding_warning_count"]
        + headline["missing_priority_quantity_count"]
        + headline["missing_reader_judgment_count"]
        + headline["prose_warning_count"]
    )
    return {
        "schema_id": "memo_gap_closer_score_v1",
        "headline": headline,
        "decision_usefulness_proxies": decision,
        "validation_report": validation,
        "source_binding_report": source_binding,
        "priority_quantity_contract_coverage_report": quantity_coverage,
        "reader_judgment_surface_report": reader_judgments,
        "prose_quality": prose,
    }


def _variant(
    variant_id: str,
    packet: dict[str, Any],
    description: str,
    *,
    mutate_section_plan: bool = False,
) -> dict[str, Any]:
    packet_variant = copy.deepcopy(packet)
    section_plan = build_memo_ready_section_synthesis_plan(packet_variant)
    changes = []
    if mutate_section_plan:
        changes = _apply_source_weighted_section_theses(section_plan, packet_variant)
    return {
        "variant_id": variant_id,
        "description": description,
        "packet": packet_variant,
        "section_plan": section_plan,
        "input_changes": changes,
    }


def _with_richer_bluf(packet: dict[str, Any]) -> dict[str, Any]:
    enriched = copy.deepcopy(packet)
    canonical = _dict(enriched.get("canonical_decision_writer_packet"))
    if not canonical:
        return enriched
    bluf = dict(_dict(canonical.get("bluf_contract")))
    balanced = _dict(canonical.get("balanced_answer_frame"))
    context = _decision_grade_bluf_context(bluf, balanced, canonical)
    if context.get("bottom_line"):
        bluf["recommended_read"] = context["bottom_line"]
        bluf["one_sentence_version"] = context["answer_sentence"]
    bluf["decision_grade_bluf_context"] = context
    canonical["bluf_contract"] = bluf
    balanced = dict(balanced)
    if context.get("bottom_line"):
        balanced["primary_answer"] = context["answer_sentence"]
        balanced["best_current_read"] = context["bottom_line"]
    canonical["balanced_answer_frame"] = balanced
    enriched["canonical_decision_writer_packet"] = canonical
    return enriched


def _decision_grade_bluf_context(bluf: dict[str, Any], balanced: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    answer = _first_text(bluf.get("one_sentence_version"), bluf.get("recommended_read"), balanced.get("primary_answer"))
    confidence = _first_text(bluf.get("confidence"), balanced.get("confidence"))
    usefulness = _dict(canonical.get("decision_usefulness_packet"))
    stance = _dict(usefulness.get("recommended_stance"))
    boundary = _compact_bluf_boundary(
        _first_text(
            stance.get("scope"),
            bluf.get("who_it_applies_to"),
            balanced.get("scope"),
            bluf.get("main_exception_or_boundary"),
            balanced.get("main_counterweight"),
            balanced.get("secondary_detail"),
        )
    )
    practical = _first_text(bluf.get("practical_read"), balanced.get("practical_read"))
    support = _first_text(balanced.get("main_support"))
    parts = [answer]
    if confidence:
        parts.append(f"Confidence: {confidence}.")
    if boundary:
        parts.append(f"Scope: {boundary}.")
    bottom_line = " ".join(part.rstrip(".") + "." for part in parts if part).strip()
    return {
        "schema_id": "decision_grade_bluf_context_v1",
        "answer_sentence": answer,
        "bottom_line": bottom_line,
        "confidence": confidence,
        "main_support": _short_text(support, 280),
        "main_boundary": _short_text(boundary, 280),
        "practical_read": _short_text(practical, 280),
        "writing_job": "Open with the decision stance, then scope/confidence, then the most important boundary.",
    }


def _compact_bluf_boundary(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    candidates = [part.strip() for part in re.split(r";|\n|(?<=\.)\s+", raw) if part.strip()]
    generic_fragments = ("state the answer", "population, option, or use case", "supported by the evidence")
    for candidate in candidates:
        lowered = candidate.lower()
        if any(fragment in lowered for fragment in generic_fragments):
            continue
        if 35 <= len(candidate) <= 240:
            return candidate.rstrip(".")
    first = candidates[0] if candidates else raw
    if len(first) <= 240:
        return first.rstrip(".")
    clipped = first[:240].rsplit(" ", 1)[0].strip()
    return clipped.rstrip(" ,;:.") + "..."


def _apply_source_weighted_section_theses(section_plan: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    contract = _dict(canonical.get("source_weighting_contract")) or _dict(packet.get("source_weighting_contract"))
    lane_cards = _list(contract.get("lane_cards"))
    lane_summary = _lane_summary(lane_cards)
    changes = []
    for section in _list(section_plan.get("sections")):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id") or "").strip()
        packet_section = _dict(section.get("packet"))
        thesis = _section_source_weighted_thesis(section_id, contract, lane_summary)
        if not thesis:
            continue
        top = dict(_dict(packet_section.get("top_context")))
        top["source_hierarchy_thesis"] = thesis["thesis"]
        packet_section["top_context"] = top
        focus = dict(_dict(packet_section.get("section_focus")))
        if thesis.get("prose_lead"):
            focus["prose_lead"] = thesis["prose_lead"]
        if thesis.get("paragraph_shape"):
            focus["paragraph_shape"] = thesis["paragraph_shape"]
        packet_section["section_focus"] = focus
        analyst_moves = _list(packet_section.get("analyst_argument_moves"))
        analyst_moves.insert(
            0,
            {
                "step_id": f"source_weighted_{section_id}",
                "section_id": section_id,
                "writing_goal": thesis["thesis"],
                "required_points": thesis.get("required_points", []),
        },
    )
        packet_section["analyst_argument_moves"] = analyst_moves
        section["packet"] = packet_section
        section["prompt"] = build_memo_ready_section_synthesis_prompt(
            packet_section,
            known_source_ids=_string_list(section_plan.get("known_source_ids")),
        )
        changes.append({"section_id": section_id, "thesis": thesis["thesis"]})
    return changes


def _section_source_weighted_thesis(section_id: str, contract: dict[str, Any], lane_summary: dict[str, dict[str, Any]]) -> dict[str, Any]:
    hierarchy = _short_text(str(contract.get("hierarchy_thesis") or ""), 420)
    primary = lane_summary.get("primary_answer_drivers", {})
    calibrators = lane_summary.get("quantitative_calibrators", {})
    counters = lane_summary.get("counterweight_sources", {})
    scope = lane_summary.get("scope_boundary_sources", {})
    context = lane_summary.get("contextual_sources", {})
    if section_id == "source_weighting":
        return {
            "thesis": hierarchy or _join_parts(
                "Read the sources in layers:",
                _lane_phrase("answer drivers", primary),
                _lane_phrase("calibrators", calibrators),
                _lane_phrase("bounds", counters),
                _lane_phrase("scope/context", scope or context),
            ),
            "prose_lead": "Open by telling the reader which sources should carry the decision and which should only bound, calibrate, or contextualize it.",
            "required_points": [
                _lane_phrase("Primary answer drivers", primary),
                _lane_phrase("Counterweights and boundaries", counters or scope),
                _lane_phrase("Calibrators and context", calibrators or context),
            ],
        }
    if section_id == "answer_evidence":
        return {
            "thesis": _join_parts(
                "Make the affirmative case from the evidence that carries the answer first.",
                _lane_phrase("Driver sources", primary),
                _lane_phrase("Quantitative calibrators", calibrators),
                "Use counterweight sources only to calibrate confidence here; leave boundaries to the boundary section.",
            ),
            "prose_lead": "Open with the driver evidence and the quantity or pattern that makes the current read the best answer.",
            "paragraph_shape": ["driver evidence and key quantity", "why source hierarchy supports the read", "brief confidence calibration"],
            "required_points": [_lane_phrase("Driver evidence", primary), _lane_phrase("Calibration evidence", calibrators)],
        }
    if section_id == "counterweights":
        return {
            "thesis": _join_parts(
                "Use boundary and counterweight evidence to say what narrows the answer, not to re-run the affirmative case.",
                _lane_phrase("Counterweight sources", counters),
                _lane_phrase("Scope boundary sources", scope),
            ),
            "prose_lead": "Open with the highest-value boundary or update trigger and explain whether it narrows, weakens, or could overturn the current read.",
            "paragraph_shape": ["strongest boundary", "why it narrows or updates rather than replaces the answer", "monitoring trigger"],
            "required_points": [_lane_phrase("Counterweight evidence", counters), _lane_phrase("Scope boundary evidence", scope)],
        }
    if section_id == "practical_implication":
        return {
            "thesis": _join_parts(
                "Translate the answer-driving sources into default guidance, then apply the scope and counterweight sources as exceptions.",
                _lane_phrase("Default guidance", primary or calibrators),
                _lane_phrase("Exceptions", scope or counters),
            ),
            "prose_lead": "Open with the action inside scope, then state the exception-handling rule.",
            "paragraph_shape": ["default action", "exception handling", "wording that avoids overclaiming"],
            "required_points": [_lane_phrase("Default action evidence", primary or calibrators), _lane_phrase("Exception evidence", scope or counters)],
        }
    return {}


def _lane_summary(lane_cards: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in lane_cards:
        if not isinstance(row, dict):
            continue
        lane = str(row.get("lane") or "").strip()
        if not lane:
            continue
        current = out.setdefault(lane, {"lane": lane, "source_ids": [], "evidence_item_ids": [], "rationales": [], "role_descriptions": []})
        current["source_ids"].extend(_string_list(row.get("source_ids")))
        current["evidence_item_ids"].extend(_string_list(row.get("evidence_item_ids")))
        if row.get("rationale"):
            current["rationales"].append(str(row.get("rationale")))
        if row.get("role_description") or row.get("role"):
            current["role_descriptions"].append(str(row.get("role_description") or row.get("role")))
    for row in out.values():
        row["source_ids"] = _dedupe(row["source_ids"])
        row["evidence_item_ids"] = _dedupe(row["evidence_item_ids"])
        row["rationales"] = _dedupe(row["rationales"])[:3]
        row["role_descriptions"] = _dedupe(row["role_descriptions"])[:3]
    return out


def _lane_phrase(label: str, lane: dict[str, Any]) -> str:
    if not lane:
        return ""
    role = "; ".join(_string_list(lane.get("role_descriptions"))[:2])
    rationale = "; ".join(_string_list(lane.get("rationales"))[:1])
    bits = [f"{label}: {role}" if role else label, rationale]
    return _short_text("; ".join(bit for bit in bits if bit), 360)


def _decision_usefulness_proxies(memo: str) -> dict[str, Any]:
    bottom_line = _extract_bottom_line(memo)
    text = str(memo or "")
    checks = {
        "bottom_line_has_scope_or_boundary": _has_any(bottom_line, ("scope", "boundary", "except", "however", "generally", "applies", "limit")),
        "bottom_line_has_confidence": _has_any(bottom_line, ("confidence", "high", "medium", "low", "uncertain")),
        "memo_has_update_trigger": _has_any(text, ("would change", "would update", "monitoring trigger", "re-evaluate", "crux")),
        "memo_has_practical_action": _has_any(text, ("should", "advise", "use this", "practical", "action", "recommend")),
        "memo_has_source_hierarchy": _has_any(text, ("source hierarchy", "carries the answer", "drives", "bounds", "calibrates", "contextualizes")),
    }
    return {
        "score": sum(1 for passed in checks.values() if passed),
        "checks": checks,
        "bottom_line": bottom_line,
    }


def _write_variant_outputs(
    variant_dir: Path,
    *,
    variant: dict[str, Any],
    synthesis: dict[str, Any],
    polish: dict[str, Any],
    final_memo: str,
    score: dict[str, Any],
    delta: dict[str, Any],
) -> None:
    (variant_dir / "memo_ready_packet.json").write_text(json.dumps(variant.get("packet"), indent=2, ensure_ascii=False), encoding="utf-8")
    (variant_dir / "section_synthesis_plan.json").write_text(json.dumps(variant.get("section_plan"), indent=2, ensure_ascii=False), encoding="utf-8")
    (variant_dir / "synthesis_report.json").write_text(json.dumps(synthesis.get("report", {}), indent=2, ensure_ascii=False), encoding="utf-8")
    (variant_dir / "synthesis_prompt.md").write_text(str(synthesis.get("prompt") or ""), encoding="utf-8")
    (variant_dir / "synthesis_raw.md").write_text(str(synthesis.get("raw") or ""), encoding="utf-8")
    (variant_dir / "draft_memo.md").write_text(str(synthesis.get("memo") or ""), encoding="utf-8")
    (variant_dir / "polish_report.json").write_text(json.dumps(polish.get("report", {}), indent=2, ensure_ascii=False), encoding="utf-8")
    (variant_dir / "polish_raw.md").write_text(str(polish.get("raw") or ""), encoding="utf-8")
    (variant_dir / "final_memo.md").write_text(final_memo, encoding="utf-8")
    (variant_dir / "score.json").write_text(json.dumps(score, indent=2, ensure_ascii=False), encoding="utf-8")
    (variant_dir / "delta_vs_baseline.json").write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")


def _score_delta(score: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    if not baseline:
        return {}
    current = _dict(score.get("headline"))
    base = _dict(baseline.get("headline"))
    fields = [
        "validation_warning_count",
        "source_binding_warning_count",
        "missing_priority_quantity_count",
        "missing_reader_judgment_count",
        "prose_warning_count",
        "decision_proxy_score",
        "lower_is_better_total",
    ]
    return {field: int(current.get(field, 0) or 0) - int(base.get(field, 0) or 0) for field in fields}


def _winner(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in rows if row.get("synthesis_accepted")]
    if not accepted:
        return {"variant_id": "", "reason": "no accepted variants"}
    return min(
        accepted,
        key=lambda row: (
            int(_dict(row.get("score")).get("lower_is_better_total", 9999) or 9999),
            -int(_dict(row.get("score")).get("decision_proxy_score", 0) or 0),
        ),
    )


def _extract_bottom_line(memo: str) -> str:
    match = re.search(r"(?im)^\*\*Bottom Line:\*\*\s*(.+)$", str(memo or ""))
    return match.group(1).strip() if match else ""


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _join_parts(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if str(part or "").strip())


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(needle in lowered for needle in needles)
