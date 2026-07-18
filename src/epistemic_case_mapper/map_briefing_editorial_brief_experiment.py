from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_ready_prompt import (
    build_memo_ready_section_synthesis_plan,
    build_memo_ready_section_synthesis_prompt,
)
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output


EDITORIAL_BRIEF_EXPERIMENT_SCHEMA = "editorial_brief_instruction_experiment_v1"

INTERNAL_CLUTTER_KEYS = {
    "analyst_decision_spine",
    "argument_spine",
    "balanced_answer_frame",
    "decision_argument_contract",
    "decision_usefulness",
    "lightweight_writer_guidance",
    "mandatory_retention_checklist",
    "organized_evidence_inventory",
    "reader_judgment_packet",
    "retention_requirements",
    "section_role_contract",
    "source_weighting_contract",
    "validation_contract",
}

OUTLINE_REBUILT_PACKET_KEYS = {
    "canonical_decision_writer_packet",
    "canonical_decision_writer_packet_quality_report",
    "decision_argument_contract",
    "decision_argument_contract_report",
    "decision_contract_source_judgment_lineage",
    "decision_memo_contract",
    "decision_synthesis_contract",
    "decision_writer_packet_quality_report",
    "model_source_weight_judgments",
    "model_source_weighting_report",
    "reader_judgment_packet",
    "source_weight_judgment_report",
    "source_weighting_contract",
    "source_weighting_flow_audit",
    "writer_decision_interface",
    "writer_decision_interface_quality_report",
    "writer_packet",
    "writer_packet_quality_report",
    "writer_packet_writeability_report",
}


@dataclass(frozen=True)
class EditorialInstructionVariant:
    variant_id: str
    label: str
    instructions: tuple[str, ...]
    input_mode: str
    include_evidence_rows: bool = True
    include_source_weighting: bool = True
    include_validation_obligations: bool = False
    exclude_low_value_context: bool = False


VARIANTS: tuple[EditorialInstructionVariant, ...] = (
    EditorialInstructionVariant(
        variant_id="minimal_thesis",
        label="Minimal Thesis Brief",
        input_mode="compact_editorial",
        instructions=(
            "Create one concise editorial brief for this memo section.",
            "Make the section thesis, reader job, and one must-land distinction explicit.",
            "Keep internal pipeline concepts out of reader-facing wording.",
        ),
        include_source_weighting=False,
    ),
    EditorialInstructionVariant(
        variant_id="source_weighted",
        label="Source-Weighted Editorial Brief",
        input_mode="compact_editorial",
        instructions=(
            "Create one concise editorial brief for this memo section.",
            "Explain why the section should weight the listed sources the way it does.",
            "State the thesis in source-weighted terms rather than as a source inventory.",
            "Keep internal pipeline concepts out of reader-facing wording.",
        ),
    ),
    EditorialInstructionVariant(
        variant_id="evidence_anchored",
        label="Evidence-Anchored Editorial Brief",
        input_mode="compact_editorial",
        instructions=(
            "Create one concise editorial brief for this memo section.",
            "State the section thesis, then map each required evidence item to a prose job.",
            "Preserve protected quantities and source IDs as writing obligations.",
            "Keep internal pipeline concepts out of reader-facing wording.",
        ),
        include_validation_obligations=True,
    ),
    EditorialInstructionVariant(
        variant_id="decision_curated",
        label="Decision-Curated Editorial Brief",
        input_mode="compact_editorial",
        instructions=(
            "Create one concise editorial brief for this memo section.",
            "Select only evidence that helps the section land a decision-relevant analytic move.",
            "Route source-context rows, appendix-only extraction notes, table descriptors, and low-atomicity residue out of the writing brief.",
            "State the section thesis as an analyst judgment, then assign each retained evidence item a specific prose job.",
            "Keep internal pipeline concepts out of reader-facing wording.",
        ),
        exclude_low_value_context=True,
    ),
    EditorialInstructionVariant(
        variant_id="full_packet_control",
        label="Full Packet Control",
        input_mode="raw_section_packet",
        instructions=(
            "Create one editorial brief for this memo section from the full section packet.",
            "Use the available contracts, source weighting, evidence, and validation obligations.",
            "Return only the editorial brief JSON.",
        ),
        include_validation_obligations=True,
    ),
)


def run_editorial_brief_instruction_experiment(
    memo_ready_packet: dict[str, Any],
    *,
    output_dir: str | Path,
    backend: str = "prompt",
    backend_timeout: int | None = 120,
    backend_retries: int = 0,
) -> dict[str, Any]:
    section_plan = build_memo_ready_section_synthesis_plan(memo_ready_packet)
    sections = _list(section_plan.get("sections"))
    if section_plan.get("status") != "ready" or not sections:
        raise ValueError("memo_ready_packet did not produce section synthesis packets")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in VARIANTS:
        variant_dir = out / variant.variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        section_results = [
            _run_variant_section(
                variant,
                section,
                backend=backend,
                backend_timeout=backend_timeout,
                backend_retries=backend_retries,
                output_dir=variant_dir,
            )
            for section in sections
        ]
        results.append(_variant_result(variant, section_results))
    summary = _experiment_summary(
        memo_ready_packet=memo_ready_packet,
        section_plan=section_plan,
        backend=backend,
        results=results,
    )
    write_json(out / "editorial_brief_instruction_experiment.json", summary)
    write_markdown(out / "EDITORIAL_BRIEF_INSTRUCTION_EXPERIMENT.md", render_editorial_brief_experiment_markdown(summary))
    return summary


def build_editorial_brief_prompt(section_packet: dict[str, Any], variant: EditorialInstructionVariant) -> str:
    schema = {
        "schema_id": "editorial_brief_v1",
        "section_id": "same section_id",
        "heading": "same heading",
        "reader_job": "one sentence: what this section must do for the reader",
        "section_thesis": "one sentence this section should land",
        "must_land_distinction": "the key distinction, boundary, or tradeoff this section must preserve",
        "evidence_to_use": [
            {
                "evidence_id": "stable evidence/item ID when available",
                "source_ids": ["source IDs"],
                "role": "load_bearing | counterweight | boundary | contextual",
                "prose_job": "how this evidence should function in the section",
                "required_detail": "number, endpoint, scope, or caveat to preserve",
            }
        ],
        "source_weighting_note": "why sources in this section should be weighted this way",
        "caveats_to_preserve": ["decision-relevant caveats"],
        "leave_to_other_sections": ["topics this section should only mention briefly or leave aside"],
    }
    packet = {
        "task": "Produce an editorial brief for one section writer. The brief will become the only semantic writing handoff for that section.",
        "instructions": list(variant.instructions),
        "return_schema": schema,
        "section_context": _variant_input_context(section_packet, variant),
    }
    return json.dumps(packet, indent=2, ensure_ascii=False)


def deterministic_editorial_brief(section_packet: dict[str, Any], variant: EditorialInstructionVariant) -> dict[str, Any]:
    compact = _compact_section_context(section_packet, variant)
    evidence_rows = _brief_evidence_rows(
        section_packet,
        include_validation=variant.include_validation_obligations,
        exclude_low_value_context=variant.exclude_low_value_context,
    )
    return {
        "schema_id": "editorial_brief_v1",
        "section_id": compact.get("section_id"),
        "heading": compact.get("heading"),
        "reader_job": compact.get("reader_job"),
        "section_thesis": _section_thesis(compact, evidence_rows),
        "must_land_distinction": _must_land_distinction(compact, evidence_rows),
        "evidence_to_use": evidence_rows if variant.include_evidence_rows else evidence_rows[:3],
        "source_weighting_note": _source_weighting_note(section_packet) if variant.include_source_weighting else "",
        "caveats_to_preserve": _caveats_to_preserve(section_packet),
        "leave_to_other_sections": _leave_to_other_sections(section_packet),
    }


