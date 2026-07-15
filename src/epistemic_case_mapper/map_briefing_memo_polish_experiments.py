from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.map_briefing_markdown_quality import markdown_structure_issues, repair_markdown_structure
from epistemic_case_mapper.map_briefing_memo_paragraph_polish import collect_parallel_paragraph_memo_polish_proposals
from epistemic_case_mapper.map_briefing_memo_polish_diagnostics import (
    build_memo_polish_diagnostics,
    high_confidence_unsupported_additions,
    prose_quality_diagnostics,
)
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    _decision_usefulness_not_worse,
    _extract_markdown,
    _final_polish_comparison,
    _json_polish_semantic_rejection,
    _retention_not_worse,
    build_decision_usefulness_retention_report,
    build_memo_ready_final_polish_prompt,
    build_memo_ready_packet_retention_report,
    normalize_memo_ready_polish_text,
    run_memo_ready_final_polish,
    run_memo_ready_json_final_polish_experiment,
    run_memo_ready_hybrid_section_final_polish_experiment,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
)
from epistemic_case_mapper.map_briefing_memo_ready_polish_guardrails import build_memo_ready_final_polish_guardrails
from epistemic_case_mapper.map_briefing_memo_ready_presentation import run_memo_ready_presentation_normalization
from epistemic_case_mapper.map_briefing_source_identity import (
    project_source_text_to_ids_for_model,
    project_sources_to_ids_for_model,
    replace_source_aliases_with_ids,
)
from epistemic_case_mapper.model_backends import run_model_backend


DEFAULT_POLISH_EXPERIMENT_VARIANTS: tuple[str, ...] = (
    "baseline_no_polish",
    "presentation_only",
    "json_issue_lens",
    "hybrid_section_completion",
    "paragraph_targeted",
    "paragraph_then_completion",
    "full_memo_rewrite",
)


