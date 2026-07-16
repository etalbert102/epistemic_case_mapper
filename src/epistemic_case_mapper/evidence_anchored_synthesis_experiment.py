from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_markdown_quality import repair_markdown_structure
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_ready_presentation import (
    build_citation_trace_markdown,
    run_memo_ready_presentation_normalization,
)
from epistemic_case_mapper.map_briefing_memo_ready_prompt import build_memo_ready_section_synthesis_plan
from epistemic_case_mapper.map_briefing_memo_ready_section_notes import render_memo_ready_section_markdown_notes
from epistemic_case_mapper.map_briefing_memo_ready_section_synthesis import _extract_section_markdown
from epistemic_case_mapper.model_backends import ModelBackendResult, model_parallelism, run_model_backend, run_parallel


ModelRunner = Callable[..., ModelBackendResult]
EVIDENCE_TAG_RE = re.compile(r"\{E:([A-Za-z0-9_.:-]+)\}")
BRACE_TAG_RE = re.compile(r"\{([^{}\n]{1,240})\}")
EVIDENCE_ANCHORED_SYNTHESIS_ENV = "ECM_EVIDENCE_ANCHORED_SYNTHESIS"


def evidence_anchored_synthesis_enabled() -> bool:
    return os.environ.get(EVIDENCE_ANCHORED_SYNTHESIS_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def run_evidence_anchored_memo_ready_synthesis(
    memo_ready_packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    result = run_evidence_anchored_synthesis_experiment(
        memo_ready_packet,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        baseline_memo="",
        output_dir=None,
        normalize_presentation=False,
        run_model=run_model,
    )
    from epistemic_case_mapper.map_briefing_memo_ready_finalization import build_decision_usefulness_retention_report

    reconciliation = _dict(result.get("reconciliation_report"))
    retention = _dict(result.get("retention_report"))
    section_reports = _list(result.get("section_reports"))
    failed_sections = [row for row in section_reports if isinstance(row, dict) and row.get("accepted") is False and not row.get("markdown")]
    warning_issues = []
    if reconciliation.get("missing_required_evidence_ids"):
        warning_issues.append("evidence_anchor_missing_required_ids")
    if reconciliation.get("unknown_evidence_ids"):
        warning_issues.append("evidence_anchor_unknown_ids")
    if reconciliation.get("quantity_warning_count"):
        warning_issues.append("evidence_anchor_quantity_warnings")
    if failed_sections:
        warning_issues.append("evidence_anchor_section_generation_failed")
    status = "accepted"
    if failed_sections:
        status = "section_synthesis_failed"
    elif warning_issues:
        status = "accepted_with_evidence_anchor_warnings"
    decision_usefulness_retention = build_decision_usefulness_retention_report(str(result.get("memo") or ""), memo_ready_packet)
    report = {
        **_dict(result.get("report")),
        "schema_id": "memo_ready_packet_synthesis_report_v1",
        "anchored_synthesis_schema_id": _dict(result.get("report")).get("schema_id"),
        "status": status,
        "accepted": not failed_sections,
        "synthesis_mode": "evidence_anchored_section_synthesis",
        "live_enrichment_required": True,
        "used_default_path": False,
        "retention_status": retention.get("status"),
        "missing_mandatory_count": retention.get("missing_mandatory_count", 0),
        "missing_quantity_count": retention.get("missing_quantity_count", 0),
        "unresolved_warning_count": retention.get("unresolved_warning_count", 0),
        "source_binding_report": retention.get("source_binding_report", {}),
        "source_binding_warning_count": retention.get("source_binding_warning_count", 0),
        "decision_usefulness_retention_report": decision_usefulness_retention,
        "evidence_reconciliation_report": reconciliation,
        "evidence_expression_contract_count": len(_list(result.get("contracts"))),
        "evidence_trace_count": len(_list(result.get("evidence_trace"))),
        "issues": warning_issues,
    }
    return {
        "memo": result.get("memo", ""),
        "prompt": result.get("prompt", ""),
        "raw": result.get("tagged_memo", ""),
        "report": report,
        "evidence_expression_contracts": result.get("contracts", []),
        "evidence_trace": result.get("evidence_trace", []),
        "evidence_reconciliation_report": reconciliation,
        "evidence_anchored_section_reports": result.get("section_reports", []),
    }


def run_evidence_anchored_synthesis_experiment(
    memo_ready_packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    baseline_memo: str = "",
    output_dir: Path | None = None,
    normalize_presentation: bool = True,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_memo_ready_finalization import build_memo_ready_packet_retention_report

    contracts = build_evidence_expression_contracts(memo_ready_packet)
    section_plan = build_memo_ready_section_synthesis_plan(memo_ready_packet)
    sections = build_experimental_tagged_sections(section_plan, contracts)
    known_evidence_ids = {str(row.get("evidence_id") or "") for row in contracts}
    reports = run_parallel(
        sections,
        lambda section: _run_experimental_section(
            section,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            known_evidence_ids=known_evidence_ids,
            run_model=run_model,
        ),
        max_workers=model_parallelism(backend),
    )
    tagged_memo = _assemble_tagged_memo(section_plan, reports)
    rendered = render_evidence_tagged_memo(tagged_memo, contracts)
    if normalize_presentation:
        presentation = run_memo_ready_presentation_normalization(rendered["memo"], memo_ready_packet, citation_trace_href="CITATION_TRACE.md")
        final_memo = presentation["memo"]
    else:
        presentation = {"memo": rendered["memo"], "report": {"status": "skipped_for_pipeline_presentation_stage"}}
        final_memo = rendered["memo"]
    retention = build_memo_ready_packet_retention_report(final_memo, memo_ready_packet)
    reconciliation = build_experimental_reconciliation_report(tagged_memo, final_memo, contracts)
    comparison = build_experimental_comparison_report(
        baseline_memo=baseline_memo,
        experimental_memo=final_memo,
        packet=memo_ready_packet,
        retention=retention,
        reconciliation=reconciliation,
    )
    report = {
        "schema_id": "evidence_anchored_synthesis_experiment_report_v1",
        "status": "accepted" if all(row.get("accepted") for row in reports) else "section_warnings",
        "section_count": len(reports),
        "accepted_section_count": sum(1 for row in reports if row.get("accepted")),
        "contract_count": len(contracts),
        "required_contract_count": sum(1 for row in contracts if row.get("required")),
        "reconciliation_status": reconciliation.get("status"),
        "retention_status": retention.get("status"),
        "missing_mandatory_count": retention.get("missing_mandatory_count", 0),
        "missing_quantity_count": retention.get("missing_quantity_count", 0),
        "source_binding_warning_count": retention.get("source_binding_warning_count", 0),
        "section_reports": [_public_section_report(row) for row in reports],
        "presentation_report": presentation.get("report", {}),
        "comparison_report": comparison,
    }
    result = {
        "contracts": contracts,
        "sections": sections,
        "section_reports": reports,
        "tagged_memo": tagged_memo,
        "prompt": "\n\n--- SECTION PROMPT ---\n\n".join(str(row.get("prompt") or "") for row in sections),
        "rendered_memo_before_presentation": rendered["memo"],
        "evidence_trace": rendered["trace"],
        "memo": final_memo,
        "retention_report": retention,
        "reconciliation_report": reconciliation,
        "comparison_report": comparison,
        "report": report,
    }
    if output_dir is not None:
        write_experiment_artifacts(result, output_dir=output_dir, packet=memo_ready_packet)
    return result


def build_evidence_expression_contracts(packet: dict[str, Any]) -> list[dict[str, Any]]:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    obligations_by_item = _obligations_by_item(canonical)
    source_ids_by_label = _source_ids_by_label(packet)
    language_by_item = {
        str(row.get("item_id") or ""): row
        for row in _list(canonical.get("evidence_language_contracts"))
        if isinstance(row, dict) and row.get("item_id")
    }
    contracts = []
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("item_id") or "").strip()
        if not evidence_id:
            continue
        obligation = obligations_by_item.get(evidence_id, {})
        language = language_by_item.get(evidence_id, {})
        sources = _dedupe([
            *_string_list(item.get("source_ids")),
            *_string_list(obligation.get("source_ids")),
            *_string_list(language.get("source_ids")),
            *_source_ids_from_labels(item, source_ids_by_label),
        ])
        quantities = _quantity_contracts(_list(item.get("quantities")) or _list(obligation.get("quantities")))
        role = str(item.get("role") or obligation.get("role") or "")
        contracts.append(
            _drop_empty(
                {
                    "schema_id": "experimental_evidence_expression_contract_v1",
                    "evidence_id": evidence_id,
                    "required": _contract_required(item, obligation, role=role, quantities=quantities),
                    "primary_section": _primary_section_for_role(role),
                    "claim": item.get("reader_claim") or item.get("claim") or obligation.get("statement"),
                    "role": role,
                    "source_ids": sources,
                    "source_labels": item.get("source_labels") or ([item.get("source_label")] if item.get("source_label") else None),
                    "required_quantity_atoms": quantities,
                    "population_scope": item.get("caveat") or item.get("applicability_scope"),
                    "required_caveat": item.get("caveat"),
                    "decision_relevance": item.get("decision_relevance"),
                    "allowed_language": _string_list(_dict(item.get("allowed_wording")).get("allowed_language")) or _string_list(language.get("allowed_language")),
                    "must_qualify_with": _string_list(_dict(item.get("allowed_wording")).get("must_qualify_with")) or _string_list(language.get("must_qualify_with")),
                    "must_not_imply": _dedupe([
                        *_string_list(_dict(item.get("allowed_wording")).get("avoid_language")),
                        *_string_list(language.get("avoid_language")),
                    ]),
                }
            )
        )
    return contracts


def build_experimental_tagged_sections(
    section_plan: dict[str, Any],
    contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sections = []
    for section in _list(section_plan.get("sections")):
        if not isinstance(section, dict):
            continue
        packet = _dict(section.get("packet"))
        heading = str(section.get("heading") or packet.get("heading") or "").strip()
        section_contracts = _contracts_for_section(packet, heading, contracts)
        prompt = build_evidence_anchored_section_prompt(
            packet,
            known_source_ids=_string_list(section_plan.get("known_source_ids")),
            contracts=section_contracts,
        )
        sections.append(
            {
                "section_id": section.get("section_id"),
                "heading": heading,
                "packet": packet,
                "contracts": section_contracts,
                "prompt": prompt,
            }
        )
    return sections


def build_evidence_anchored_section_prompt(
    section_packet: dict[str, Any],
    *,
    known_source_ids: list[str],
    contracts: list[dict[str, Any]],
) -> str:
    heading = str(section_packet.get("heading") or "").strip()
    return (
        "You are writing one section of a source-grounded decision memo from markdown analyst notes.\n"
        "Write polished decision-ready prose. Use evidence tags as invisible trace anchors for later rendering.\n\n"
        "Output rules:\n"
        f"- Output must start exactly with: ## {heading}\n"
        "- After each load-bearing evidence sentence, add one or more evidence tags like {E:evidence_id}.\n"
        "- Use only evidence IDs listed in Evidence expression contracts.\n"
        "- Do not add bracketed source citations; the renderer will convert evidence tags into source citations.\n"
        "- Use parentheses, not square brackets, for confidence intervals, uncertainty ranges, and numeric ranges.\n"
        "- Preserve the required quantities, scope, direction, and caveats in the evidence contracts.\n"
        "- Write natural prose; tags are trace markers, not visible reader citations.\n\n"
        f"{render_memo_ready_section_markdown_notes(section_packet, known_source_ids=known_source_ids)}\n\n"
        "### Evidence expression contracts\n"
        f"{json.dumps([_compact_contract_for_prompt(row) for row in contracts], indent=2, ensure_ascii=False)}\n\n"
        "Now write the section as natural Markdown prose with evidence tags.\n"
    )


def render_evidence_tagged_memo(tagged_memo: str, contracts: list[dict[str, Any]]) -> dict[str, Any]:
    contracts_by_id = _contracts_by_evidence_alias(contracts)
    known_source_ids = {
        source_id
        for contract in contracts
        for source_id in _string_list(contract.get("source_ids"))
    }
    trace = []

    def replace(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        evidence_ids = _evidence_ids_from_brace_content(content, contracts_by_id)
        if evidence_ids:
            source_ids = []
            for evidence_id in evidence_ids:
                contract = contracts_by_id.get(evidence_id, {})
                row_source_ids = _string_list(contract.get("source_ids"))
                source_ids.extend(row_source_ids)
                trace.append(
                    {
                        "evidence_id": evidence_id,
                        "source_ids": row_source_ids,
                        "claim": contract.get("claim"),
                        "required_quantity_atoms": contract.get("required_quantity_atoms", []),
                        "tag": match.group(0),
                    }
                )
            source_ids = _dedupe(source_ids)
            return f"[{', '.join(source_ids)}]" if source_ids else ""
        source_ids = _source_ids_from_brace_content(content, known_source_ids)
        if source_ids:
            return f"[{', '.join(source_ids)}]"
        return match.group(0)

    memo = BRACE_TAG_RE.sub(replace, tagged_memo)
    memo = re.sub(r"[ \t]+(\n)", r"\1", memo)
    memo = re.sub(r"\s+\.", ".", memo)
    return {"memo": repair_markdown_structure(memo), "trace": trace}


def build_experimental_reconciliation_report(
    tagged_memo: str,
    rendered_memo: str,
    contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    used_ids = set(_evidence_ids_in_text(tagged_memo, contracts))
    known_ids = {str(row.get("evidence_id") or "") for row in contracts}
    required = [row for row in contracts if row.get("required")]
    missing_required = [row.get("evidence_id") for row in required if row.get("evidence_id") not in used_ids]
    unknown = sorted(used_ids - known_ids)
    quantity_warnings = _quantity_warnings(tagged_memo, contracts)
    untagged = _untagged_high_risk_sentences(tagged_memo)
    status = "ready"
    if missing_required or unknown:
        status = "warning"
    return {
        "schema_id": "experimental_evidence_reconciliation_report_v1",
        "status": status,
        "known_evidence_id_count": len(known_ids),
        "used_evidence_id_count": len(used_ids & known_ids),
        "required_evidence_id_count": len(required),
        "missing_required_evidence_ids": missing_required,
        "unknown_evidence_ids": unknown,
        "quantity_warning_count": len(quantity_warnings),
        "quantity_warnings": quantity_warnings,
        "untagged_high_risk_sentence_count": len(untagged),
        "untagged_high_risk_sentences": untagged[:20],
        "raw_tag_count": len(_evidence_ids_in_text(tagged_memo, contracts)),
        "rendered_raw_tag_count": len(_evidence_ids_in_text(rendered_memo, contracts)),
    }


def build_experimental_comparison_report(
    *,
    baseline_memo: str,
    experimental_memo: str,
    packet: dict[str, Any],
    retention: dict[str, Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_memo_ready_finalization import build_memo_ready_packet_retention_report

    baseline_retention = build_memo_ready_packet_retention_report(baseline_memo, packet) if baseline_memo.strip() else {}
    return {
        "schema_id": "experimental_evidence_anchored_comparison_report_v1",
        "baseline_chars": len(baseline_memo),
        "experimental_chars": len(experimental_memo),
        "baseline_citation_count": _citation_count(baseline_memo),
        "experimental_citation_count": _citation_count(experimental_memo),
        "baseline_repetition_score": _repetition_score(baseline_memo),
        "experimental_repetition_score": _repetition_score(experimental_memo),
        "baseline_retention": _retention_summary(baseline_retention),
        "experimental_retention": _retention_summary(retention),
        "reconciliation": {
            "status": reconciliation.get("status"),
            "missing_required_evidence_ids": reconciliation.get("missing_required_evidence_ids", []),
            "unknown_evidence_ids": reconciliation.get("unknown_evidence_ids", []),
            "untagged_high_risk_sentence_count": reconciliation.get("untagged_high_risk_sentence_count", 0),
        },
    }


def write_experiment_artifacts(result: dict[str, Any], *, output_dir: Path, packet: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "experimental_evidence_expression_contracts.json", result["contracts"])
    _write_json(output_dir / "experimental_evidence_trace.json", result["evidence_trace"])
    _write_json(output_dir / "experimental_reconciliation_report.json", result["reconciliation_report"])
    _write_json(output_dir / "experimental_comparison_report.json", result["comparison_report"])
    _write_json(output_dir / "experimental_report.json", result["report"])
    _write_json(output_dir / "experimental_section_reports.json", result["section_reports"])
    (output_dir / "experimental_tagged_section_prompts.txt").write_text(
        "\n\n--- SECTION PROMPT ---\n\n".join(str(row.get("prompt") or "") for row in result["sections"]),
        encoding="utf-8",
    )
    (output_dir / "experimental_tagged_sections_raw.md").write_text(str(result["tagged_memo"]), encoding="utf-8")
    (output_dir / "experimental_rendered_memo.md").write_text(str(result["memo"]), encoding="utf-8")
    (output_dir / "BRIEFING.md").write_text(str(result["memo"]), encoding="utf-8")
    (output_dir / "CITATION_TRACE.md").write_text(build_citation_trace_markdown(str(result["memo"]), packet), encoding="utf-8")
    _write_json(output_dir / "retention_report.json", result["retention_report"])


def _run_experimental_section(
    section: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    known_evidence_ids: set[str],
    run_model: ModelRunner,
) -> dict[str, Any]:
    heading = str(section.get("heading") or "").strip()
    prompt = str(section.get("prompt") or "")
    try:
        result = run_model(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            num_predict=4096,
            json_mode=False,
        )
    except RuntimeError as exc:
        return {"section_id": section.get("section_id"), "heading": heading, "accepted": False, "issues": ["backend_error", str(exc)], "prompt": prompt, "raw": "", "markdown": ""}
    markdown = _extract_section_markdown(result.text, heading)
    used_ids = set(_evidence_ids_in_text(markdown, section.get("contracts", [])))
    unknown = sorted(used_ids - known_evidence_ids)
    missing_heading = not (markdown.lstrip().startswith(f"## {heading}\n") or markdown.strip() == f"## {heading}")
    issues = [
        *(["missing_exact_heading"] if missing_heading else []),
        *([f"unknown_evidence_ids:{', '.join(unknown)}"] if unknown else []),
    ]
    return {
        "section_id": section.get("section_id"),
        "heading": heading,
        "accepted": not issues,
        "issues": issues,
        "unknown_evidence_ids": unknown,
        "used_evidence_ids": sorted(used_ids & known_evidence_ids),
        "prompt": prompt,
        "raw": result.text,
        "markdown": markdown,
        "char_count": len(markdown),
        "attempts": result.attempts,
    }


def _assemble_tagged_memo(section_plan: dict[str, Any], reports: list[dict[str, Any]]) -> str:
    title = str(section_plan.get("title") or "Decision Memo").strip()
    question = str(section_plan.get("decision_question") or "").strip()
    bottom_line = str(section_plan.get("bottom_line") or "").strip()
    lines = [f"# Decision Memo: {title}" if title and title != "Decision Memo" else "# Decision Memo", ""]
    if question:
        lines.extend([f"**Decision Question:** {question}", ""])
    if bottom_line:
        lines.extend([f"**Bottom Line:** {bottom_line}", ""])
    for row in reports:
        markdown = str(row.get("markdown") or "").strip()
        if markdown:
            lines.extend([markdown, ""])
    return repair_markdown_structure("\n".join(lines).strip() + "\n")


def _contracts_for_section(section_packet: dict[str, Any], heading: str, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section_id = str(section_packet.get("section_id") or "").strip()
    local_ids = {
        str(row.get("item_id") or row.get("requirement_id") or "")
        for key in ("evidence_context", "section_retention_requirements", "source_bound_evidence_atoms")
        for row in _list(section_packet.get(key))
        if isinstance(row, dict)
    }
    selected = [
        row
        for row in contracts
        if row.get("evidence_id") in local_ids
        or row.get("primary_section") == section_id
        or _heading_matches_section(str(row.get("primary_section") or ""), heading)
    ]
    if selected:
        return selected[:18]
    return [row for row in contracts if row.get("required")][:12]


def _obligations_by_item(canonical: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_item = {}
    for row in _list(canonical.get("mandatory_retention_checklist")):
        if not isinstance(row, dict):
            continue
        for item_id in _string_list(row.get("evidence_item_ids")):
            by_item.setdefault(item_id, row)
    return by_item


def _source_ids_by_label(packet: dict[str, Any]) -> dict[str, str]:
    rows = _list(packet.get("source_trail"))
    mapping = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or row.get("citation_key") or "").strip()
        if not source_id:
            continue
        for value in (
            row.get("source_label"),
            row.get("display_label"),
            row.get("source_slug"),
            row.get("original_source_id"),
            row.get("citation_key"),
        ):
            key = _label_key(value)
            if key:
                mapping[key] = source_id
        for alias in _string_list(row.get("source_aliases")):
            key = _label_key(alias)
            if key:
                mapping[key] = source_id
    return mapping


def _source_ids_from_labels(item: dict[str, Any], source_ids_by_label: dict[str, str]) -> list[str]:
    labels = [*_string_list(item.get("source_labels")), *_string_list(item.get("source_label"))]
    ids = []
    for label in labels:
        source_id = source_ids_by_label.get(_label_key(label))
        if source_id:
            ids.append(source_id)
    return _dedupe(ids)


def _label_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _contract_required(item: dict[str, Any], obligation: dict[str, Any], *, role: str, quantities: list[dict[str, Any]]) -> bool:
    role_text = role.lower()
    return (
        bool(item.get("must_use"))
        or str(item.get("obligation_level") or "") == "must_include"
        or bool(obligation)
        or role_text in {"strongest_counterweight", "scope_boundary", "quantitative_anchor", "decision_crux"}
    )


def _quantity_contracts(rows: list[Any]) -> list[dict[str, Any]]:
    quantities = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = str(row.get("value") or "").strip()
        if not value:
            continue
        quantities.append(
            _drop_empty(
                {
                    "value": value,
                    "interpretation": row.get("interpretation"),
                    "quantity_role": row.get("quantity_role"),
                    "source_ids": row.get("source_ids"),
                }
            )
        )
    return quantities


def _quantity_warnings(tagged_memo: str, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    for contract in contracts:
        if not contract.get("required"):
            continue
        span = _span_for_evidence_id(tagged_memo, str(contract.get("evidence_id") or ""))
        if not span:
            continue
        for quantity in _list(contract.get("required_quantity_atoms")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if value and not _quantity_surface_present(value, span):
                warnings.append({"evidence_id": contract.get("evidence_id"), "missing_quantity_near_tag": value, "span": _short_text(span, 240)})
    return warnings


def _span_for_evidence_id(text: str, evidence_id: str) -> str:
    if not evidence_id:
        return ""
    pattern = re.compile(rf"[^.\n]*(?:\{{E:{re.escape(evidence_id)}\}}|\{{[^}}\n]*\b{re.escape(evidence_id)}\b[^}}\n]*\}})[^.\n]*(?:\.|\n|$)")
    match = pattern.search(text)
    return match.group(0).strip() if match else ""


def _quantity_surface_present(value: str, text: str) -> bool:
    value_text = str(value or "").lower()
    text_norm = str(text or "").lower()
    if value_text in text_norm:
        return True
    numbers = re.findall(r"\d+(?:\.\d+)?", value_text)
    return bool(numbers) and all(number in text_norm for number in numbers)


def _untagged_high_risk_sentences(tagged_memo: str) -> list[str]:
    rows = []
    for sentence in _sentences_without_sources(tagged_memo):
        if _evidence_ids_in_text(sentence, []):
            continue
        lowered = sentence.lower()
        if re.search(r"\d", sentence) or any(token in lowered for token in ("associated", "risk", "increased", "reduced", "should", "must", "recommend", "causes", "proves")):
            rows.append(_short_text(BRACE_TAG_RE.sub("", sentence).strip(), 300))
    return rows


def _sentences_without_sources(memo: str) -> list[str]:
    body = re.split(r"(?m)^## Sources\s*$", memo)[0]
    body = "\n".join(line for line in body.splitlines() if not line.startswith("#") and not line.startswith("**Decision"))
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if len(part.strip()) > 30]


def _evidence_ids_in_text(text: str, contracts: list[dict[str, Any]]) -> list[str]:
    contracts_by_id = _contracts_by_evidence_alias(contracts)
    if not contracts_by_id:
        candidates = []
        for content in BRACE_TAG_RE.findall(text or ""):
            candidates.extend(_brace_tokens(content))
        return [token.removeprefix("E:") for token in candidates if token.startswith("E:") or token.startswith("decision_writer_item_")]
    found = []
    for content in BRACE_TAG_RE.findall(text or ""):
        found.extend(_evidence_ids_from_brace_content(content.strip(), contracts_by_id))
    return _dedupe(found)


def _evidence_ids_from_brace_content(content: str, contracts_by_id: dict[str, dict[str, Any]]) -> list[str]:
    ids = []
    for token in _brace_tokens(content):
        candidate = token.removeprefix("E:")
        contract = contracts_by_id.get(candidate)
        if contract:
            ids.append(str(contract.get("evidence_id") or candidate))
    return _dedupe(ids)


def _contracts_by_evidence_alias(contracts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in contracts:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        for alias in _evidence_id_aliases(evidence_id):
            by_id.setdefault(alias, row)
    return by_id


def _evidence_id_aliases(evidence_id: str) -> list[str]:
    aliases = [evidence_id]
    match = re.match(r"^(.*?)(\d+)$", evidence_id)
    if match:
        prefix, digits = match.groups()
        unpadded = str(int(digits)) if digits.strip("0") else "0"
        aliases.append(f"{prefix}{unpadded}")
    return _dedupe(aliases)


def _source_ids_from_brace_content(content: str, known_source_ids: set[str]) -> list[str]:
    tokens = _brace_tokens(content)
    if tokens and all(token in known_source_ids for token in tokens):
        return _dedupe(tokens)
    return []


def _brace_tokens(content: str) -> list[str]:
    return [token.strip() for token in re.split(r"[,;]", str(content or "")) if token.strip()]


def _primary_section_for_role(role: str) -> str:
    text = role.lower()
    if any(token in text for token in ("counter", "scope", "boundary", "crux", "limit")):
        return "counterweights"
    if any(token in text for token in ("practical", "context")):
        return "practical_implication"
    return "answer_evidence"


def _heading_matches_section(section_id: str, heading: str) -> bool:
    lowered = heading.lower()
    return (
        (section_id == "answer_evidence" and "best current" in lowered)
        or (section_id == "counterweights" and ("change" in lowered or "bound" in lowered))
        or (section_id == "practical_implication" and "practical" in lowered)
        or (section_id == "source_weighting" and "weight" in lowered)
    )


def _compact_contract_for_prompt(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "evidence_id": row.get("evidence_id"),
            "claim": row.get("claim"),
            "required": row.get("required"),
            "source_ids": row.get("source_ids"),
            "quantities": row.get("required_quantity_atoms"),
            "scope": row.get("population_scope"),
            "caveat": row.get("required_caveat"),
            "must_qualify_with": row.get("must_qualify_with"),
            "must_not_imply": row.get("must_not_imply"),
        }
    )


def _public_section_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "section_id": row.get("section_id"),
        "heading": row.get("heading"),
        "accepted": bool(row.get("accepted")),
        "issues": _list(row.get("issues")),
        "unknown_evidence_ids": _list(row.get("unknown_evidence_ids")),
        "used_evidence_id_count": len(_list(row.get("used_evidence_ids"))),
        "char_count": row.get("char_count", 0),
        "attempts": row.get("attempts", 0),
    }


def _retention_summary(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {}
    return {
        "status": report.get("status"),
        "missing_mandatory_count": report.get("missing_mandatory_count", 0),
        "missing_quantity_count": report.get("missing_quantity_count", 0),
        "source_binding_warning_count": report.get("source_binding_warning_count", 0),
        "unresolved_warning_count": report.get("unresolved_warning_count", 0),
    }


def _citation_count(memo: str) -> int:
    return len(re.findall(r"\[[^\]]+\]", memo or ""))


def _repetition_score(memo: str) -> int:
    words = re.findall(r"[a-z][a-z0-9'-]+", (memo or "").lower())
    grams = [" ".join(words[index : index + 5]) for index in range(max(0, len(words) - 4))]
    counts: dict[str, int] = {}
    for gram in grams:
        counts[gram] = counts.get(gram, 0) + 1
    return sum(count - 1 for count in counts.values() if count > 1)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