def score_editorial_brief(
    brief: dict[str, Any],
    *,
    prompt: str,
    section_packet: dict[str, Any],
) -> dict[str, Any]:
    expected_sources = set(_expected_source_ids_for_score(section_packet))
    brief_sources = set()
    for row in _list(brief.get("evidence_to_use")):
        if isinstance(row, dict):
            brief_sources.update(_string_list(row.get("source_ids")))
    required_points = _required_point_count(section_packet)
    evidence_count = len(_list(brief.get("evidence_to_use")))
    low_value_evidence_count = _low_value_evidence_count(_list(brief.get("evidence_to_use")))
    required_fields = [
        "reader_job",
        "section_thesis",
        "must_land_distinction",
        "evidence_to_use",
        "source_weighting_note",
        "caveats_to_preserve",
        "leave_to_other_sections",
    ]
    missing_fields = [
        field
        for field in required_fields
        if field not in brief or brief.get(field) in ("", None)
    ]
    prompt_chars = len(prompt)
    clutter_hits = _clutter_hits(prompt)
    score = 100
    score -= min(25, max(0, prompt_chars - 4500) // 300)
    score -= min(20, len(clutter_hits) * 2)
    score -= len(missing_fields) * 7
    score += min(15, evidence_count * 2)
    score -= min(40, low_value_evidence_count * 10)
    if expected_sources:
        source_coverage = len(expected_sources & brief_sources) / len(expected_sources)
        score += round(source_coverage * 12)
    else:
        source_coverage = 1.0
    if required_points and evidence_count == 0:
        score -= 10
    if _looks_generic(brief):
        score -= 12
    return {
        "schema_id": "editorial_brief_score_v1",
        "score": max(0, min(100, int(score))),
        "prompt_chars": prompt_chars,
        "prompt_token_proxy": round(prompt_chars / 4),
        "clutter_hits": clutter_hits,
        "missing_fields": missing_fields,
        "evidence_count": evidence_count,
        "low_value_evidence_count": low_value_evidence_count,
        "required_point_count": required_points,
        "source_coverage": round(source_coverage, 3),
        "generic_language_warning": _looks_generic(brief),
    }


def render_editorial_brief_experiment_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Editorial Brief Instruction Experiment",
        "",
        f"Backend: `{summary.get('backend')}`",
        f"Recommended variant: `{summary.get('recommended_variant')}`",
        "",
        "## Variant Scores",
        "",
        "| Variant | Score | Prompt chars | Evidence rows | Low-value rows | Source coverage | Clutter hits | Notes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in _list(summary.get("variant_results")):
        aggregate = _dict(row.get("aggregate_score"))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("variant_id")),
                    str(aggregate.get("mean_score")),
                    str(aggregate.get("mean_prompt_chars")),
                    str(aggregate.get("mean_evidence_count")),
                    str(aggregate.get("mean_low_value_evidence_count")),
                    str(aggregate.get("mean_source_coverage")),
                    str(aggregate.get("total_clutter_hits")),
                    _md_cell("; ".join(_string_list(row.get("notes"))) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The experiment scores instruction variants as a writing-handoff proxy, not as final memo quality. A strong variant should be compact, preserve source/evidence obligations, avoid internal pipeline clutter, and give each section a thesis plus a distinct reader job.",
            "",
            "Use a live backend to test whether the instructions reliably produce valid editorial brief JSON. Use prompt mode to inspect prompt size and deterministic target briefs without model cost.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_editorial_brief_memo_generation(
    memo_ready_packet: dict[str, Any],
    *,
    output_dir: str | Path,
    variant_ids: list[str] | None = None,
    backend: str = "prompt",
    backend_timeout: int | None = 180,
    backend_retries: int = 0,
) -> dict[str, Any]:
    section_plan = build_memo_ready_section_synthesis_plan(memo_ready_packet)
    sections = _list(section_plan.get("sections"))
    if section_plan.get("status") != "ready" or not sections:
        raise ValueError("memo_ready_packet did not produce section synthesis packets")
    variants = _selected_variants(variant_ids)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for variant in variants:
        briefs = [
            deterministic_editorial_brief(_dict(section.get("packet")), variant)
            for section in sections
        ]
        prompt = build_editorial_brief_memo_prompt(
            memo_ready_packet,
            section_plan=section_plan,
            variant=variant,
            editorial_briefs=briefs,
        )
        variant_dir = out / variant.variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        write_json(variant_dir / "editorial_briefs.json", {"variant_id": variant.variant_id, "briefs": briefs})
        write_markdown(variant_dir / "memo_prompt.txt", prompt)
        if backend.strip() == "prompt":
            memo = prompt
            raw = ""
            status = "prompt_only"
        else:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                json_mode=False,
                num_predict=4096,
            )
            raw = result.text
            memo = _extract_markdown_memo(raw)
            status = "accepted" if memo else "empty_output"
        write_markdown(variant_dir / "MEMO.md", memo)
        if raw:
            write_markdown(variant_dir / "raw.txt", raw)
        score = score_generated_memo(memo, editorial_briefs=briefs, question=str(memo_ready_packet.get("decision_question") or ""))
        rows.append(
            {
                "variant_id": variant.variant_id,
                "label": variant.label,
                "status": status,
                "memo_path": f"{variant.variant_id}/MEMO.md",
                "prompt_path": f"{variant.variant_id}/memo_prompt.txt",
                "score": score,
            }
        )
    summary = {
        "schema_id": "editorial_brief_memo_generation_comparison_v1",
        "backend": backend,
        "decision_question": memo_ready_packet.get("decision_question"),
        "variant_count": len(rows),
        "results": rows,
        "best_by_proxy": max(rows, key=lambda row: int(_dict(row.get("score")).get("score", 0))).get("variant_id") if rows else "",
    }
    write_json(out / "editorial_brief_memo_generation_comparison.json", summary)
    write_markdown(out / "EDITORIAL_BRIEF_MEMO_GENERATION_COMPARISON.md", render_editorial_brief_memo_generation_markdown(summary))
    return summary