def run_memo_polish_experiment_matrix(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    variants: list[str] | None = None,
    output_dir: Path | None = None,
    run_reader_judge: bool = False,
) -> dict[str, Any]:
    selected = variants or list(DEFAULT_POLISH_EXPERIMENT_VARIANTS)
    results = []
    for variant in selected:
        result = run_memo_polish_experiment_variant(
            variant,
            memo,
            packet,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            run_reader_judge=run_reader_judge,
        )
        results.append(result)
        if output_dir is not None:
            _write_variant_artifacts(output_dir, result)
    summary = {
        "schema_id": "memo_polish_experiment_matrix_v1",
        "backend": backend,
        "variant_count": len(results),
        "variants": [_compact_variant_result(row) for row in results],
        "promotion_candidates": _promotion_candidates(results),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "experiment_matrix_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        (output_dir / "experiment_matrix_summary.md").write_text(render_memo_polish_experiment_matrix_markdown(summary))
    return {"summary": summary, "results": results}


def run_memo_polish_experiment_variant(
    variant: str,
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_reader_judge: bool = False,
) -> dict[str, Any]:
    if variant == "baseline_no_polish":
        base = _accepted_result(variant, memo, memo, packet, {"status": "baseline", "accepted": True})
        return _with_optional_judge(base, memo, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries, run_reader_judge=run_reader_judge)
    if variant == "presentation_only":
        presentation = run_memo_ready_presentation_normalization(memo, packet)
        base = _accepted_result(variant, memo, str(presentation.get("memo") or memo), packet, presentation.get("report", {}))
        return _with_optional_judge(base, memo, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries, run_reader_judge=run_reader_judge)
    if variant == "json_issue_lens":
        polished = run_memo_ready_json_final_polish_experiment(memo, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
        return _finalize_variant(variant, memo, polished, packet, run_reader_judge=run_reader_judge, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
    if variant == "hybrid_section_completion":
        polished = run_memo_ready_hybrid_section_final_polish_experiment(memo, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
        return _finalize_variant(variant, memo, polished, packet, run_reader_judge=run_reader_judge, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
    if variant == "paragraph_targeted":
        polished = run_memo_ready_paragraph_final_polish_experiment(memo, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
        return _finalize_variant(variant, memo, polished, packet, run_reader_judge=run_reader_judge, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
    if variant == "paragraph_then_completion":
        paragraph = run_memo_ready_paragraph_final_polish_experiment(memo, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
        intermediate = str(paragraph.get("memo") or memo)
        section = run_memo_ready_hybrid_section_final_polish_experiment(intermediate, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
        merged = {
            "memo": section.get("memo") or intermediate,
            "prompt": "\n\n".join([str(paragraph.get("prompt") or ""), str(section.get("prompt") or "")]).strip(),
            "raw": "\n\n".join([str(paragraph.get("raw") or ""), str(section.get("raw") or "")]).strip(),
            "report": {
                "schema_id": "memo_polish_experiment_composed_report_v1",
                "status": section.get("report", {}).get("status"),
                "accepted": bool(paragraph.get("report", {}).get("accepted") or section.get("report", {}).get("accepted")),
                "paragraph_report": paragraph.get("report", {}),
                "section_report": section.get("report", {}),
            },
        }
        return _finalize_variant(variant, memo, merged, packet, run_reader_judge=run_reader_judge, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
    if variant == "full_memo_rewrite":
        polished = run_full_memo_rewrite_polish_experiment(memo, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
        return _finalize_variant(variant, memo, polished, packet, run_reader_judge=run_reader_judge, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
    raise ValueError(f"unknown memo polish experiment variant: {variant}")


def run_memo_ready_paragraph_final_polish_experiment(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    max_paragraphs: int = 5,
) -> dict[str, Any]:
    before = build_memo_ready_packet_retention_report(memo, packet)
    before_decision_usefulness = build_decision_usefulness_retention_report(memo, packet)
    report = {
        "schema_id": "memo_ready_paragraph_final_polish_experiment_report_v1",
        "status": "skipped_prompt_backend" if backend.strip() == "prompt" else "not_run",
        "accepted": False,
        "issues": [],
    }
    proposal_bundle = collect_parallel_paragraph_memo_polish_proposals(
        memo,
        packet,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        max_paragraphs=max_paragraphs,
        run_model=run_model_backend,
    )
    if backend.strip() == "prompt":
        return {"memo": memo, "prompt": proposal_bundle.get("prompt", ""), "raw": "", "report": report}
    current = memo
    accepted_paragraphs: list[dict[str, Any]] = []
    rejected_paragraphs: list[dict[str, Any]] = []
    for paragraph, paragraph_report in zip(_list(proposal_bundle.get("selected_paragraphs")), _list(proposal_bundle.get("paragraph_reports")), strict=False):
        if not isinstance(paragraph, dict) or not isinstance(paragraph_report, dict):
            continue
        if not paragraph_report.get("accepted_candidate"):
            rejected_paragraphs.append(_paragraph_rejection(paragraph, paragraph_report, "candidate_not_accepted"))
            continue
        original = str(paragraph.get("markdown") or "").strip()
        replacement = normalize_memo_ready_polish_text(repair_markdown_structure(str(paragraph_report.get("replacement_markdown") or "")))
        if not replacement.strip() or replacement.strip() == original:
            rejected_paragraphs.append(_paragraph_rejection(paragraph, paragraph_report, "empty_or_unchanged_replacement"))
            continue
        if current.count(original) != 1:
            rejected_paragraphs.append(_paragraph_rejection(paragraph, paragraph_report, "paragraph_target_not_unique"))
            continue
        candidate = current.replace(original, replacement.strip(), 1)
        rejection = _json_polish_semantic_rejection(
            original_memo=memo,
            candidate=candidate,
            packet=packet,
            before_retention=before,
            before_decision_usefulness=before_decision_usefulness,
        )
        if rejection:
            rejected_paragraphs.append(_paragraph_rejection(paragraph, paragraph_report, rejection))
            continue
        current = candidate
        accepted_paragraphs.append(_paragraph_acceptance(paragraph, paragraph_report))
    after = build_memo_ready_packet_retention_report(current, packet)
    after_decision_usefulness = build_decision_usefulness_retention_report(current, packet)
    structure_issues = markdown_structure_issues(current, original=memo)
    diagnostics = build_memo_polish_diagnostics(memo, current, packet)
    unsupported_additions = high_confidence_unsupported_additions(diagnostics)
    decision_usefulness_not_worse = _decision_usefulness_not_worse(before_decision_usefulness, after_decision_usefulness)
    accepted = (
        bool(accepted_paragraphs)
        and _retention_not_worse(before, after)
        and decision_usefulness_not_worse
        and not structure_issues
        and not unsupported_additions
    )
    report.update(
        {
            "status": "accepted" if accepted else "no_safe_paragraph_polish_kept_original",
            "accepted": accepted,
            "before_missing_mandatory_count": before.get("missing_mandatory_count", 0),
            "after_missing_mandatory_count": after.get("missing_mandatory_count", 0),
            "structure_issues": structure_issues,
            "polish_diagnostics": diagnostics,
            "polish_comparison": _final_polish_comparison(
                before_memo=memo,
                after_memo=current,
                before_retention=before,
                after_retention=after,
                before_decision_usefulness=before_decision_usefulness,
                after_decision_usefulness=after_decision_usefulness,
                diagnostics=diagnostics,
            ),
            "paragraph_proposal_report": proposal_bundle.get("report", {}),
            "accepted_paragraph_count": len(accepted_paragraphs),
            "rejected_paragraph_count": len(rejected_paragraphs),
            "accepted_paragraphs": accepted_paragraphs,
            "rejected_paragraphs": rejected_paragraphs,
            "decision_usefulness_not_worse": decision_usefulness_not_worse,
            "issues": [] if accepted else ["no safe paragraph polish accepted"],
        }
    )
    return {
        "memo": current if accepted else memo,
        "prompt": str(proposal_bundle.get("prompt") or ""),
        "raw": str(proposal_bundle.get("raw") or ""),
        "report": report,
    }


def run_full_memo_rewrite_polish_experiment(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    before = build_memo_ready_packet_retention_report(memo, packet)
    before_decision_usefulness = build_decision_usefulness_retention_report(memo, packet)
    prompt = build_full_memo_rewrite_polish_prompt(memo, packet)
    report = {
        "schema_id": "full_memo_rewrite_polish_experiment_report_v1",
        "status": "skipped_prompt_backend" if backend.strip() == "prompt" else "not_run",
        "accepted": False,
        "issues": [],
    }
    if backend.strip() == "prompt":
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries, json_mode=False)
    except RuntimeError as exc:
        report.update({"status": "backend_error", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    candidate = normalize_memo_ready_polish_text(repair_markdown_structure(_extract_markdown(raw)))
    if not candidate.strip():
        report.update({"status": "empty_or_unparseable", "issues": ["rewrite returned no markdown"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    rejection = _json_polish_semantic_rejection(
        original_memo=memo,
        candidate=candidate,
        packet=packet,
        before_retention=before,
        before_decision_usefulness=before_decision_usefulness,
    )
    after = build_memo_ready_packet_retention_report(candidate, packet)
    after_decision_usefulness = build_decision_usefulness_retention_report(candidate, packet)
    diagnostics = build_memo_polish_diagnostics(memo, candidate, packet)
    report.update(
        {
            "status": "accepted" if not rejection else "rejected_kept_original",
            "accepted": not bool(rejection),
            "rejection": rejection,
            "polish_diagnostics": diagnostics,
            "polish_comparison": _final_polish_comparison(
                before_memo=memo,
                after_memo=candidate,
                before_retention=before,
                after_retention=after,
                before_decision_usefulness=before_decision_usefulness,
                after_decision_usefulness=after_decision_usefulness,
                diagnostics=diagnostics,
            ),
            "issues": [] if not rejection else [rejection],
        }
    )
    return {"memo": candidate if not rejection else memo, "prompt": prompt, "raw": raw, "report": report}


def build_full_memo_rewrite_polish_prompt(memo: str, packet: dict[str, Any]) -> str:
    source_trail = _list(packet.get("source_trail"))
    guardrails = build_memo_ready_final_polish_guardrails(packet)
    guardrails = project_source_text_to_ids_for_model(project_sources_to_ids_for_model(guardrails, source_trail), source_trail)
    memo_for_model = replace_source_aliases_with_ids(memo, source_trail)
    return (
        "Rewrite this decision memo so it reads like polished decision-ready analysis.\n"
        "This is an experiment: preserve all evidence-bearing content while improving flow and presentation.\n\n"
        "Rules:\n"
        "- Return the full memo in Markdown.\n"
        "- Preserve the decision question, answer stance, source IDs, quantities, uncertainty, caveats, and practical implications.\n"
        "- You may reorganize sentences for flow using existing facts, sources, populations, mechanisms, comparisons, and recommendations.\n"
        "- Keep citations near the claims they support.\n"
        "- Make the memo readable enough for a thoughtful human judge.\n\n"
        f"Validation guardrails:\n{json.dumps(guardrails, indent=2, ensure_ascii=False)}\n\n"
        f"Current memo:\n{memo_for_model.strip()}\n"
    )


def run_reader_judge_evaluation(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    report = deterministic_reader_quality_report(memo, packet)
    if backend.strip() == "prompt":
        return {**report, "model_judge": {"status": "skipped_prompt_backend"}}
    prompt = build_reader_judge_prompt(memo, packet)
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        return {**report, "model_judge": {"status": "backend_error", "issues": [str(exc)]}}
    payload = _parse_json_payload(result.text)
    model_judge = payload if isinstance(payload, dict) else {"status": "unparseable", "raw_preview": result.text[:500]}
    return {**report, "model_judge": model_judge}


def build_reader_judge_prompt(memo: str, packet: dict[str, Any]) -> str:
    return (
        "Evaluate this decision memo for reader-facing quality without rewarding unsupported polish.\n"
        "Return JSON only.\n\n"
        "Score 1-5 for:\n"
        "- clarity\n"
        "- decision_usefulness\n"
        "- narrative_flow\n"
        "- evidence_weighting\n"
        "- citation_readability\n"
        "- faithfulness_to_stated_evidence\n\n"
        "Also return: preferred_for_human_judge: true/false, top_strengths, top_weaknesses, promotion_risk.\n\n"
        f"Decision question: {packet.get('decision_question')}\n\n"
        f"Memo:\n{memo.strip()}\n"
    )


def deterministic_reader_quality_report(memo: str, packet: dict[str, Any]) -> dict[str, Any]:
    text = str(memo or "")
    prose = prose_quality_diagnostics(text)
    lower = text.lower()
    stock = sum(lower.count(phrase) for phrase in ("supporting this is", "to ensure a complete picture", "these points bound", "primary evidence", "rooted in"))
    citation_count = text.count("[")
    words = len(re.findall(r"\b\w+\b", text))
    section_count = len(re.findall(r"(?m)^##\s+", text))
    practical_present = bool(re.search(r"(?mi)^##\s+Practical", text))
    bottom_line_present = "**Bottom Line:**" in text or re.search(r"(?mi)^##\s+Bottom", text)
    warning_count = int(prose.get("warning_count", 0) or 0)
    score = 100
    score -= min(30, warning_count * 10)
    score -= min(20, stock * 5)
    if "..." in text or "…" in text:
        score -= 30
    if citation_count > 24:
        score -= min(18, (citation_count - 24) * 2)
    if words < 350 or words > 1400:
        score -= 10
    if not practical_present:
        score -= 10
    if not bottom_line_present:
        score -= 12
    return {
        "schema_id": "deterministic_reader_quality_report_v1",
        "word_count": words,
        "section_count": section_count,
        "citation_count": citation_count,
        "stock_phrase_count": stock,
        "has_unfinished_marker": "..." in text or "…" in text,
        "bottom_line_present": bottom_line_present,
        "practical_section_present": practical_present,
        "prose_quality": prose,
        "reader_quality_score": max(0, score),
    }


def render_memo_polish_experiment_matrix_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Memo Polish Experiment Matrix",
        "",
        f"Backend: `{summary.get('backend')}`",
        "",
        "| Variant | Accepted | Reader score | Missing | Quant missing | Warnings | Stock | Unfinished | Promotion |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in _list(summary.get("variants")):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("variant")),
                    str(row.get("accepted")),
                    str(row.get("reader_quality_score")),
                    str(row.get("missing_mandatory_count")),
                    str(row.get("missing_quantity_count")),
                    str(row.get("prose_warning_count")),
                    str(row.get("stock_phrase_count")),
                    str(row.get("has_unfinished_marker")),
                    str(row.get("promotion_candidate")),
                ]
            )
            + " |"
        )
    candidates = _list(summary.get("promotion_candidates"))
    lines.extend(["", "## Promotion Candidates", ""])
    if candidates:
        for candidate in candidates:
            lines.append(f"- `{candidate.get('variant')}`: score {candidate.get('reader_quality_score')}")
    else:
        lines.append("- None met the no-regression promotion gate.")
    return "\n".join(lines).rstrip() + "\n"


def _finalize_variant(
    variant: str,
    original_memo: str,
    polish_result: dict[str, Any],
    packet: dict[str, Any],
    *,
    run_reader_judge: bool,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    polished_memo = str(polish_result.get("memo") or original_memo)
    presentation = run_memo_ready_presentation_normalization(polished_memo, packet)
    memo = str(presentation.get("memo") or polished_memo)
    report = {
        "schema_id": "memo_polish_experiment_variant_report_v1",
        "variant": variant,
        "accepted": bool(polish_result.get("report", {}).get("accepted") or memo != original_memo),
        "polish_report": polish_result.get("report", {}),
        "presentation_report": presentation.get("report", {}),
    }
    result = _accepted_result(variant, original_memo, memo, packet, report, prompt=polish_result.get("prompt", ""), raw=polish_result.get("raw", ""))
    return _with_optional_judge(result, original_memo, packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries, run_reader_judge=run_reader_judge)


def _accepted_result(
    variant: str,
    original_memo: str,
    memo: str,
    packet: dict[str, Any],
    report: dict[str, Any],
    *,
    prompt: str = "",
    raw: str = "",
) -> dict[str, Any]:
    before = build_memo_ready_packet_retention_report(original_memo, packet)
    after = build_memo_ready_packet_retention_report(memo, packet)
    before_decision_usefulness = build_decision_usefulness_retention_report(original_memo, packet)
    after_decision_usefulness = build_decision_usefulness_retention_report(memo, packet)
    diagnostics = build_memo_polish_diagnostics(original_memo, memo, packet)
    comparison = _final_polish_comparison(
        before_memo=original_memo,
        after_memo=memo,
        before_retention=before,
        after_retention=after,
        before_decision_usefulness=before_decision_usefulness,
        after_decision_usefulness=after_decision_usefulness,
        diagnostics=diagnostics,
    )
    return {
        "variant": variant,
        "memo": memo,
        "prompt": str(prompt or ""),
        "raw": str(raw or ""),
        "report": report,
        "retention": after,
        "decision_usefulness": after_decision_usefulness,
        "diagnostics": diagnostics,
        "comparison": comparison,
        "reader_quality": deterministic_reader_quality_report(memo, packet),
    }


def _with_optional_judge(
    result: dict[str, Any],
    original_memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_reader_judge: bool,
) -> dict[str, Any]:
    if not run_reader_judge:
        return result
    judged = run_reader_judge_evaluation(str(result.get("memo") or original_memo), packet, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
    result = dict(result)
    result["reader_quality"] = judged
    return result


def _compact_variant_result(result: dict[str, Any]) -> dict[str, Any]:
    comparison = _dict(result.get("comparison"))
    reader = _dict(result.get("reader_quality"))
    diagnostics = _dict(result.get("diagnostics"))
    prose = _dict(diagnostics.get("prose_quality"))
    high_unsupported = high_confidence_unsupported_additions(diagnostics)
    row = {
        "variant": result.get("variant"),
        "accepted": _dict(result.get("report")).get("accepted"),
        "word_count": reader.get("word_count"),
        "reader_quality_score": reader.get("reader_quality_score"),
        "missing_mandatory_count": comparison.get("after_missing_mandatory_count"),
        "missing_quantity_count": comparison.get("after_missing_quantity_count"),
        "decision_usefulness_missing_count": comparison.get("after_decision_usefulness_missing_count"),
        "unsupported_addition_count": comparison.get("unsupported_addition_count"),
        "high_unsupported_addition_count": len(high_unsupported),
        "prose_warning_count": prose.get("warning_count"),
        "prose_warnings": prose.get("warnings", []),
        "stock_phrase_count": reader.get("stock_phrase_count"),
        "has_unfinished_marker": reader.get("has_unfinished_marker"),
        "citation_count": reader.get("citation_count"),
    }
    row["promotion_candidate"] = _is_promotion_candidate(row)
    return row


def _promotion_candidates(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [_compact_variant_result(row) for row in results]
    return sorted(
        [row for row in rows if row.get("promotion_candidate")],
        key=lambda row: int(row.get("reader_quality_score") or 0),
        reverse=True,
    )


def _is_promotion_candidate(row: dict[str, Any]) -> bool:
    return (
        int(row.get("missing_mandatory_count") or 0) == 0
        and int(row.get("missing_quantity_count") or 0) == 0
        and int(row.get("decision_usefulness_missing_count") or 0) == 0
        and int(row.get("high_unsupported_addition_count") or 0) == 0
        and not bool(row.get("has_unfinished_marker"))
        and int(row.get("reader_quality_score") or 0) >= 70
    )


def _write_variant_artifacts(output_dir: Path, result: dict[str, Any]) -> None:
    variant_dir = output_dir / str(result.get("variant") or "variant")
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "memo.md").write_text(str(result.get("memo") or ""))
    (variant_dir / "report.json").write_text(json.dumps(result.get("report", {}), indent=2, ensure_ascii=False))
    (variant_dir / "comparison.json").write_text(json.dumps(result.get("comparison", {}), indent=2, ensure_ascii=False))
    (variant_dir / "reader_quality.json").write_text(json.dumps(result.get("reader_quality", {}), indent=2, ensure_ascii=False))
    prompt = str(result.get("prompt") or "")
    raw = str(result.get("raw") or "")
    if prompt:
        (variant_dir / "prompt.txt").write_text(prompt)
    if raw:
        (variant_dir / "raw.txt").write_text(raw)


def _paragraph_acceptance(paragraph: dict[str, Any], paragraph_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "paragraph_id": paragraph.get("paragraph_id"),
        "section_heading": paragraph.get("section_heading"),
        "issues": paragraph.get("issues", []),
        "reason": str(paragraph_report.get("reason") or "").strip(),
        "replacement_preview": _preview(paragraph_report.get("replacement_markdown")),
    }


def _paragraph_rejection(paragraph: dict[str, Any], paragraph_report: dict[str, Any], issue: str) -> dict[str, Any]:
    return {
        "paragraph_id": paragraph.get("paragraph_id"),
        "section_heading": paragraph.get("section_heading"),
        "issue": issue,
        "candidate_issues": _list(paragraph_report.get("issues")),
        "reason": str(paragraph_report.get("reason") or "").strip(),
        "replacement_preview": _preview(paragraph_report.get("replacement_markdown")),
    }


def _parse_json_payload(raw: str) -> Any:
    cleaned = str(raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _preview(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."
