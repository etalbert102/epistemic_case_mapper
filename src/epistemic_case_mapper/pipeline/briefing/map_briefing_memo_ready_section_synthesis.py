from __future__ import annotations

import difflib
import json
import re
from typing import Any, Callable

from epistemic_case_mapper.pipeline.briefing.map_briefing_markdown_quality import markdown_structure_issues, repair_markdown_structure
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_output_limits import memo_ready_section_num_predict
from epistemic_case_mapper.pipeline.briefing.map_briefing_priority_quantity_contracts import (
    build_priority_quantity_contract_coverage_report,
    build_priority_quantity_contracts,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_entailment import (
    collect_packet_source_evidence_by_source,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_evidence_anchoring import (
    build_evidence_expression_contracts,
    build_evidence_reconciliation_report,
    build_evidence_tagged_section_prompt,
    contracts_for_section,
    evidence_ids_in_text,
    render_evidence_tagged_memo,
    unknown_evidence_ids_in_text,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_synthesis_logic import (
    repair_section_synthesis_logic as _repair_section_synthesis_logic,
    section_synthesis_logic_issues as _section_synthesis_logic_issues,
)
from epistemic_case_mapper.model_stage_retry import model_stage_attempts
from epistemic_case_mapper.model_backends import ModelBackendResult, model_parallelism, run_model_backend, run_parallel


ModelRunner = Callable[..., ModelBackendResult]


def run_parallel_memo_ready_section_generation(
    section_plan: dict[str, Any],
    *,
    memo_ready_packet: dict[str, Any] | None = None,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    whole_prompt: str,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    evidence_contracts = build_evidence_expression_contracts(memo_ready_packet or {})
    sections = _prepare_sections(section_plan, memo_ready_packet or {}, evidence_contracts)
    if _uses_section_owned_evidence_contracts(section_plan, sections):
        evidence_contracts = _section_owned_evidence_contracts(sections)
    known_source_ids = set(_string_list(section_plan.get("known_source_ids")))
    known_source_aliases = _source_alias_map(section_plan.get("known_source_aliases"))
    known_evidence_ids = _known_evidence_id_aliases(evidence_contracts)
    num_predict = memo_ready_section_num_predict()
    report = {
        "schema_id": "memo_ready_section_generation_report_v1",
        "status": "not_run",
        "accepted": False,
        "synthesis_mode": "unified_section_synthesis",
        "parallelism": min(model_parallelism(backend), len(sections)) if sections else 0,
        "num_predict": num_predict,
        "section_count": len(sections),
        "evidence_expression_contract_count": len(evidence_contracts),
        "issues": [],
    }

    def run_section(section: dict[str, Any]) -> dict[str, Any]:
        return _run_section(
            section,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            num_predict=num_predict,
            known_source_ids=known_source_ids,
            known_source_aliases=known_source_aliases,
            known_evidence_ids=known_evidence_ids,
            run_model=run_model,
        )

    section_reports = run_parallel(sections, run_section, max_workers=model_parallelism(backend))
    blocking_failed = [row for row in section_reports if _section_has_blocking_failure(row)]
    combined_prompt = _combined_section_prompts(sections, whole_prompt=whole_prompt)
    combined_raw = "\n\n".join(
        f"<!-- {row.get('heading')} raw -->\n{row.get('raw', '')}" for row in section_reports
    )
    if blocking_failed:
        report.update(
            {
                "status": "section_synthesis_failed",
                "accepted": False,
                "section_reports": [_public_section_report(row) for row in section_reports],
                "issues": ["one_or_more_sections_failed_validation"],
            }
        )
        return {"memo": "", "prompt": combined_prompt, "raw": combined_raw, "report": report}
    section_warning_issues = _section_warning_issues(section_reports)
    report.update(
        {
            "status": "accepted_with_section_warnings" if section_warning_issues else "accepted",
            "accepted": not section_warning_issues,
            "section_reports": [_public_section_report(row) for row in section_reports],
            "issues": section_warning_issues,
        }
    )
    tagged_memo = _assemble_section_synthesis_memo(section_plan, section_reports)
    rendered = (
        render_evidence_tagged_memo(
            tagged_memo,
            evidence_contracts,
            source_evidence_by_source=collect_packet_source_evidence_by_source(memo_ready_packet or {}),
        )
        if evidence_contracts
        else {"memo": tagged_memo, "trace": []}
    )
    reconciliation = (
        build_evidence_reconciliation_report(tagged_memo, rendered["memo"], evidence_contracts)
        if evidence_contracts
        else {"schema_id": "evidence_reconciliation_report_v1", "status": "not_available"}
    )
    priority_quantity_contracts = (
        _priority_quantity_contracts_from_evidence_contracts(evidence_contracts)
        if _uses_section_owned_evidence_contracts(section_plan, sections)
        else build_priority_quantity_contracts(memo_ready_packet or {})
    )
    priority_quantity_coverage = build_priority_quantity_contract_coverage_report(rendered["memo"], priority_quantity_contracts)
    if reconciliation.get("status") == "warning":
        report["status"] = "accepted_with_evidence_tag_warnings"
        report["issues"] = ["evidence_reconciliation_warnings"]
    report.update(
        {
            "evidence_reconciliation_report": reconciliation,
            "priority_quantity_contracts": priority_quantity_contracts,
            "priority_quantity_contract_coverage_report": priority_quantity_coverage,
            "evidence_trace_count": len(_list(rendered.get("trace"))),
        }
    )
    return {
        "memo": rendered["memo"],
        "prompt": combined_prompt,
        "raw": tagged_memo if evidence_contracts else combined_raw,
        "report": report,
        "tagged_memo": tagged_memo,
        "section_raw": combined_raw,
        "evidence_expression_contracts": evidence_contracts,
        "priority_quantity_contracts": priority_quantity_contracts,
        "priority_quantity_contract_coverage_report": priority_quantity_coverage,
        "evidence_trace": rendered.get("trace", []),
        "evidence_reconciliation_report": reconciliation,
        "evidence_tag_section_reports": section_reports,
    }


def _run_section(
    section: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    num_predict: int,
    known_source_ids: set[str],
    known_source_aliases: dict[str, str],
    known_evidence_ids: set[str],
    run_model: ModelRunner,
) -> dict[str, Any]:
    heading = str(section.get("heading") or "").strip()
    prompt = str(section.get("prompt") or "")
    active_prompt = prompt
    citation_mode = str(section.get("citation_mode") or "source_ids")
    contracts = _list(section.get("contracts"))
    section_report = {
        "section_id": section.get("section_id"),
        "heading": heading,
        "citation_mode": citation_mode,
        "accepted": False,
        "issues": [],
        "unknown_source_ids": [],
        "unknown_evidence_ids": [],
        "used_evidence_ids": [],
        "raw": "",
        "prompt": prompt,
        "markdown": "",
    }
    attempts = model_stage_attempts()
    raw = ""
    markdown = ""
    unknown: list[str] = []
    unknown_evidence: list[str] = []
    used_evidence: list[str] = []
    issues: list[str] = []
    reconciliation: dict[str, Any] = {}
    backend_attempts = 0
    validation_attempt_reports = []
    for attempt in range(1, attempts + 1):
        try:
            result = run_model(
                active_prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                num_predict=num_predict,
                json_mode=False,
            )
        except RuntimeError as exc:
            section_report["issues"] = ["backend_error", str(exc)]
            section_report["validation_attempts"] = attempt
            return section_report
        backend_attempts += int(result.attempts or 1)
        raw = result.text
        markdown = _extract_section_markdown(raw, heading)
        markdown = _normalize_statistical_brackets(markdown)
        packet = section.get("packet") if isinstance(section.get("packet"), dict) else {}
        markdown = _repair_section_synthesis_logic(
            markdown,
            section_id=str(section.get("section_id") or ""),
            contracts=contracts,
            packet=packet,
        )
        unknown = []
        unknown_evidence = []
        used_evidence = []
        reconciliation = {}
        if citation_mode == "evidence_tags":
            used_evidence = evidence_ids_in_text(markdown, contracts)
            unknown_evidence = unknown_evidence_ids_in_text(markdown, contracts, known_source_ids=known_source_ids)
            reconciliation = build_evidence_reconciliation_report(markdown, markdown, contracts, known_source_ids=known_source_ids)
            unknown_evidence = [evidence_id for evidence_id in unknown_evidence if evidence_id not in known_evidence_ids]
            reconciliation = _reconciliation_without_global_known_unknowns(reconciliation, known_evidence_ids)
        elif citation_mode == "none":
            markdown = _strip_uncontracted_citations(markdown)
        else:
            markdown = _normalize_known_source_alias_citations(markdown, known_source_aliases)
            markdown = _repair_near_miss_source_ids(markdown, known_source_ids)
            unknown = _unknown_section_source_ids(markdown, known_source_ids)
        structure_issues = markdown_structure_issues(markdown)
        heading_ok = markdown.lstrip().startswith(f"## {heading}\n") or markdown.strip() == f"## {heading}"
        issues = [
            *(["missing_exact_heading"] if not heading_ok else []),
            *([f"unknown_source_ids:{', '.join(unknown)}"] if unknown else []),
            *([f"unknown_evidence_ids:{', '.join(unknown_evidence)}"] if unknown_evidence else []),
            *_section_reconciliation_issues(reconciliation),
            *_section_synthesis_logic_issues(markdown, section_id=str(section.get("section_id") or ""), contracts=contracts, packet=packet),
            *structure_issues,
        ]
        validation_attempt_reports.append(
            {
                "attempt": attempt,
                "accepted": not issues,
                "issue_count": len(issues),
                "issues": issues[:12],
                "quantity_warning_count": len(_list(reconciliation.get("quantity_warnings"))),
            }
        )
        if not issues:
            break
        if attempt < attempts:
            active_prompt = _section_retry_prompt(
                prompt,
                heading=heading,
                issues=issues,
                reconciliation=reconciliation,
                contracts=contracts,
            )
    section_report.update(
        {
            "accepted": not issues,
            "issues": issues,
            "unknown_source_ids": unknown,
            "unknown_evidence_ids": unknown_evidence,
            "used_evidence_ids": sorted(set(used_evidence) & known_evidence_ids),
            "raw": raw,
            "markdown": markdown,
            "char_count": len(markdown),
            "attempts": backend_attempts,
            "validation_attempts": len(validation_attempt_reports),
            "validation_attempt_reports": validation_attempt_reports,
            "num_predict": num_predict,
            "evidence_reconciliation_report": reconciliation,
        }
    )
    return section_report


def _uses_section_owned_evidence_contracts(
    section_plan: dict[str, Any],
    sections: list[dict[str, Any]],
) -> bool:
    if section_plan.get("evidence_contract_scope") == "section_owned":
        return True
    return any(_dict(section.get("packet")).get("schema_id") == "arm_b_slim_section_packet_v1" for section in sections)


def _section_owned_evidence_contracts(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for section in sections:
        for contract in _list(section.get("contracts")):
            if not isinstance(contract, dict):
                continue
            evidence_id = str(contract.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id in seen:
                continue
            seen.add(evidence_id)
            rows.append(contract)
    return rows


def _priority_quantity_contracts_from_evidence_contracts(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for contract in contracts:
        evidence_id = str(contract.get("evidence_id") or "").strip()
        claim = str(contract.get("claim") or "").strip()
        source_labels = _string_list(contract.get("source_labels"))
        for index, quantity in enumerate(_list(contract.get("required_quantity_atoms")), start=1):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or quantity.get("quantity_text") or "").strip()
            if not evidence_id or not value:
                continue
            rows.append(
                {
                    "contract_id": f"{evidence_id}::{index}",
                    "evidence_id": evidence_id,
                    "quantity_text": value,
                    "decision_role": quantity.get("decision_role") or contract.get("role"),
                    "source_labels": source_labels,
                    "claim": claim,
                    "required_if_claim_used": bool(contract.get("required")),
                    "contract_level": "required_if_related_claim_used",
                }
            )
    return {
        "schema_id": "priority_quantity_contracts_v1",
        "selection_method": "section_owned_evidence_contracts",
        "rule": "When a memo uses the related evidence claim, preserve the quantity with the same decision role.",
        "rows": rows,
    }


def _section_reconciliation_issues(reconciliation: dict[str, Any]) -> list[str]:
    if not reconciliation:
        return []
    issues = []
    missing_required = _string_list(reconciliation.get("missing_required_evidence_ids"))
    unknown = _string_list(reconciliation.get("unknown_evidence_ids"))
    for evidence_id in missing_required:
        issues.append(f"missing_required_evidence:{evidence_id}")
    for evidence_id in unknown:
        issues.append(f"unknown_evidence_id:{evidence_id}")
    for warning in _list(reconciliation.get("quantity_warnings")):
        if not isinstance(warning, dict):
            continue
        evidence_id = str(warning.get("evidence_id") or "").strip()
        value = str(warning.get("missing_quantity_near_tag") or "").strip()
        if evidence_id and value:
            issues.append(f"missing_required_quantity:{evidence_id}:{value}")
    for warning in _list(reconciliation.get("source_mismatch_warnings")):
        if not isinstance(warning, dict):
            continue
        evidence_ids = ", ".join(_string_list(warning.get("evidence_ids")))
        adjacent_sources = ", ".join(_string_list(warning.get("adjacent_source_ids")))
        if evidence_ids and adjacent_sources:
            issues.append(f"source_evidence_mismatch:{evidence_ids}:{adjacent_sources}")
    for warning in _list(reconciliation.get("unsupported_quantity_warnings")):
        if not isinstance(warning, dict):
            continue
        evidence_ids = ", ".join(_string_list(warning.get("evidence_ids")))
        quantities = ", ".join(_string_list(warning.get("unsupported_quantities")))
        if evidence_ids and quantities:
            issues.append(f"unsupported_quantity_near_tag:{evidence_ids}:{quantities}")
    for warning in _list(reconciliation.get("untagged_unsupported_quantity_warnings")):
        if not isinstance(warning, dict):
            continue
        quantities = ", ".join(_string_list(warning.get("unsupported_quantities")))
        if quantities:
            issues.append(f"unsupported_untagged_quantity:{quantities}")
    return issues


def _known_evidence_id_aliases(contracts: list[dict[str, Any]]) -> set[str]:
    aliases: set[str] = set()
    for row in contracts:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        aliases.add(evidence_id)
        match = re.match(r"^(.*?)(\d+)$", evidence_id)
        if match:
            prefix, digits = match.groups()
            unpadded = str(int(digits)) if digits.strip("0") else "0"
            aliases.add(f"{prefix}{unpadded}")
    return aliases


def _reconciliation_without_global_known_unknowns(
    reconciliation: dict[str, Any],
    known_evidence_ids: set[str],
) -> dict[str, Any]:
    if not reconciliation:
        return reconciliation
    unknown = [
        evidence_id
        for evidence_id in _string_list(reconciliation.get("unknown_evidence_ids"))
        if evidence_id not in known_evidence_ids
    ]
    if len(unknown) == len(_string_list(reconciliation.get("unknown_evidence_ids"))):
        return reconciliation
    updated = dict(reconciliation)
    updated["unknown_evidence_ids"] = unknown
    if not unknown and updated.get("status") == "warning":
        residual = [
            *_string_list(updated.get("missing_required_evidence_ids")),
            *_list(updated.get("quantity_warnings")),
            *_list(updated.get("source_mismatch_warnings")),
            *_list(updated.get("unsupported_quantity_warnings")),
            *_list(updated.get("untagged_unsupported_quantity_warnings")),
        ]
        updated["status"] = "warning" if residual else "ready"
    return updated


def _section_has_blocking_failure(section_report: dict[str, Any]) -> bool:
    if section_report.get("accepted"):
        return False
    issues = [str(issue or "") for issue in _list(section_report.get("issues"))]
    if not str(section_report.get("markdown") or "").strip():
        return True
    return any(
        issue == "backend_error"
        or issue == "missing_exact_heading"
        or issue.startswith("unknown_source_ids:")
        or issue.startswith("unknown_evidence_ids:")
        or issue.startswith("unknown_evidence_id:")
        or issue == "missing_conflict_reconciliation"
        or issue == "unreconciled_dose_thresholds"
        or issue == "unsupported_strength_from_indirect_evidence"
        or issue.startswith("unsupported_temporal_qualifier:")
        for issue in issues
    )


def _section_warning_issues(section_reports: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for row in section_reports:
        if row.get("accepted"):
            continue
        section_id = str(row.get("section_id") or row.get("heading") or "section").strip()
        for issue in _list(row.get("issues")):
            issue_text = str(issue or "").strip()
            if issue_text:
                warnings.append(f"{section_id}:{issue_text}")
    return _dedupe(warnings)


def _section_retry_prompt(
    base_prompt: str,
    *,
    heading: str,
    issues: list[str],
    reconciliation: dict[str, Any],
    contracts: list[dict[str, Any]],
) -> str:
    repair_packet = {
        "task": "Revise this section so it satisfies its evidence-expression contract.",
        "heading": heading,
        "issues_to_fix": issues[:16],
        "missing_required_evidence_ids": reconciliation.get("missing_required_evidence_ids", []),
        "missing_required_contracts": _missing_contracts_for_retry(
            _string_list(reconciliation.get("missing_required_evidence_ids")),
            contracts,
        ),
        "missing_required_quantities": [
            {
                "evidence_id": row.get("evidence_id"),
                "required_quantity_or_detail": row.get("missing_quantity_near_tag"),
                "previous_sentence": row.get("span"),
            }
            for row in _list(reconciliation.get("quantity_warnings"))
            if isinstance(row, dict)
        ],
        "source_evidence_mismatches": [
            {
                "evidence_ids": row.get("evidence_ids"),
                "tag_source_ids": row.get("tag_source_ids"),
                "adjacent_source_ids": row.get("adjacent_source_ids"),
                "previous_sentence": row.get("span"),
            }
            for row in _list(reconciliation.get("source_mismatch_warnings"))
            if isinstance(row, dict)
        ],
        "unsupported_quantities_near_tags": [
            {
                "evidence_ids": row.get("evidence_ids"),
                "unsupported_quantities": row.get("unsupported_quantities"),
                "previous_sentence": row.get("span"),
            }
            for row in _list(reconciliation.get("unsupported_quantity_warnings"))
            if isinstance(row, dict)
        ],
        "unsupported_untagged_quantities": [
            {
                "unsupported_quantities": row.get("unsupported_quantities"),
                "previous_sentence": row.get("span"),
            }
            for row in _list(reconciliation.get("untagged_unsupported_quantity_warnings"))
            if isinstance(row, dict)
        ],
        "instructions": [
            f"Return the complete section starting with ## {heading}.",
            "Keep the prose natural and decision-ready.",
            "Include every missing required contract below with its evidence tag.",
            "For each missing required quantity or detail, include it in the same sentence as that evidence tag.",
            "For each source-evidence mismatch, attach the claim to the evidence tag whose source IDs match the sentence.",
            "For each unsupported quantity near a tag, either remove that quantity from the sentence or use the evidence tag whose contract supports it.",
            "For each unsupported untagged quantity, remove it unless the original contracts list that quantity.",
            "For missing conflict reconciliation, explain why opposing findings differ by population, endpoint, design, or exposure instead of merely listing both.",
            "For unreconciled dose thresholds, state that ranges are study-specific and do not create one universal cutoff unless the contracts explicitly do so.",
            "Remove unsupported duration, population, endpoint, or causal qualifiers when they do not appear in the source_evidence excerpts.",
            "Do not let acute, mechanistic, biomarker, or surrogate evidence carry a broader clinical conclusion by itself.",
            "Use only evidence tags and source IDs already listed in the original prompt.",
        ],
    }
    return (
        f"{base_prompt.rstrip()}\n\n"
        "### Required revision feedback\n"
        f"{json.dumps(repair_packet, indent=2, ensure_ascii=False)}\n\n"
        "Rewrite the complete section now.\n"
    )


def _missing_contracts_for_retry(missing_ids: list[str], contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = set(missing_ids)
    rows = []
    for contract in contracts:
        if str(contract.get("evidence_id") or "") not in missing:
            continue
        rows.append(
            {
                "evidence_id": contract.get("evidence_id"),
                "claim": contract.get("claim"),
                "role": contract.get("role"),
                "required_quantity_atoms": contract.get("required_quantity_atoms", []),
                "source_ids": contract.get("citation_source_ids") or contract.get("source_ids", []),
                "must_qualify_with": contract.get("must_qualify_with", []),
            }
        )
    return rows


def _prepare_sections(
    section_plan: dict[str, Any],
    memo_ready_packet: dict[str, Any],
    evidence_contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    known_source_ids = _string_list(section_plan.get("known_source_ids"))
    sections = []
    for section in _list(section_plan.get("sections")):
        if not isinstance(section, dict):
            continue
        packet = section.get("packet") if isinstance(section.get("packet"), dict) else {}
        heading = str(section.get("heading") or packet.get("heading") or "").strip()
        section_id = str(section.get("section_id") or packet.get("section_id") or "").strip()
        prepared = dict(section)
        if section.get("prompt_mode") == "arm_b_slim" or packet.get("schema_id") == "arm_b_slim_section_packet_v1":
            local_contracts = [row for row in _list(section.get("contracts")) if isinstance(row, dict)]
            prepared["contracts"] = local_contracts
            prepared["citation_mode"] = "evidence_tags" if local_contracts else str(packet.get("citation_mode") or "none")
            if not str(prepared.get("prompt") or "").strip():
                prepared["prompt"] = str(section.get("prompt") or "")
        elif memo_ready_packet and evidence_contracts and section_id != "source_weighting":
            local_contracts = contracts_for_section(packet, heading, evidence_contracts)
            if local_contracts:
                prepared["contracts"] = local_contracts
                prepared["citation_mode"] = "evidence_tags"
                prepared["prompt"] = build_evidence_tagged_section_prompt(
                    packet,
                    known_source_ids=known_source_ids,
                    contracts=local_contracts,
                )
            else:
                prepared["contracts"] = []
                prepared["citation_mode"] = "source_ids"
        else:
            prepared["contracts"] = []
            prepared["citation_mode"] = "source_ids"
        sections.append(prepared)
    return sections


def _extract_section_markdown(raw: str, heading: str) -> str:
    candidate = repair_markdown_structure(_extract_markdown(raw))
    heading = str(heading or "").strip()
    if not candidate or not heading:
        return candidate
    candidate = re.sub(rf"(?m)^#+\s+{re.escape(heading)}\s*$", f"## {heading}", candidate, count=1)
    match = re.search(rf"(?ms)^##\s+{re.escape(heading)}\s*\n.*?(?=^##\s+\S|\Z)", candidate)
    if match:
        return repair_markdown_structure(match.group(0))
    return candidate


def _extract_markdown(raw: str) -> str:
    cleaned = str(raw).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md|json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    payload = _parse_json(cleaned)
    if isinstance(payload, dict):
        for key in ("memo_markdown", "markdown", "memo", "text", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        args = payload.get("args")
        if isinstance(args, dict):
            for key in ("memo_markdown", "markdown", "memo", "text", "content"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""
    if isinstance(payload, list):
        return ""
    return cleaned


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _unknown_section_source_ids(markdown: str, known_source_ids: set[str]) -> list[str]:
    unknown = []
    for citation in re.findall(r"\[([^\]]+)\]", str(markdown or "")):
        for token in re.split(r"[,;]", citation):
            source_id = token.strip()
            if source_id and source_id not in known_source_ids:
                unknown.append(source_id)
    return _dedupe(unknown)


def _normalize_known_source_alias_citations(markdown: str, aliases: dict[str, str]) -> str:
    if not aliases:
        return markdown

    def replace_cluster(match: re.Match[str]) -> str:
        tokens = [token.strip() for token in re.split(r"([,;])", match.group(1))]
        changed = False
        repaired = []
        for token in tokens:
            if token in {",", ";"}:
                repaired.append(token)
                continue
            replacement = _source_alias_lookup(token, aliases)
            changed = changed or replacement != token
            repaired.append(replacement)
        return "[" + "".join(repaired) + "]" if changed else match.group(0)

    return re.sub(r"\[([^\[\]]{1,180})\]", replace_cluster, str(markdown or ""))


def _source_alias_lookup(value: str, aliases: dict[str, str]) -> str:
    text = str(value or "").strip()
    if text in aliases:
        return aliases[text]
    normalized = _normalize_source_alias(text)
    for alias, source_id in aliases.items():
        if _normalize_source_alias(alias) == normalized:
            return source_id
    return text


def _source_alias_map(value: Any) -> dict[str, str]:
    return {str(key).strip(): str(item).strip() for key, item in (value.items() if isinstance(value, dict) else []) if str(key).strip() and str(item).strip()}


def _normalize_source_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _normalize_statistical_brackets(markdown: str) -> str:
    return re.sub(
        r"\[([^\[\]]{1,100})\]",
        lambda match: f"({match.group(1)})" if _statistical_bracket_content(match.group(1)) else match.group(0),
        str(markdown or ""),
    )


def _strip_uncontracted_citations(markdown: str) -> str:
    text = re.sub(r"\s*\[(?:SRC_[A-Z0-9_]+(?:\s*[,;]\s*SRC_[A-Z0-9_]+)*)\]", "", str(markdown or ""))
    return re.sub(r"\s*\{(?:E:)?[^{}\n]{1,120}\}", "", text)


def _statistical_bracket_content(content: str) -> bool:
    text = str(content or "").strip()
    if not re.search(r"\d", text):
        return False
    if re.search(r"\b(?:ci|confidence interval)\b", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\d+(?:\.\d+)?\s*(?:to|[-–—])\s*\d+(?:\.\d+)?", text, flags=re.IGNORECASE):
        return not re.search(r"[A-Za-z_]", re.sub(r"\bto\b", "", text, flags=re.IGNORECASE))
    return False


def _repair_near_miss_source_ids(markdown: str, known_source_ids: set[str]) -> str:
    if not known_source_ids:
        return markdown

    def repair_cluster(match: re.Match[str]) -> str:
        content = match.group(1)
        tokens = [token.strip() for token in re.split(r"([,;])", content)]
        changed = False
        repaired = []
        for token in tokens:
            if token in {",", ";"}:
                repaired.append(token)
                continue
            candidate = _nearest_known_source_id(token, known_source_ids)
            if candidate and candidate != token:
                changed = True
                repaired.append(candidate)
            else:
                repaired.append(token)
        return "[" + "".join(repaired) + "]" if changed else match.group(0)

    return re.sub(r"\[([^\[\]]{1,160})\]", repair_cluster, str(markdown or ""))


def _nearest_known_source_id(source_id: str, known_source_ids: set[str]) -> str:
    source_id = str(source_id or "").strip()
    if source_id in known_source_ids or len(source_id) < 12:
        return source_id
    scored = [
        (difflib.SequenceMatcher(None, source_id, known).ratio(), known)
        for known in known_source_ids
        if len(known) >= 12
    ]
    if not scored:
        return source_id
    score, known = max(scored)
    return known if score >= 0.9 else source_id


def _combined_section_prompts(sections: list[dict[str, Any]], *, whole_prompt: str) -> str:
    section_manifest = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        prompt = str(section.get("prompt") or "")
        packet = section.get("packet") if isinstance(section.get("packet"), dict) else {}
        section_manifest.append(
            {
                "section_id": section.get("section_id"),
                "heading": section.get("heading"),
                "prompt_chars": len(prompt),
                "packet_chars": len(json.dumps(packet, ensure_ascii=False)) if packet else 0,
                "model_call": "unified_section_synthesis",
                "citation_mode": section.get("citation_mode") or "source_ids",
                "contract_count": len(_list(section.get("contracts"))),
            }
        )
    lines = [
        "Parallel section synthesis prompts.",
        "",
        "Whole-memo reference prompt retained for artifact comparison:",
        whole_prompt.strip(),
        "",
        "Parallel section prompt manifest:",
        json.dumps(section_manifest, indent=2, ensure_ascii=False),
    ]
    return "\n".join(lines).strip() + "\n"


def _assemble_section_synthesis_memo(section_plan: dict[str, Any], section_reports: list[dict[str, Any]]) -> str:
    title = str(section_plan.get("title") or "Decision Memo").strip()
    question = str(section_plan.get("decision_question") or "").strip()
    bottom_line = str(section_plan.get("bottom_line") or "").strip()
    lines = [f"# Decision Memo: {title}" if title and title != "Decision Memo" else "# Decision Memo", ""]
    if question:
        lines.extend([f"**Decision Question:** {question}", ""])
    if bottom_line:
        lines.extend([f"**Bottom Line:** {bottom_line}", ""])
    for row in section_reports:
        section = str(row.get("markdown") or "").strip()
        if section:
            lines.extend([section, ""])
    return repair_markdown_structure("\n".join(lines).strip() + "\n")


def _public_section_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "section_id": row.get("section_id"),
        "heading": row.get("heading"),
        "citation_mode": row.get("citation_mode"),
        "accepted": bool(row.get("accepted")),
        "issues": _list(row.get("issues")),
        "unknown_source_ids": _list(row.get("unknown_source_ids")),
        "unknown_evidence_ids": _list(row.get("unknown_evidence_ids")),
        "used_evidence_id_count": len(_list(row.get("used_evidence_ids"))),
        "quantity_warning_count": len(_list(_dict(row.get("evidence_reconciliation_report")).get("quantity_warnings"))),
        "char_count": row.get("char_count", 0),
        "attempts": row.get("attempts", 0),
        "validation_attempts": row.get("validation_attempts", 0),
        "num_predict": row.get("num_predict", 0),
    }