def build_editorial_brief_memo_prompt(
    memo_ready_packet: dict[str, Any],
    *,
    section_plan: dict[str, Any],
    variant: EditorialInstructionVariant,
    editorial_briefs: list[dict[str, Any]],
) -> str:
    packet = {
        "decision_question": memo_ready_packet.get("decision_question"),
        "bottom_line": section_plan.get("bottom_line"),
        "variant_id": variant.variant_id,
        "editorial_briefs": editorial_briefs,
    }
    return (
        "You are a senior decision analyst writing the final memo from section-level editorial briefs.\n"
        "Use the editorial briefs as the only semantic writing handoff. Write crisp prose for a human decision-maker.\n"
        "Make each section perform its listed reader job and land its section thesis. Convert evidence prose jobs into natural reasoning rather than an inventory.\n"
        "Use bracketed source IDs near the claims they support. Keep source IDs exactly as provided. Preserve named quantities and endpoint distinctions.\n"
        "When evidence rows are in tension, explain the tension in decision terms. When a brief lists topics for other sections, keep those topics concise in this section.\n\n"
        "Required markdown structure:\n"
        "# Decision Memo: <short title>\n"
        "**Decision Question:** <question>\n"
        "**Bottom Line:** <direct answer with scope and confidence>\n"
        "## How to Weight the Evidence\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change or Bound the Answer\n"
        "## Practical Implication\n\n"
        "Editorial brief packet:\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def score_generated_memo(memo: str, *, editorial_briefs: list[dict[str, Any]], question: str) -> dict[str, Any]:
    text = str(memo or "")
    lower = text.lower()
    evidence_ids = _dedupe(
        str(row.get("evidence_id") or "")
        for brief in editorial_briefs
        for row in _list(brief.get("evidence_to_use"))
        if isinstance(row, dict) and row.get("evidence_id")
    )
    source_ids = _dedupe(
        source_id
        for brief in editorial_briefs
        for row in _list(brief.get("evidence_to_use"))
        if isinstance(row, dict)
        for source_id in _string_list(row.get("source_ids"))
    )
    evidence_mentions = sum(1 for evidence_id in evidence_ids if evidence_id and evidence_id in text)
    source_mentions = sum(1 for source_id in source_ids if source_id and source_id in text)
    low_value_phrases = sum(1 for phrase in ("appendix-only", "low atomicity", "table descriptor", "no (%)") if phrase in lower)
    headings = [
        "## How to Weight the Evidence",
        "## Why This Is the Best Current Read",
        "## What Could Change or Bound the Answer",
        "## Practical Implication",
    ]
    heading_hits = sum(1 for heading in headings if heading in text)
    word_count = len(re.findall(r"\b\w+\b", text))
    repeated_sentence_count = _repeated_sentence_count(text)
    question_terms = set(_content_terms(question))
    answer_focus = len(question_terms & set(_content_terms(text))) / max(1, len(question_terms))
    score = 50
    score += heading_hits * 5
    score += min(15, source_mentions * 2)
    score += min(10, evidence_mentions)
    score += round(answer_focus * 10)
    if 550 <= word_count <= 1300:
        score += 10
    elif word_count < 350:
        score -= 10
    elif word_count > 1800:
        score -= 8
    score -= low_value_phrases * 8
    score -= repeated_sentence_count * 3
    return {
        "schema_id": "generated_memo_proxy_score_v1",
        "score": max(0, min(100, int(score))),
        "word_count": word_count,
        "heading_hits": heading_hits,
        "source_mentions": source_mentions,
        "source_count": len(source_ids),
        "evidence_mentions": evidence_mentions,
        "evidence_count": len(evidence_ids),
        "low_value_phrase_count": low_value_phrases,
        "repeated_sentence_count": repeated_sentence_count,
        "question_term_coverage": round(answer_focus, 3),
    }


def render_editorial_brief_memo_generation_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Editorial Brief Memo Generation Comparison",
        "",
        f"Backend: `{summary.get('backend')}`",
        f"Best by proxy: `{summary.get('best_by_proxy')}`",
        "",
        "| Variant | Score | Words | Headings | Sources | Evidence IDs | Low-value phrases | Memo |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in _list(summary.get("results")):
        score = _dict(row.get("score"))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("variant_id")),
                    str(score.get("score")),
                    str(score.get("word_count")),
                    str(score.get("heading_hits")),
                    f"{score.get('source_mentions')}/{score.get('source_count')}",
                    f"{score.get('evidence_mentions')}/{score.get('evidence_count')}",
                    str(score.get("low_value_phrase_count")),
                    str(row.get("memo_path")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def run_source_weighted_narrative_outline_experiment(
    memo_ready_packet: dict[str, Any],
    *,
    output_dir: str | Path,
    backend: str,
    backend_timeout: int | None = 240,
    backend_retries: int = 0,
    variant_id: str = "source_weighted",
) -> dict[str, Any]:
    section_plan = build_memo_ready_section_synthesis_plan(memo_ready_packet)
    sections = _list(section_plan.get("sections"))
    if section_plan.get("status") != "ready" or not sections:
        raise ValueError("memo_ready_packet did not produce section synthesis packets")
    variant = _selected_variants([variant_id])[0]
    editorial_briefs = [deterministic_editorial_brief(_dict(section.get("packet")), variant) for section in sections]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    outline_prompt = build_source_weighted_narrative_outline_prompt(
        memo_ready_packet,
        section_plan=section_plan,
        editorial_briefs=editorial_briefs,
    )
    write_markdown(out / "outline_prompt.txt", outline_prompt)
    if backend.strip() == "prompt":
        raw_outline = ""
        outline = deterministic_source_weighted_narrative_outline(memo_ready_packet, editorial_briefs=editorial_briefs)
        outline_status = "prompt_mode_target"
    else:
        result = run_model_backend(
            outline_prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            json_mode=True,
            num_predict=2048,
        )
        raw_outline = result.text
        outline = _parse_source_weighted_outline(raw_outline)
        outline_status = "accepted" if outline else "parse_failed"
        if not outline:
            outline = deterministic_source_weighted_narrative_outline(memo_ready_packet, editorial_briefs=editorial_briefs)
    write_json(out / "source_weighted_narrative_outline.json", outline)
    if raw_outline:
        write_markdown(out / "outline_raw.txt", raw_outline)
    memo_prompt = build_outline_guided_memo_prompt(
        memo_ready_packet,
        section_plan=section_plan,
        editorial_briefs=editorial_briefs,
        outline=outline,
    )
    write_markdown(out / "outline_guided_memo_prompt.txt", memo_prompt)
    if backend.strip() == "prompt":
        memo = memo_prompt
        raw_memo = ""
        memo_status = "prompt_only"
    else:
        result = run_model_backend(
            memo_prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            json_mode=False,
            num_predict=4096,
        )
        raw_memo = result.text
        memo = _extract_markdown_memo(raw_memo)
        memo_status = "accepted" if memo else "empty_output"
    write_markdown(out / "OUTLINE_GUIDED_MEMO.md", memo)
    if raw_memo:
        write_markdown(out / "memo_raw.txt", raw_memo)
    score = score_generated_memo(memo, editorial_briefs=editorial_briefs, question=str(memo_ready_packet.get("decision_question") or ""))
    summary = {
        "schema_id": "source_weighted_narrative_outline_experiment_v1",
        "backend": backend,
        "variant_id": variant.variant_id,
        "decision_question": memo_ready_packet.get("decision_question"),
        "outline_status": outline_status,
        "memo_status": memo_status,
        "outline_path": "source_weighted_narrative_outline.json",
        "memo_path": "OUTLINE_GUIDED_MEMO.md",
        "score": score,
    }
    write_json(out / "source_weighted_narrative_outline_experiment.json", summary)
    write_markdown(out / "SOURCE_WEIGHTED_NARRATIVE_OUTLINE_EXPERIMENT.md", render_source_weighted_outline_experiment_markdown(summary))
    return summary


def run_source_weighted_pipeline_fit_experiment(
    memo_ready_packet: dict[str, Any],
    *,
    output_dir: str | Path,
    backend: str,
    backend_timeout: int | None = 240,
    backend_retries: int = 0,
    variant_id: str = "source_weighted",
    compare_baseline: bool = False,
    outline_owned_contracts: bool = False,
    protect_critical_evidence: bool = True,
    opinionated_section_plan: bool = False,
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
        build_decision_usefulness_retention_report,
        build_memo_ready_packet_retention_report,
        run_memo_ready_packet_synthesis,
    )
    from epistemic_case_mapper.map_briefing_memo_ready_presentation import run_memo_ready_presentation_normalization
    from epistemic_case_mapper.map_briefing_memo_ready_section_synthesis import run_parallel_memo_ready_section_generation
    from epistemic_case_mapper.map_briefing_source_weighting_contract import build_source_weighting_fidelity_report

    section_plan = build_memo_ready_section_synthesis_plan(memo_ready_packet)
    sections = _list(section_plan.get("sections"))
    if section_plan.get("status") != "ready" or not sections:
        raise ValueError("memo_ready_packet did not produce section synthesis packets")
    variant = _selected_variants([variant_id])[0]
    editorial_briefs = [deterministic_editorial_brief(_dict(section.get("packet")), variant) for section in sections]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    outline_prompt = build_source_weighted_narrative_outline_prompt(
        memo_ready_packet,
        section_plan=section_plan,
        editorial_briefs=editorial_briefs,
    )
    write_markdown(out / "outline_prompt.txt", outline_prompt)
    if backend.strip() == "prompt":
        raw_outline = ""
        outline = deterministic_source_weighted_narrative_outline(memo_ready_packet, editorial_briefs=editorial_briefs)
        outline_status = "prompt_mode_target"
    else:
        result = run_model_backend(
            outline_prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            json_mode=True,
            num_predict=2048,
        )
        raw_outline = result.text
        outline = _parse_source_weighted_outline(raw_outline)
        outline_status = "accepted" if outline else "parse_failed"
        if not outline:
            outline = deterministic_source_weighted_narrative_outline(memo_ready_packet, editorial_briefs=editorial_briefs)
    active_evidence_ids = (
        build_outline_active_evidence_ids(
            memo_ready_packet,
            outline,
            protect_critical_evidence=protect_critical_evidence,
        )
        if outline_owned_contracts
        else None
    )
    active_packet = (
        build_outline_owned_memo_ready_packet(memo_ready_packet, outline, active_evidence_ids=active_evidence_ids)
        if outline_owned_contracts
        else memo_ready_packet
    )
    integration_report = build_outline_contract_integration_report(
        memo_ready_packet,
        active_packet,
        outline,
        active_evidence_ids=active_evidence_ids,
    )
    integrated_plan = build_source_weighted_outline_integrated_section_plan(
        section_plan,
        outline,
        owned_evidence_ids=active_evidence_ids if outline_owned_contracts else None,
    )
    opinionated_report = {}
    if opinionated_section_plan:
        integrated_plan, opinionated_report = build_opinionated_section_plan(integrated_plan)
    write_json(out / "source_weighted_narrative_outline.json", outline)
    write_json(out / "outline_contract_integration_report.json", integration_report)
    write_json(out / "integrated_section_plan.json", integrated_plan)
    if opinionated_report:
        write_json(out / "opinionated_section_plan_report.json", opinionated_report)
    if raw_outline:
        write_markdown(out / "outline_raw.txt", raw_outline)
    generated = run_parallel_memo_ready_section_generation(
        integrated_plan,
        memo_ready_packet=active_packet,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        whole_prompt=build_outline_integrated_reference_prompt(memo_ready_packet, outline=outline),
    )
    memo = str(generated.get("memo") or "")
    presentation = run_memo_ready_presentation_normalization(memo, active_packet) if memo else {"memo": memo, "report": {}}
    memo = str(presentation.get("memo") or memo)
    write_markdown(out / "OUTLINE_INTEGRATED_PRODUCTION_MEMO.md", memo)
    write_markdown(out / "outline_integrated_production_prompt_manifest.txt", str(generated.get("prompt") or ""))
    if generated.get("raw"):
        write_markdown(out / "outline_integrated_production_raw.txt", str(generated.get("raw") or ""))
    retention = build_memo_ready_packet_retention_report(memo, active_packet)
    decision_usefulness = build_decision_usefulness_retention_report(memo, active_packet)
    source_weighting = build_source_weighting_fidelity_report(memo, active_packet)
    baseline = {}
    if compare_baseline and backend.strip() != "prompt":
        baseline_result = run_memo_ready_packet_synthesis(
            memo_ready_packet,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
        )
        baseline_memo = str(baseline_result.get("memo") or "")
        write_markdown(out / "BASELINE_PRODUCTION_MEMO.md", baseline_memo)
        baseline = {
            "memo_path": "BASELINE_PRODUCTION_MEMO.md",
            "report": baseline_result.get("report", {}),
            "retention_report": build_memo_ready_packet_retention_report(baseline_memo, memo_ready_packet),
            "decision_usefulness_retention_report": build_decision_usefulness_retention_report(baseline_memo, memo_ready_packet),
            "source_weighting_fidelity_report": build_source_weighting_fidelity_report(baseline_memo, memo_ready_packet),
            "score": score_generated_memo(baseline_memo, editorial_briefs=editorial_briefs, question=str(memo_ready_packet.get("decision_question") or "")),
        }
    summary = {
        "schema_id": "source_weighted_pipeline_fit_experiment_v1",
        "backend": backend,
        "variant_id": variant.variant_id,
        "decision_question": memo_ready_packet.get("decision_question"),
        "outline_status": outline_status,
        "outline_owned_contracts": outline_owned_contracts,
        "protect_critical_evidence": protect_critical_evidence,
        "opinionated_section_plan": opinionated_section_plan,
        "opinionated_section_plan_report": opinionated_report,
        "outline_contract_integration_report": integration_report,
        "section_generation_report": generated.get("report", {}),
        "presentation_normalization_report": presentation.get("report", {}),
        "memo_path": "OUTLINE_INTEGRATED_PRODUCTION_MEMO.md",
        "outline_path": "source_weighted_narrative_outline.json",
        "integrated_section_plan_path": "integrated_section_plan.json",
        "score": score_generated_memo(memo, editorial_briefs=editorial_briefs, question=str(memo_ready_packet.get("decision_question") or "")),
        "retention_report": retention,
        "decision_usefulness_retention_report": decision_usefulness,
        "source_weighting_fidelity_report": source_weighting,
        "baseline": baseline,
    }
    write_json(out / "source_weighted_pipeline_fit_experiment.json", summary)
    write_markdown(out / "SOURCE_WEIGHTED_PIPELINE_FIT_EXPERIMENT.md", render_source_weighted_pipeline_fit_experiment_markdown(summary))
    return summary


def build_opinionated_section_plan(section_plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = deepcopy(section_plan if isinstance(section_plan, dict) else {})
    sections = []
    changed = []
    for section in _list(plan.get("sections")):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id") or _dict(section.get("packet")).get("section_id") or "").strip()
        heading = str(section.get("heading") or _dict(section.get("packet")).get("heading") or "").strip()
        contract = _opinionated_section_contract(section_id, heading)
        if not contract:
            sections.append(section)
            continue
        updated = dict(section)
        packet = dict(_dict(section.get("packet")))
        focus = dict(_dict(packet.get("section_focus")))
        role = dict(_dict(packet.get("section_role_contract")))
        focus["reader_question"] = str(focus.get("reader_question") or contract.get("reader_question") or "").strip()
        focus["paragraph_shape"] = _dedupe([*_string_list(contract.get("paragraph_shape")), *_string_list(focus.get("paragraph_shape"))])[:8]
        role["do"] = _dedupe([*_string_list(contract.get("do")), *_string_list(role.get("do"))])[:10]
        role["avoid"] = _dedupe([*_string_list(contract.get("avoid")), *_string_list(role.get("avoid"))])[:10]
        packet["section_focus"] = focus
        packet["section_role_contract"] = role
        packet["opinionated_prose_plan"] = contract
        updated["packet"] = packet
        sections.append(updated)
        changed.append({"section_id": section_id, "heading": heading, "added_move_count": len(_string_list(contract.get("paragraph_shape")))})
    plan["sections"] = sections
    report = {
        "schema_id": "opinionated_section_plan_report_v1",
        "status": "changed" if changed else "no_changes",
        "changed_section_count": len(changed),
        "changed_sections": changed,
        "principle": (
            "Make each section own a distinct reader-facing reasoning job before model writing, "
            "while leaving evidence selection and validation to the existing source-grounded contracts."
        ),
    }
    return plan, report


def _opinionated_section_contract(section_id: str, heading: str) -> dict[str, Any]:
    section_id = str(section_id or "").strip()
    heading = str(heading or "").strip()
    contracts = {
        "source_weighting": {
            "reader_question": "Which sources should carry the answer, and which only bound or contextualize it?",
            "do": [
                "Open by naming the evidence class that carries the answer.",
                "Separate driver, boundary, calibrator, and context sources by what each can decide.",
                "Explain why a boundary source narrows the answer rather than replacing the direct answer evidence.",
            ],
            "avoid": [
                "Avoid restating every later section; focus on source roles and evidential weight.",
                "Avoid source inventory prose unless each source role is interpreted.",
            ],
            "paragraph_shape": [
                "Driver frame: name the source class that carries the current read.",
                "Boundary frame: explain which evidence narrows scope, dose, confidence, or population.",
                "Context frame: identify sources that help interpretation but should not carry the answer.",
                "Close with the source-weighting rule the rest of the memo follows.",
            ],
        },
        "answer_evidence": {
            "reader_question": "Why does the current read follow from the most direct answer evidence?",
            "do": [
                "State the positive case for the current read in one clear analytic move.",
                "Explain convergence across the direct answer evidence rather than listing caveats.",
                "End by handing off boundaries to the next section instead of developing them here.",
            ],
            "avoid": [
                "Avoid introducing boundary-only quantities or subgroup exceptions as answer support.",
                "Avoid repeating the practical recommendation before proving the current read.",
            ],
            "paragraph_shape": [
                "Lead with the direct answer evidence and its supported scope.",
                "Explain why the answer evidence converges on the current read.",
                "Name the boundary category briefly as a handoff, without developing boundary evidence.",
            ],
        },
        "counterweights": {
            "reader_question": "What would narrow, weaken, or change the current read?",
            "do": [
                "Group limiting evidence by decision function: threshold, subgroup, measurement, or uncertainty.",
                "For each limit, state whether it overturns, narrows, or calibrates the answer.",
                "Make the update condition explicit when the evidence implies one.",
            ],
            "avoid": [
                "Avoid repeating the answer evidence except as a reference point for what the limit modifies.",
                "Avoid treating all caveats as equally important.",
            ],
            "paragraph_shape": [
                "Start with the strongest boundary and say what it does to the answer.",
                "Separate dose or threshold limits from subgroup or scope limits.",
                "Explain measurement, confounding, or uncertainty limits as calibration rather than decision reversal.",
                "Close with the practical update condition.",
            ],
        },
        "practical_implication": {
            "reader_question": "What should a decision-maker do with this read?",
            "do": [
                "Translate the answer into a concrete default action or communication stance.",
                "State the exception or monitoring rule separately from the default.",
                "Tie implementation advice back to the evidence roles rather than repeating study findings.",
            ],
            "avoid": [
                "Avoid re-proving the evidence hierarchy.",
                "Avoid generic advice that could apply to any decision question.",
            ],
            "paragraph_shape": [
                "Default action: state what the reader should do under the supported scope.",
                "Exception handling: state when advice should narrow, monitor, or change.",
                "Communication rule: give the phrasing or operational implication that follows from the evidence.",
            ],
        },
    }
    if section_id in contracts:
        return {"section_id": section_id, "heading": heading, **contracts[section_id]}
    return {}


def build_source_weighted_outline_integrated_section_plan(
    section_plan: dict[str, Any],
    outline: dict[str, Any],
    *,
    owned_evidence_ids: set[str] | None = None,
) -> dict[str, Any]:
    plan = dict(section_plan)
    plan["source_weighted_narrative_outline"] = outline
    if bottom_line := _outline_bottom_line(outline):
        plan["bottom_line"] = bottom_line
    known_source_ids = _string_list(section_plan.get("known_source_ids"))
    plan["sections"] = [
        _section_with_source_weighted_outline(
            section,
            outline,
            known_source_ids=known_source_ids,
            owned_evidence_ids=owned_evidence_ids,
        )
        for section in _list(section_plan.get("sections"))
        if isinstance(section, dict)
    ]
    return plan


def build_outline_active_evidence_ids(
    memo_ready_packet: dict[str, Any],
    outline: dict[str, Any],
    *,
    protect_critical_evidence: bool = True,
) -> set[str]:
    owned_ids = set(_outline_owned_evidence_ids(outline))
    if protect_critical_evidence:
        owned_ids.update(_protected_critical_evidence_ids(memo_ready_packet))
    return owned_ids


def build_outline_owned_memo_ready_packet(
    memo_ready_packet: dict[str, Any],
    outline: dict[str, Any],
    *,
    active_evidence_ids: set[str] | None = None,
) -> dict[str, Any]:
    owned_ids = set(active_evidence_ids or _outline_owned_evidence_ids(outline))
    packet = deepcopy(memo_ready_packet if isinstance(memo_ready_packet, dict) else {})
    owned_source_ids = _owned_source_ids(packet, owned_ids)
    packet["evidence_items"] = [
        item
        for item in _list(packet.get("evidence_items"))
        if isinstance(item, dict) and str(item.get("item_id") or "").strip() in owned_ids
    ]
    packet = _dict(_project_owned_evidence_references(packet, owned_ids))
    for key in OUTLINE_REBUILT_PACKET_KEYS:
        packet.pop(key, None)
    packet = _with_outline_answer_state(packet, outline)
    packet["outline_contract_active_evidence_ids"] = sorted(owned_ids)
    packet["outline_contract_active_source_ids"] = sorted(owned_source_ids)
    return packet


def _with_outline_answer_state(packet: dict[str, Any], outline: dict[str, Any]) -> dict[str, Any]:
    updated = dict(packet)
    bottom_line = _outline_bottom_line(outline)
    answer_order = _string_list(_dict(outline).get("answer_order"))
    thesis = _short_text(str(_dict(outline).get("source_weighting_thesis") or ""), 900)
    primary = _short_text(answer_order[0], 520) if answer_order else bottom_line
    secondary = _short_text(answer_order[1], 420) if len(answer_order) > 1 else ""
    updated["answer_spine"] = _drop_empty(
        {
            "confidence": _dict(updated.get("answer_spine")).get("confidence") or "not_specified",
            "default_read": bottom_line or primary,
            "primary_answer": primary,
            "secondary_detail": secondary,
            "secondary_detail_type": "boundary_or_scope" if secondary else "",
            "full_direct_answer": bottom_line,
            "why_this_read": thesis,
            "synthesis_strategy": "Write from the source-weighted narrative outline and active evidence.",
        }
    )
    updated["analyst_decision_logic"] = _drop_empty(
        {
            "bounded_bottom_line": bottom_line or primary,
            "support_summary": _outline_main_point(outline, section_id="answer_evidence") or primary,
            "strongest_counterweight": _outline_main_point(outline, section_id="counterweights") or secondary,
            "counterweight_weighting": _outline_main_point(outline, section_id="counterweights") or secondary,
            "scope_boundaries": [secondary] if secondary else [],
            "practical_implications": [
                value
                for value in (
                    _outline_main_point(outline, section_id="practical_implication"),
                    _outline_section_guidance(outline, "practical_implication").get("section_thesis"),
                )
                if value
            ],
            "do_not_overstate": _string_list(_dict(outline).get("what_to_omit")),
        }
    )
    updated["analyst_source_weight_judgments"] = []
    updated["analyst_source_hierarchy"] = {}
    updated["analyst_source_hierarchy_report"] = {}
    return updated


def _outline_main_point(outline: dict[str, Any], *, section_id: str) -> str:
    guidance = _outline_section_guidance(outline, section_id)
    for key in ("section_thesis", "start_with"):
        text = str(guidance.get(key) or "").strip()
        if text:
            return _short_text(text, 520)
    for row in _list(_dict(outline).get("narrative_arc")):
        if not isinstance(row, dict):
            continue
        role = str(row.get("paragraph_role") or "").lower()
        point = str(row.get("main_point") or "").strip()
        if point and section_id.replace("_", " ") in role:
            return _short_text(point, 520)
    return ""


def build_outline_contract_integration_report(
    original_packet: dict[str, Any],
    active_packet: dict[str, Any],
    outline: dict[str, Any],
    *,
    active_evidence_ids: set[str] | None = None,
) -> dict[str, Any]:
    owned_ids = _outline_owned_evidence_ids(outline)
    active_ids = set(active_evidence_ids or owned_ids)
    protected_ids = _protected_critical_evidence_ids(original_packet)
    original_items = {str(item.get("item_id") or ""): item for item in _list(original_packet.get("evidence_items")) if isinstance(item, dict)}
    active_items = {str(item.get("item_id") or ""): item for item in _list(active_packet.get("evidence_items")) if isinstance(item, dict)}
    demoted = [
        evidence_id
        for evidence_id, original in original_items.items()
        if evidence_id not in owned_ids
        and (
            bool(original.get("must_use"))
            or str(original.get("obligation_level") or "") in {"must_include", "should_include"}
        )
        and not bool(active_items.get(evidence_id, {}).get("must_use"))
    ]
    low_value_demoted = [evidence_id for evidence_id in demoted if _looks_low_value_item(original_items.get(evidence_id, {}))]
    critical_demoted = sorted(protected_ids & set(demoted))
    active_source_refs = _source_refs_for_items(original_items, active_ids)
    original_significant_source_refs = _source_refs_for_items(
        original_items,
        {
            evidence_id
            for evidence_id, item in original_items.items()
            if _is_significant_reader_facing_item(item)
        },
    )
    warnings = []
    if critical_demoted:
        warnings.append("protected_critical_evidence_demoted")
    if len(active_source_refs) < min(3, len(original_significant_source_refs)):
        warnings.append("active_source_coverage_low")
    if not owned_ids:
        warnings.append("outline_selected_no_evidence")
    protected_policy = (
        "Outline-owned evidence and analyst-critical evidence are required; other rows remain optional context."
        if protected_ids and protected_ids.issubset(active_ids)
        else "Outline-owned evidence is required; analyst-critical evidence omitted by the outline is surfaced as QA rather than silently preserved."
    )
    return {
        "schema_id": "outline_contract_integration_report_v1",
        "status": "ready" if not warnings else "warning",
        "warnings": warnings,
        "outline_owned_evidence_count": len(owned_ids),
        "owned_evidence_ids": sorted(owned_ids),
        "active_evidence_count": len(active_ids),
        "active_evidence_ids": sorted(active_ids),
        "protected_critical_evidence_count": len(protected_ids),
        "protected_critical_evidence_ids": sorted(protected_ids),
        "demoted_required_count": len(demoted),
        "demoted_required_evidence_ids": sorted(demoted),
        "low_value_demoted_count": len(low_value_demoted),
        "low_value_demoted_evidence_ids": sorted(low_value_demoted),
        "critical_demoted_count": len(critical_demoted),
        "critical_demoted_evidence_ids": critical_demoted,
        "active_source_refs": active_source_refs,
        "source_refs_without_active_evidence": sorted(set(original_significant_source_refs) - set(active_source_refs)),
        "policy": protected_policy,
    }


def build_outline_integrated_reference_prompt(memo_ready_packet: dict[str, Any], *, outline: dict[str, Any]) -> str:
    packet = {
        "decision_question": memo_ready_packet.get("decision_question"),
        "source_weighted_narrative_outline": outline,
    }
    return (
        "Production section synthesis reference packet.\n"
        "The source-weighted narrative outline is the governing answer frame for section synthesis and deterministic assembly.\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def build_source_weighted_narrative_outline_prompt(
    memo_ready_packet: dict[str, Any],
    *,
    section_plan: dict[str, Any],
    editorial_briefs: list[dict[str, Any]],
) -> str:
    schema = {
        "schema_id": "source_weighted_narrative_outline_v1",
        "answer_order": [
            "first sentence of answer",
            "second sentence that names the main boundary",
        ],
        "source_weighting_thesis": "one paragraph explaining which evidence should drive, bound, calibrate, or contextualize the answer",
        "narrative_arc": [
            {
                "paragraph_role": "what this paragraph accomplishes",
                "main_point": "the point the paragraph should land",
                "source_ids": ["source IDs to cite"],
                "evidence_ids": ["evidence IDs to use if available"],
            }
        ],
        "section_guidance": [
            {
                "section_id": "section ID",
                "section_thesis": "the exact thesis this section should land",
                "start_with": "what the section should open with",
                "omit_or_defer": ["points to omit or leave to other sections"],
            }
        ],
        "what_to_omit": ["evidence or phrasing that would make the memo worse"],
    }
    packet = {
        "task": (
            "Create a source-weighted narrative outline before memo writing. "
            "The goal is sharper answer order and analyst judgment, not more detail."
        ),
        "rules": [
            "Return strict JSON matching the schema.",
            "Put the direct answer before caveats unless the evidence cannot support a direct answer.",
            "Use source weighting to decide answer order, not just section order.",
            "Identify low-value context to omit from prose.",
            "Keep the outline generalizable across decision questions by using evidence roles and source weight rather than domain-specific templates.",
        ],
        "return_schema": schema,
        "context": {
            "decision_question": memo_ready_packet.get("decision_question"),
            "bottom_line_candidate": section_plan.get("bottom_line"),
            "editorial_briefs": editorial_briefs,
        },
    }
    return json.dumps(packet, indent=2, ensure_ascii=False)


def deterministic_source_weighted_narrative_outline(
    memo_ready_packet: dict[str, Any],
    *,
    editorial_briefs: list[dict[str, Any]],
) -> dict[str, Any]:
    source_rows = _source_weighted_outline_sources(editorial_briefs)
    return {
        "schema_id": "source_weighted_narrative_outline_v1",
        "answer_order": [
            str(memo_ready_packet.get("decision_question") or "Answer the decision question directly."),
            "Then state the strongest boundary or counterweight that limits the answer.",
        ],
        "source_weighting_thesis": _source_weighting_outline_thesis(source_rows),
        "narrative_arc": [
            {
                "paragraph_role": "answer first",
                "main_point": _short_text(str(_list(editorial_briefs)[0].get("section_thesis") if editorial_briefs else ""), 240),
                "source_ids": source_rows[:3],
                "evidence_ids": _outline_evidence_ids(editorial_briefs)[:5],
            },
            {
                "paragraph_role": "explain the evidence hierarchy",
                "main_point": "Explain which sources drive the answer and which sources bound or contextualize it.",
                "source_ids": source_rows,
                "evidence_ids": _outline_evidence_ids(editorial_briefs)[5:10],
            },
        ],
        "section_guidance": [
            {
                "section_id": brief.get("section_id"),
                "section_thesis": brief.get("section_thesis"),
                "start_with": brief.get("must_land_distinction") or brief.get("section_thesis"),
                "omit_or_defer": _string_list(brief.get("leave_to_other_sections")),
            }
            for brief in editorial_briefs
        ],
        "what_to_omit": [
            "source-context residue that does not help answer the decision question",
            "table descriptors or extraction notes",
            "generic caution language without a concrete decision implication",
        ],
    }


def build_outline_guided_memo_prompt(
    memo_ready_packet: dict[str, Any],
    *,
    section_plan: dict[str, Any],
    editorial_briefs: list[dict[str, Any]],
    outline: dict[str, Any],
) -> str:
    packet = {
        "decision_question": memo_ready_packet.get("decision_question"),
        "source_weighted_narrative_outline": outline,
        "editorial_briefs": editorial_briefs,
    }
    return (
        "You are a senior decision analyst writing the final memo.\n"
        "Use the source-weighted narrative outline as the governing answer frame, answer order, and paragraph flow. "
        "Use the editorial briefs for section-local evidence and citations. Write crisp prose for a human decision-maker.\n"
        "Build the bottom line from the outline answer_order and source_weighting_thesis. Explain why sources carry different weight. "
        "Convert evidence rows into reasoning, not inventory. Omit items listed in what_to_omit unless needed for source traceability.\n"
        "Use bracketed source IDs near the claims they support. Keep source IDs exactly as provided. Preserve quantities and endpoint distinctions.\n\n"
        "Required markdown structure:\n"
        "# Decision Memo: <short title>\n"
        "**Decision Question:** <question>\n"
        "**Bottom Line:** <direct answer with scope and confidence>\n"
        "## How to Weight the Evidence\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change or Bound the Answer\n"
        "## Practical Implication\n\n"
        "Outline-guided writing packet:\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def render_source_weighted_outline_experiment_markdown(summary: dict[str, Any]) -> str:
    score = _dict(summary.get("score"))
    return "\n".join(
        [
            "# Source-Weighted Narrative Outline Experiment",
            "",
            f"Backend: `{summary.get('backend')}`",
            f"Outline status: `{summary.get('outline_status')}`",
            f"Memo status: `{summary.get('memo_status')}`",
            "",
            f"- Memo score: `{score.get('score')}`",
            f"- Word count: `{score.get('word_count')}`",
            f"- Source mentions: `{score.get('source_mentions')}/{score.get('source_count')}`",
            f"- Low-value phrases: `{score.get('low_value_phrase_count')}`",
            "",
            f"Memo: `{summary.get('memo_path')}`",
            f"Outline: `{summary.get('outline_path')}`",
        ]
    ) + "\n"


def render_source_weighted_pipeline_fit_experiment_markdown(summary: dict[str, Any]) -> str:
    score = _dict(summary.get("score"))
    retention = _dict(summary.get("retention_report"))
    usefulness = _dict(summary.get("decision_usefulness_retention_report"))
    source_weighting = _dict(summary.get("source_weighting_fidelity_report"))
    generation = _dict(summary.get("section_generation_report"))
    integration = _dict(summary.get("outline_contract_integration_report"))
    lines = [
        "# Source-Weighted Pipeline Fit Experiment",
        "",
        f"Backend: `{summary.get('backend')}`",
        f"Outline status: `{summary.get('outline_status')}`",
        f"Section generation status: `{generation.get('status')}`",
        "",
        "## Outline-Integrated Production Path",
        "",
        f"- Memo score: `{score.get('score')}`",
        f"- Word count: `{score.get('word_count')}`",
        f"- Source mentions: `{score.get('source_mentions')}/{score.get('source_count')}`",
        f"- Retention status: `{retention.get('status')}`",
        f"- Missing mandatory count: `{retention.get('missing_mandatory_count')}`",
        f"- Decision-usefulness status: `{usefulness.get('status')}`",
        f"- Source-weighting fidelity status: `{source_weighting.get('status')}`",
        f"- Outline contract QA: `{integration.get('status')}`",
        f"- Opinionated sections: `{summary.get('opinionated_section_plan')}`",
        f"- Active evidence: `{integration.get('active_evidence_count')}`",
        f"- Demoted required evidence: `{integration.get('demoted_required_count')}`",
        f"- Critical demoted evidence: `{integration.get('critical_demoted_count')}`",
        f"- QA warnings: `{', '.join(_string_list(integration.get('warnings'))) or '-'}`",
        "",
        f"Memo: `{summary.get('memo_path')}`",
        f"Outline: `{summary.get('outline_path')}`",
    ]
    baseline = _dict(summary.get("baseline"))
    if baseline:
        baseline_score = _dict(baseline.get("score"))
        baseline_retention = _dict(baseline.get("retention_report"))
        lines.extend(
            [
                "",
                "## Baseline Production Path",
                "",
                f"- Memo score: `{baseline_score.get('score')}`",
                f"- Word count: `{baseline_score.get('word_count')}`",
                f"- Source mentions: `{baseline_score.get('source_mentions')}/{baseline_score.get('source_count')}`",
                f"- Retention status: `{baseline_retention.get('status')}`",
                f"- Missing mandatory count: `{baseline_retention.get('missing_mandatory_count')}`",
                f"- Memo: `{baseline.get('memo_path')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def _parse_source_weighted_outline(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(canonical_json_output(raw))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    payload["schema_id"] = "source_weighted_narrative_outline_v1"
    payload["answer_order"] = _string_list(payload.get("answer_order"))[:5]
    payload["source_weighting_thesis"] = _short_text(str(payload.get("source_weighting_thesis") or ""), 900)
    payload["narrative_arc"] = _normalize_outline_rows(_list(payload.get("narrative_arc")), row_type="arc")[:8]
    payload["section_guidance"] = _normalize_outline_rows(_list(payload.get("section_guidance")), row_type="section")[:8]
    payload["what_to_omit"] = _string_list(payload.get("what_to_omit"))[:10]
    return payload


def _normalize_outline_rows(rows: list[Any], *, row_type: str) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row_type == "section":
            normalized.append(
                {
                    "section_id": str(row.get("section_id") or "").strip(),
                    "section_thesis": _short_text(str(row.get("section_thesis") or ""), 420),
                    "start_with": _short_text(str(row.get("start_with") or ""), 300),
                    "omit_or_defer": _string_list(row.get("omit_or_defer"))[:6],
                    "evidence_ids": _string_list(row.get("evidence_ids") or row.get("owned_evidence_ids"))[:10],
                }
            )
        else:
            normalized.append(
                {
                    "paragraph_role": _short_text(str(row.get("paragraph_role") or ""), 160),
                    "main_point": _short_text(str(row.get("main_point") or ""), 420),
                    "source_ids": _string_list(row.get("source_ids"))[:8],
                    "evidence_ids": _string_list(row.get("evidence_ids"))[:10],
                }
            )
    return [row for row in normalized if any(value for value in row.values())]


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}


def _source_weighted_outline_sources(editorial_briefs: list[dict[str, Any]]) -> list[str]:
    source_ids: list[str] = []
    for brief in editorial_briefs:
        for row in _list(brief.get("evidence_to_use")):
            if isinstance(row, dict):
                source_ids.extend(_string_list(row.get("source_ids")))
    return _dedupe(source_ids)


def _outline_evidence_ids(editorial_briefs: list[dict[str, Any]]) -> list[str]:
    evidence_ids: list[str] = []
    for brief in editorial_briefs:
        for row in _list(brief.get("evidence_to_use")):
            if isinstance(row, dict) and row.get("evidence_id"):
                evidence_ids.append(str(row.get("evidence_id")))
    return _dedupe(evidence_ids)


def _source_weighting_outline_thesis(source_ids: list[str]) -> str:
    if not source_ids:
        return "Weight sources by directness to the decision question, endpoint relevance, and whether they drive, bound, or contextualize the answer."
    if len(source_ids) == 1:
        return f"Treat {source_ids[0]} as the main cited source, while making the scope and uncertainty of that source explicit."
    driver = ", ".join(source_ids[:3])
    remaining = len(source_ids) - min(3, len(source_ids))
    tail = f"; use the remaining {remaining} source(s) to bound or contextualize the answer" if remaining else ""
    return f"Use {driver} as the first source-weighting frame{tail}. Explain source roles in decision terms rather than listing sources."


def _outline_bottom_line(outline: dict[str, Any]) -> str:
    answer_order = _string_list(_dict(outline).get("answer_order"))
    if not answer_order:
        return ""
    first = answer_order[0].strip()
    second = answer_order[1].strip() if len(answer_order) > 1 else ""
    return _short_text(" ".join(part for part in (first, second) if part), 520)


def _section_with_source_weighted_outline(
    section: dict[str, Any],
    outline: dict[str, Any],
    *,
    known_source_ids: list[str],
    owned_evidence_ids: set[str] | None = None,
) -> dict[str, Any]:
    updated = dict(section)
    packet = dict(_dict(section.get("packet")))
    if owned_evidence_ids is not None:
        packet = _filter_section_packet_to_outline_owned_evidence(packet, owned_evidence_ids)
    section_id = str(packet.get("section_id") or section.get("section_id") or "").strip()
    guidance = _outline_section_guidance(outline, section_id)
    packet["top_context"] = _top_context_with_outline(_dict(packet.get("top_context")), outline)
    packet["section_focus"] = _section_focus_with_outline(_dict(packet.get("section_focus")), outline, guidance)
    packet["section_role_contract"] = _section_role_contract_with_outline(_dict(packet.get("section_role_contract")), guidance)
    updated["packet"] = packet
    updated["prompt"] = build_memo_ready_section_synthesis_prompt(packet, known_source_ids=known_source_ids) if known_source_ids else str(section.get("prompt") or "")
    return updated


def _top_context_with_outline(top: dict[str, Any], outline: dict[str, Any]) -> dict[str, Any]:
    updated = dict(top)
    if bottom := _outline_bottom_line(outline):
        updated["current_read_reference"] = bottom
    if thesis := str(_dict(outline).get("source_weighting_thesis") or "").strip():
        updated["source_hierarchy_thesis"] = _short_text(thesis, 520)
    answer_order = _string_list(_dict(outline).get("answer_order"))
    if len(answer_order) > 1:
        updated["main_boundary"] = _short_text(answer_order[1], 320)
    return updated


def _section_focus_with_outline(
    focus: dict[str, Any],
    outline: dict[str, Any],
    guidance: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(focus)
    flow = _string_list(focus.get("paragraph_shape"))
    outline_flow = []
    if guidance.get("start_with"):
        outline_flow.append(f"Open with: {guidance['start_with']}")
    if guidance.get("section_thesis"):
        outline_flow.append(f"Land this thesis: {guidance['section_thesis']}")
    for row in _list(_dict(outline).get("narrative_arc")):
        if not isinstance(row, dict):
            continue
        point = _short_text(str(row.get("main_point") or ""), 220)
        role = _short_text(str(row.get("paragraph_role") or ""), 120)
        if point:
            outline_flow.append(f"{role + ': ' if role else ''}{point}")
    updated["paragraph_shape"] = _dedupe([*outline_flow, *flow])[:8]
    return updated


def _section_role_contract_with_outline(role: dict[str, Any], guidance: dict[str, Any]) -> dict[str, Any]:
    updated = dict(role)
    instructions = []
    if guidance.get("section_thesis"):
        instructions.append(f"land this source-weighted thesis: {guidance['section_thesis']}")
    if guidance.get("start_with"):
        instructions.append(f"open from this source-weighted move: {guidance['start_with']}")
    existing = _string_list(role.get("do"))
    if instructions:
        updated["do"] = _dedupe([*instructions, *existing])
    return updated


def _outline_section_guidance(outline: dict[str, Any], section_id: str) -> dict[str, Any]:
    for row in _list(_dict(outline).get("section_guidance")):
        if isinstance(row, dict) and str(row.get("section_id") or "").strip() == section_id:
            return row
    return {}


def _outline_owned_evidence_ids(outline: dict[str, Any]) -> set[str]:
    ids: list[str] = []
    for row in _list(_dict(outline).get("narrative_arc")):
        if isinstance(row, dict):
            ids.extend(_string_list(row.get("evidence_ids")))
    for row in _list(_dict(outline).get("section_guidance")):
        if isinstance(row, dict):
            ids.extend(_string_list(row.get("evidence_ids")))
    return {evidence_id for evidence_id in ids if evidence_id}


def _protected_critical_evidence_ids(packet: dict[str, Any]) -> set[str]:
    protected = set()
    for item in _list(_dict(packet).get("evidence_items")):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or "").strip()
        if not item_id or _looks_low_value_item(item):
            continue
        if _is_analyst_critical_item(item):
            protected.add(item_id)
    return protected


def _is_analyst_critical_item(item: dict[str, Any]) -> bool:
    role = str(item.get("role") or "").strip()
    relation = str(item.get("answer_relation") or "").strip()
    level = str(item.get("obligation_level") or "").strip()
    return bool(item.get("must_use")) and (
        role in {"strongest_counterweight", "decision_crux", "quantitative_anchor"}
        or relation in {"challenges_answer", "identifies_crux"}
        or (level == "must_include" and role in {"scope_boundary"})
    )


def _is_significant_reader_facing_item(item: dict[str, Any]) -> bool:
    if _looks_low_value_item(item):
        return False
    role = str(item.get("role") or "").strip()
    level = str(item.get("obligation_level") or "").strip()
    return bool(item.get("must_use")) or level in {"must_include", "should_include"} or role in {
        "strongest_support",
        "strongest_counterweight",
        "decision_crux",
        "quantitative_anchor",
        "scope_boundary",
    }


def _source_refs_for_items(items_by_id: dict[str, dict[str, Any]], evidence_ids: set[str]) -> list[str]:
    source_refs: list[str] = []
    for evidence_id in sorted(evidence_ids):
        item = _dict(items_by_id.get(evidence_id))
        source_refs.extend(_string_list(item.get("source_ids")))
        source_refs.extend(_string_list(item.get("citation_source_ids")))
        source_refs.extend(_string_list(item.get("source_labels")))
        if item.get("source_label"):
            source_refs.append(str(item.get("source_label")))
    return _dedupe(source_refs)


def _outline_owned_item(item: dict[str, Any], owned_ids: set[str]) -> dict[str, Any]:
    item_id = str(item.get("item_id") or "").strip()
    if item_id in owned_ids:
        return item
    updated = dict(item)
    updated["must_use"] = False
    updated["obligation_level"] = "optional_context"
    if _looks_low_value_item(item):
        updated["role"] = "context_only"
        updated["decision_relevance"] = _short_text(
            "Optional trace context retained in artifacts; not required for reader-facing synthesis.",
            220,
        )
    else:
        updated["role"] = "supplemental_context"
    for key in ("quantities", "quantity_tuples", "quantities_to_preserve", "must_preserve_terms"):
        updated.pop(key, None)
    return updated


def _owned_source_ids(packet: dict[str, Any], owned_ids: set[str]) -> set[str]:
    source_ids = set()
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        if str(item.get("item_id") or "").strip() in owned_ids:
            source_ids.update(_string_list(item.get("source_ids")))
            source_ids.update(_string_list(item.get("citation_source_ids")))
    return source_ids


def _outline_owned_canonical_packet(canonical: dict[str, Any], owned_ids: set[str], *, owned_source_ids: set[str]) -> dict[str, Any]:
    updated = deepcopy(canonical)
    for key in ("mandatory_retention_checklist", "priority_evidence"):
        rows = []
        for row in _list(updated.get(key)):
            if not isinstance(row, dict):
                continue
            filtered = _row_with_owned_evidence_ids(row, owned_ids)
            if filtered:
                rows.append(filtered)
        updated[key] = rows
    for key in ("evidence_language_contracts", "counterweight_dispositions"):
        updated[key] = [
            row
            for row in _list(updated.get(key))
            if isinstance(row, dict) and _row_evidence_ids(row) & owned_ids
        ]
    for key in ("decision_cruxes", "scope_boundaries", "quantitative_anchors", "source_bound_evidence_atoms"):
        if key in updated:
            updated[key] = _rows_owned_by_outline(updated.get(key), owned_ids)
    inventory = _dict(updated.get("organized_evidence_inventory"))
    if inventory:
        inventory = dict(inventory)
        lanes = _dict(inventory.get("lanes"))
        if lanes:
            inventory["lanes"] = {
                lane: _rows_owned_by_outline(rows, owned_ids)
                for lane, rows in lanes.items()
            }
        updated["organized_evidence_inventory"] = inventory
    hierarchy = _dict(updated.get("source_hierarchy"))
    if hierarchy:
        hierarchy = dict(hierarchy)
        hierarchy["source_accounting"] = [
            row
            for row in _list(hierarchy.get("source_accounting"))
            if isinstance(row, dict) and _row_uses_owned_sources(row, owned_source_ids)
        ]
        lanes = _dict(hierarchy.get("lanes"))
        if lanes:
            hierarchy["lanes"] = {
                lane: [
                    row
                    for row in _rows_owned_by_outline(rows, owned_ids)
                    if _row_uses_owned_sources(row, owned_source_ids)
                ]
                for lane, rows in lanes.items()
            }
        updated["source_hierarchy"] = hierarchy
    if "source_weight_judgments" in updated:
        updated["source_weight_judgments"] = [
            row
            for row in _list(updated.get("source_weight_judgments"))
            if isinstance(row, dict) and _row_uses_owned_sources(row, owned_source_ids)
        ]
    for key in (
        "source_weighting_contract",
        "source_weighting_flow_audit",
        "decision_argument_contract",
        "decision_argument_contract_report",
    ):
        updated.pop(key, None)
    spine = _dict(updated.get("evidence_weighted_argument_spine"))
    if spine:
        spine = dict(spine)
        spine["steps"] = [
            row
            for row in _list(spine.get("steps"))
            if isinstance(row, dict) and (_row_evidence_ids(row) & owned_ids or not _row_evidence_ids(row))
        ]
        updated["evidence_weighted_argument_spine"] = spine
    return _dict(_project_owned_evidence_references(updated, owned_ids))


def _row_uses_owned_sources(row: dict[str, Any], owned_source_ids: set[str]) -> bool:
    if not owned_source_ids:
        return True
    source_ids = set(_string_list(row.get("source_ids")))
    if row.get("source_id"):
        source_ids.add(str(row.get("source_id")))
    return bool(source_ids & owned_source_ids)


def _project_owned_evidence_references(value: Any, owned_ids: set[str]) -> Any:
    if isinstance(value, list):
        projected = [_project_owned_evidence_references(row, owned_ids) for row in value]
        return [row for row in projected if row not in (None, {}, [])]
    if not isinstance(value, dict):
        return value
    direct_ids = {
        str(value.get(key) or "").strip()
        for key in ("item_id", "evidence_id", "atom_id", "requirement_id")
        if str(value.get(key) or "").strip()
    }
    if direct_ids and not direct_ids & owned_ids:
        return None
    had_reference_list = False
    updated: dict[str, Any] = {}
    for key, raw in value.items():
        if key in {"evidence_item_ids", "evidence_ids", "item_ids"} and isinstance(raw, list):
            had_reference_list = True
            filtered = [item for item in _string_list(raw) if item in owned_ids]
            if filtered:
                updated[key] = filtered
            continue
        projected = _project_owned_evidence_references(raw, owned_ids)
        if projected not in (None, {}, []):
            updated[key] = projected
    if had_reference_list and not any(
        isinstance(updated.get(key), list) and updated.get(key)
        for key in ("evidence_item_ids", "evidence_ids", "item_ids")
    ):
        return None
    return updated


def _rows_owned_by_outline(value: Any, owned_ids: set[str]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(value):
        if not isinstance(row, dict):
            continue
        row_ids = _row_evidence_ids(row)
        if row_ids and row_ids & owned_ids:
            filtered = _row_with_owned_evidence_ids(row, owned_ids)
            if filtered:
                rows.append(filtered)
    return rows


def _filter_section_packet_to_outline_owned_evidence(packet: dict[str, Any], owned_ids: set[str]) -> dict[str, Any]:
    updated = dict(packet)
    for key in (
        "source_bound_evidence_atoms",
        "section_retention_requirements",
        "evidence_context",
        "section_argument_steps",
    ):
        rows = []
        for row in _list(updated.get(key)):
            if not isinstance(row, dict):
                continue
            row_ids = _row_evidence_ids(row)
            if not row_ids or row_ids & owned_ids:
                filtered = _row_with_owned_evidence_ids(row, owned_ids) if row_ids else row
                if filtered:
                    rows.append(filtered)
        updated[key] = rows
    updated["required_points"] = _filter_required_points(updated.get("required_points"), owned_ids)
    return updated


def _filter_required_points(value: Any, owned_ids: set[str]) -> list[Any]:
    rows = []
    for row in _list(value):
        if isinstance(row, dict):
            row_ids = _row_evidence_ids(row)
            if not row_ids or row_ids & owned_ids:
                rows.append(_row_with_owned_evidence_ids(row, owned_ids) if row_ids else row)
        elif isinstance(row, str):
            ids = set(re.findall(r"decision_writer_item_\d+", row))
            if not ids or ids & owned_ids:
                rows.append(row)
    return [row for row in rows if row]


def _row_with_owned_evidence_ids(row: dict[str, Any], owned_ids: set[str]) -> dict[str, Any]:
    row_ids = _row_evidence_ids(row)
    if row_ids and not row_ids & owned_ids:
        return {}
    updated = dict(row)
    for key in ("evidence_item_ids", "evidence_ids", "item_ids"):
        if isinstance(updated.get(key), list):
            updated[key] = [value for value in _string_list(updated.get(key)) if value in owned_ids]
    return updated


def _row_evidence_ids(row: dict[str, Any]) -> set[str]:
    ids: list[str] = []
    for key in ("item_id", "evidence_id", "atom_id", "requirement_id"):
        value = str(row.get(key) or "").strip()
        if value:
            ids.append(value)
    for key in ("evidence_item_ids", "evidence_ids", "item_ids"):
        ids.extend(_string_list(row.get(key)))
    text_ids = re.findall(r"decision_writer_item_\d+", json.dumps(row, ensure_ascii=False))
    return {evidence_id for evidence_id in [*ids, *text_ids] if evidence_id}


def _looks_low_value_item(item: dict[str, Any]) -> bool:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("claim", "reader_claim", "decision_relevance", "source_appraisal_note", "role")
    ).lower()
    return any(
        pattern in text
        for pattern in (
            "appendix-only",
            "low atomicity",
            "source context",
            "malformed",
            "fragmentary",
            "no (%)",
            "table descriptor",
            "pubmed logo",
            "disclaimer",
        )
    )


def _run_variant_section(
    variant: EditorialInstructionVariant,
    section: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    output_dir: Path,
) -> dict[str, Any]:
    section_packet = _dict(section.get("packet"))
    section_id = str(section_packet.get("section_id") or section.get("section_id") or "section")
    prompt = build_editorial_brief_prompt(section_packet, variant)
    raw = ""
    if backend.strip() == "prompt":
        brief = deterministic_editorial_brief(section_packet, variant)
        status = "prompt_mode_target"
    else:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            json_mode=True,
            num_predict=2048,
        )
        raw = result.text
        brief = _parse_editorial_brief(raw)
        status = "accepted" if brief else "parse_failed"
        if not brief:
            brief = deterministic_editorial_brief(section_packet, variant)
    score = score_editorial_brief(brief, prompt=prompt, section_packet=section_packet)
    safe_id = _safe_filename(section_id)
    write_markdown(output_dir / f"{safe_id}_prompt.txt", prompt)
    write_json(output_dir / f"{safe_id}_editorial_brief.json", brief)
    if raw:
        write_markdown(output_dir / f"{safe_id}_raw.txt", raw)
    return {
        "section_id": section_id,
        "heading": section_packet.get("heading"),
        "status": status,
        "prompt_path": f"{variant.variant_id}/{safe_id}_prompt.txt",
        "brief_path": f"{variant.variant_id}/{safe_id}_editorial_brief.json",
        "brief": brief,
        "score": score,
    }


def _selected_variants(variant_ids: list[str] | None) -> list[EditorialInstructionVariant]:
    if not variant_ids:
        return list(VARIANTS)
    wanted = set(variant_ids)
    variants = [variant for variant in VARIANTS if variant.variant_id in wanted]
    missing = sorted(wanted - {variant.variant_id for variant in variants})
    if missing:
        raise ValueError(f"unknown editorial brief variants: {', '.join(missing)}")
    return variants


def _extract_markdown_memo(raw: str) -> str:
    text = str(raw or "").strip()
    fenced = re.search(r"```(?:markdown|md)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    if "# Decision Memo" in text:
        return text[text.find("# Decision Memo") :].strip() + "\n"
    return text + ("\n" if text else "")


def _repeated_sentence_count(text: str) -> int:
    sentences = [re.sub(r"\s+", " ", sentence.strip().lower()) for sentence in re.split(r"(?<=[.!?])\s+", text) if len(sentence.strip()) > 40]
    seen: set[str] = set()
    repeats = 0
    for sentence in sentences:
        if sentence in seen:
            repeats += 1
        seen.add(sentence)
    return repeats


def _content_terms(text: str) -> list[str]:
    stop = {
        "about", "after", "also", "because", "between", "could", "from", "have", "into",
        "more", "should", "than", "that", "their", "there", "these", "this", "what",
        "when", "where", "which", "with", "would",
    }
    return [token for token in re.findall(r"[a-z0-9]{4,}", str(text).lower()) if token not in stop]


def _variant_result(variant: EditorialInstructionVariant, section_results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [_dict(row.get("score")) for row in section_results]
    mean_score = round(sum(float(row.get("score", 0)) for row in scores) / max(1, len(scores)), 1)
    mean_chars = round(sum(int(row.get("prompt_chars", 0)) for row in scores) / max(1, len(scores)))
    mean_evidence = round(sum(int(row.get("evidence_count", 0)) for row in scores) / max(1, len(scores)), 1)
    mean_low_value = round(sum(int(row.get("low_value_evidence_count", 0)) for row in scores) / max(1, len(scores)), 1)
    mean_source_coverage = round(sum(float(row.get("source_coverage", 0)) for row in scores) / max(1, len(scores)), 3)
    total_clutter = sum(len(_list(row.get("clutter_hits"))) for row in scores)
    notes = []
    if mean_chars > 7000:
        notes.append("prompts are still large")
    if total_clutter:
        notes.append("exposes internal control-surface keys")
    if mean_source_coverage < 0.8:
        notes.append("source coverage is weak")
    if not notes:
        notes.append("clean candidate")
    return {
        "variant_id": variant.variant_id,
        "label": variant.label,
        "input_mode": variant.input_mode,
        "aggregate_score": {
            "mean_score": mean_score,
            "mean_prompt_chars": mean_chars,
            "mean_evidence_count": mean_evidence,
            "mean_low_value_evidence_count": mean_low_value,
            "mean_source_coverage": mean_source_coverage,
            "total_clutter_hits": total_clutter,
        },
        "section_results": section_results,
        "notes": notes,
    }


def _experiment_summary(
    *,
    memo_ready_packet: dict[str, Any],
    section_plan: dict[str, Any],
    backend: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    ranked = sorted(results, key=lambda row: float(_dict(row.get("aggregate_score")).get("mean_score", 0)), reverse=True)
    return {
        "schema_id": EDITORIAL_BRIEF_EXPERIMENT_SCHEMA,
        "backend": backend,
        "decision_question": memo_ready_packet.get("decision_question"),
        "section_count": len(_list(section_plan.get("sections"))),
        "variant_count": len(results),
        "recommended_variant": ranked[0]["variant_id"] if ranked else "",
        "variant_results": results,
    }


def _variant_input_context(section_packet: dict[str, Any], variant: EditorialInstructionVariant) -> dict[str, Any]:
    if variant.input_mode == "raw_section_packet":
        return section_packet
    return _compact_section_context(section_packet, variant)


def _compact_section_context(section_packet: dict[str, Any], variant: EditorialInstructionVariant) -> dict[str, Any]:
    focus = _dict(section_packet.get("section_focus"))
    context = {
        "section_id": section_packet.get("section_id"),
        "heading": section_packet.get("heading"),
        "reader_job": focus.get("reader_question") or section_packet.get("section_job"),
        "section_job": section_packet.get("section_job"),
        "prose_lead": focus.get("prose_lead") or focus.get("lead"),
        "new_value": focus.get("new_value"),
        "paragraph_shape": focus.get("paragraph_shape"),
        "required_points": _compact_required_points(section_packet),
        "evidence_rows": _brief_evidence_rows(
            section_packet,
            include_validation=variant.include_validation_obligations,
            exclude_low_value_context=variant.exclude_low_value_context,
        ),
        "caveats": _caveats_to_preserve(section_packet),
        "leave_to_other_sections": _leave_to_other_sections(section_packet),
    }
    if variant.include_source_weighting:
        context["source_weighting"] = _compact_source_weighting(section_packet)
        context["source_weighting_note"] = _source_weighting_note(section_packet)
    if variant.include_validation_obligations:
        context["validation_obligations"] = _compact_validation_obligations(section_packet)
    return {key: value for key, value in context.items() if value not in ({}, [], "", None)}


def _brief_evidence_rows(
    section_packet: dict[str, Any],
    *,
    include_validation: bool,
    exclude_low_value_context: bool = False,
) -> list[dict[str, Any]]:
    rows = []
    for row in _list(section_packet.get("source_bound_evidence_atoms")):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "evidence_id": row.get("evidence_id") or row.get("atom_id") or row.get("item_id"),
                "source_ids": _string_list(row.get("source_ids")) or _string_list(row.get("citation_source_ids")),
                "role": row.get("citation_role") or row.get("role") or row.get("use_role") or "load_bearing",
                "prose_job": _short_text(str(row.get("writing_job") or row.get("prose_job") or row.get("claim") or ""), 260),
                "required_detail": _required_detail(row),
            }
        )
    if rows:
        return _filter_evidence_rows(rows, exclude_low_value_context=exclude_low_value_context)[:10]
    for row in _list(section_packet.get("evidence_context")):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "evidence_id": row.get("item_id") or row.get("evidence_id"),
                "source_ids": _string_list(row.get("source_ids")),
                "role": row.get("role") or row.get("decision_role") or "load_bearing",
                "prose_job": _short_text(str(row.get("why_it_matters") or row.get("claim") or row.get("statement") or ""), 260),
                "required_detail": _required_detail(row),
            }
        )
    if include_validation:
        for row in _list(section_packet.get("section_retention_requirements")):
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "evidence_id": row.get("item_id") or row.get("evidence_id") or row.get("requirement_id"),
                    "source_ids": _string_list(row.get("source_ids")),
                    "role": "retention_obligation",
                    "prose_job": _short_text(str(row.get("writing_job") or row.get("claim") or row.get("requirement") or ""), 260),
                    "required_detail": _required_detail(row),
                }
            )
    return [
        row
        for row in _filter_evidence_rows(rows, exclude_low_value_context=exclude_low_value_context)[:10]
        if row.get("evidence_id") or row.get("source_ids") or row.get("prose_job")
    ]


def _filter_evidence_rows(rows: list[dict[str, Any]], *, exclude_low_value_context: bool) -> list[dict[str, Any]]:
    if not exclude_low_value_context:
        return rows
    retained = [row for row in rows if not _looks_low_value_evidence(row)]
    return retained or rows[:3]


def _looks_low_value_evidence(row: dict[str, Any]) -> bool:
    text = " ".join(str(row.get(key) or "") for key in ("prose_job", "required_detail", "role")).lower()
    patterns = (
        "appendix-only",
        "low atomicity",
        "use only as source context",
        "source context",
        "baseline characteristic",
        "no (%)",
        "table descriptor",
        "eligibility window",
        "study descriptor",
        "trace_only",
    )
    return any(pattern in text for pattern in patterns)


def _low_value_evidence_count(rows: list[Any]) -> int:
    return sum(1 for row in rows if isinstance(row, dict) and _looks_low_value_evidence(row))


def _required_detail(row: dict[str, Any]) -> str:
    quantities = _string_list(row.get("protected_quantities")) or _string_list(row.get("quantities"))
    if quantities:
        return "; ".join(quantities[:3])
    for key in ("required_detail", "quote", "excerpt", "scope", "caveat", "endpoint"):
        value = str(row.get(key) or "").strip()
        if value:
            return _short_text(value, 220)
    return ""


def _compact_required_points(section_packet: dict[str, Any]) -> list[str]:
    points = []
    for row in _list(section_packet.get("required_points")):
        if isinstance(row, str):
            points.append(_short_text(row, 220))
        elif isinstance(row, dict):
            points.append(_short_text(str(row.get("point") or row.get("claim") or row.get("text") or ""), 220))
    return [point for point in points if point][:8]


def _compact_source_weighting(section_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(section_packet.get("source_weighting")) + _list(section_packet.get("source_role_groups")):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "source_ids": _string_list(row.get("source_ids")) or _string_list(row.get("source_id")),
                "role": row.get("role") or row.get("weight_role") or row.get("primary_lane"),
                "rationale": _short_text(str(row.get("rationale") or row.get("reader_use_sentence") or row.get("why_this_role") or ""), 240),
            }
        )
    return rows[:8]


def _compact_validation_obligations(section_packet: dict[str, Any]) -> dict[str, Any]:
    contract = _dict(section_packet.get("validation_contract"))
    return {
        "known_required_points": len(_list(section_packet.get("required_points"))),
        "known_retention_requirements": len(_list(section_packet.get("section_retention_requirements"))),
        "known_evidence_atoms": len(_list(section_packet.get("source_bound_evidence_atoms"))),
        "validation_summary": _short_text(str(contract.get("summary") or contract.get("status") or ""), 240),
    }


def _section_thesis(compact: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> str:
    lead = str(compact.get("prose_lead") or compact.get("section_job") or "").strip()
    if lead:
        return _short_text(lead.rstrip(".") + ".", 260)
    if evidence_rows:
        return _short_text(str(evidence_rows[0].get("prose_job") or ""), 260)
    return "State the section's decision-relevant point in one direct sentence."


def _must_land_distinction(compact: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> str:
    points = _string_list(compact.get("required_points"))
    if points:
        return _short_text(points[0], 260)
    roles = _dedupe([str(row.get("role") or "") for row in evidence_rows if row.get("role")])
    if len(roles) > 1:
        return "Distinguish " + ", ".join(roles[:3]) + " evidence rather than blending it."
    return str(compact.get("new_value") or compact.get("reader_job") or "Make this section add one distinct analytic move.")


def _source_weighting_note(section_packet: dict[str, Any]) -> str:
    rows = _compact_source_weighting(section_packet)
    for row in rows:
        rationale = str(row.get("rationale") or "").strip()
        if rationale:
            return rationale
    if rows:
        return "Explain why the listed sources play different roles in this section."
    return ""


def _caveats_to_preserve(section_packet: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("limiting_evidence", "required_points", "section_retention_requirements"):
        for row in _list(section_packet.get(key)):
            if isinstance(row, str) and re.search(r"\b(limit|caveat|scope|uncertain|bound|could change)\b", row, re.I):
                values.append(_short_text(row, 220))
            elif isinstance(row, dict):
                text = " ".join(str(row.get(k) or "") for k in ("caveat", "scope", "limit", "claim", "writing_job", "requirement"))
                if re.search(r"\b(limit|caveat|scope|uncertain|bound|could change)\b", text, re.I):
                    values.append(_short_text(text, 220))
    return _dedupe([value for value in values if value])[:5]


def _leave_to_other_sections(section_packet: dict[str, Any]) -> list[str]:
    contract = _dict(section_packet.get("section_role_contract"))
    avoid = [_short_text(str(value), 180) for value in _list(contract.get("avoid"))]
    focus = _dict(section_packet.get("section_focus"))
    if focus.get("new_value"):
        avoid.append("Do not repeat other sections; add this section's specific value.")
    return _dedupe([value for value in avoid if value])[:5]


def _source_ids_in_section(section_packet: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for value in section_packet.values():
        ids.extend(_source_ids_in_value(value))
    return _dedupe(ids)


def _expected_source_ids_for_score(section_packet: dict[str, Any]) -> list[str]:
    rows = _brief_evidence_rows(section_packet, include_validation=True, exclude_low_value_context=True)
    ids: list[str] = []
    for row in rows:
        ids.extend(_string_list(row.get("source_ids")))
    return _dedupe(ids) or _source_ids_in_section(section_packet)


def _source_ids_in_value(value: Any) -> list[str]:
    if isinstance(value, dict):
        ids: list[str] = []
        for key, nested in value.items():
            if key in {"source_id", "source_ids", "citation_source_ids"}:
                ids.extend(_string_list(nested))
            else:
                ids.extend(_source_ids_in_value(nested))
        return ids
    if isinstance(value, list):
        ids = []
        for nested in value:
            ids.extend(_source_ids_in_value(nested))
        return ids
    return []


def _required_point_count(section_packet: dict[str, Any]) -> int:
    return len(_list(section_packet.get("required_points"))) + len(_list(section_packet.get("section_retention_requirements")))


def _clutter_hits(text: str) -> list[str]:
    lower = text.lower()
    return sorted(key for key in INTERNAL_CLUTTER_KEYS if key.lower() in lower)


def _looks_generic(brief: dict[str, Any]) -> bool:
    text = " ".join(str(brief.get(key) or "") for key in ("reader_job", "section_thesis", "must_land_distinction", "source_weighting_note")).lower()
    generic = ["important evidence", "various sources", "relevant information", "this section should discuss"]
    return any(phrase in text for phrase in generic)


def _parse_editorial_brief(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(canonical_json_output(raw))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    if payload.get("schema_id") != "editorial_brief_v1":
        payload["schema_id"] = "editorial_brief_v1"
    return payload


def _safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(text).strip()).strip("_")
    return cleaned[:80] or "section"


def _md_cell(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).replace("|", "\\|").strip()
