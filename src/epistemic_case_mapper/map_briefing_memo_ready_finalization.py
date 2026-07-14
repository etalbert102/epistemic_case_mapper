from __future__ import annotations

import ast
import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_analytical_balance_contract import required_analytical_balance_cards
from epistemic_case_mapper.map_briefing_calibrated_language import normalize_calibrated_language
from epistemic_case_mapper.map_briefing_canonical_packet_retention import (
    build_canonical_packet_retention_report,
    canonical_repair_items,
)
from epistemic_case_mapper.map_briefing_markdown_quality import markdown_structure_issues, repair_markdown_structure
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_memo_ready_packet_synthesis_prompt
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_obligations import all_memo_obligations, required_memo_obligations
from epistemic_case_mapper.map_briefing_memo_ready_presentation import build_citation_trace_markdown, run_memo_ready_presentation_normalization
from epistemic_case_mapper.map_briefing_memo_ready_polish_guardrails import build_memo_ready_final_polish_guardrails
from epistemic_case_mapper.map_briefing_memo_warning_packet import build_warning_resolution_report, unresolved_warning_repair_items
from epistemic_case_mapper.map_briefing_quantity_retention import quantity_retained, retention_quantity_rows
from epistemic_case_mapper.map_briefing_source_identity import compact_source_display, project_source_text_to_ids_for_model, project_sources_to_ids_for_model, replace_source_aliases_with_ids
from epistemic_case_mapper.model_backends import run_model_backend


def run_memo_ready_packet_synthesis(
    memo_ready_packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_memo_ready_packet_synthesis_prompt(memo_ready_packet)
    draft = render_memo_ready_packet_draft(memo_ready_packet)
    report = {
        "schema_id": "memo_ready_packet_synthesis_report_v1",
        "status": "deterministic_fallback" if backend.strip() == "prompt" else "not_run",
        "accepted": backend.strip() == "prompt",
        "live_enrichment_required": backend.strip() != "prompt",
        "used_default_path": True,
        "issues": [],
    }
    if backend.strip() == "prompt":
        return {"memo": draft, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            json_mode=False,
        )
    except RuntimeError as exc:
        report.update(
            {
                "status": "backend_error_live_enrichment_failed",
                "accepted": False,
                "issues": ["live_model_enrichment_failed", str(exc)],
            }
        )
        return {"memo": "", "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    candidate = repair_markdown_structure(_extract_markdown(raw))
    if not candidate:
        report.update(
            {
                "status": "empty_or_unparseable_live_enrichment_failed",
                "accepted": False,
                "issues": ["live_model_enrichment_failed", "synthesis returned no markdown"],
            }
        )
        return {"memo": "", "prompt": prompt, "raw": raw, "report": report}
    retention = build_memo_ready_packet_retention_report(candidate, memo_ready_packet)
    decision_usefulness_retention = build_decision_usefulness_retention_report(candidate, memo_ready_packet)
    decision_usefulness_repair = run_decision_usefulness_memo_repair(
        candidate,
        memo_ready_packet,
        decision_usefulness_retention,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    if decision_usefulness_repair.get("report", {}).get("applied"):
        candidate = decision_usefulness_repair["memo"]
        retention = build_memo_ready_packet_retention_report(candidate, memo_ready_packet)
        decision_usefulness_retention = build_decision_usefulness_retention_report(candidate, memo_ready_packet)
    strict_contract = _strict_packet_contract(memo_ready_packet)
    accepted = _acceptable_synthesis(candidate, retention, strict_contract=strict_contract)
    report.update(
        {
            "status": "accepted" if accepted else "accepted_with_retention_warnings",
            "accepted": accepted if strict_contract else True,
            "contract_mode": "strict_writer_packet" if strict_contract else "standard_packet",
            "used_default_path": False,
            "retention_status": retention.get("status"),
            "missing_mandatory_count": retention.get("missing_mandatory_count", 0),
            "unresolved_warning_count": retention.get("unresolved_warning_count", 0),
            "warning_resolution_report": retention.get("warning_resolution_report", {}),
            "decision_usefulness_retention_report": decision_usefulness_retention,
            "decision_usefulness_repair_report": decision_usefulness_repair.get("report", {}),
            "issues": [] if accepted else ["synthesis has packet-retention warnings"],
        }
    )
    return {"memo": candidate, "prompt": prompt, "raw": raw, "report": report}


def render_memo_ready_packet_draft(packet: dict[str, Any]) -> str:
    spine = _dict(packet.get("answer_spine"))
    items = _list(packet.get("evidence_items"))
    question = str(packet.get("decision_question") or "").strip()
    lines = [
        "## Decision Brief",
        "",
        f"**Decision question:** {question or 'not specified'}",
        "",
        _spine_text(spine.get("default_read")) or "The packet does not establish a clear default read.",
    ]
    confidence = str(spine.get("confidence") or "").strip()
    if confidence:
        lines.extend(["", f"**Confidence:** {confidence}"])
    support = _item_lines(items, {"strongest_support", "quantitative_anchor"})
    if support:
        lines.extend(["", "## What the Evidence Supports", "", *support])
    limits = _item_lines(items, {"strongest_counterweight", "scope_boundary"})
    if limits:
        lines.extend(["", "## What Limits the Inference", "", *limits])
    cruxes = _item_lines(items, {"decision_crux"})
    if cruxes:
        lines.extend(["", "## Decision Cruxes", "", *cruxes])
    sources = _source_lines(packet)
    if sources:
        lines.extend(["", "## Sources", "", *sources])
    return "\n".join(lines).rstrip() + "\n"


def build_memo_ready_packet_retention_report(memo: str, packet: dict[str, Any]) -> dict[str, Any]:
    source_aliases = _source_alias_lookup(packet)
    obligations = required_memo_obligations(packet)
    uses_obligations = bool(obligations)
    evidence_statuses = [_item_retention_status(memo, item, source_aliases) for item in _mandatory_items(packet)]
    statuses = (
        [_obligation_retention_status(memo, obligation, source_aliases) for obligation in obligations]
        if uses_obligations
        else evidence_statuses
    )
    balance_statuses = [_analytical_balance_retention_status(memo, card, source_aliases) for card in required_analytical_balance_cards(packet)]
    item_issues = [row for row in statuses if not row["retained"]]
    balance_issues = [row for row in balance_statuses if not row["retained"]]
    evidence_item_issues = [row for row in evidence_statuses if not row["retained"]]
    warning_resolution = build_warning_resolution_report(
        memo,
        _dict(packet.get("memo_warning_packet")),
        source_aliases=source_aliases,
    )
    warning_issues = [] if uses_obligations else [
        {
            "issue_type": "unresolved_memo_warning",
            "warning_status": row.get("status"),
            "severity": row.get("severity"),
            "warning_id": row.get("warning_id"),
            "warning_type": row.get("warning_type"),
            "claim": row.get("claim"),
            "source_labels": row.get("source_labels", []),
            "missing_anchor_terms": row.get("missing_anchor_terms", []),
        }
        for row in _list(warning_resolution.get("warnings_needing_repair"))
        if isinstance(row, dict)
    ]
    canonical_retention = build_canonical_packet_retention_report(memo, packet, source_aliases=source_aliases)
    canonical_issues = _list(canonical_retention.get("issues"))
    issues = [*item_issues, *balance_issues, *canonical_issues, *warning_issues]
    retained_status_count = sum(1 for row in statuses if row["retained"]) + sum(1 for row in balance_statuses if row["retained"])
    return {
        "schema_id": "memo_ready_packet_retention_report_v1",
        "validation_basis": "canonical_decision_writer_packet" if canonical_retention.get("status") != "not_available" else "memo_obligations" if uses_obligations else "mandatory_evidence_items",
        "analytical_balance_validation": "enabled",
        "canonical_packet_validation": canonical_retention.get("status", "not_available"),
        "status": "ready" if not issues else "warning",
        "must_retain_count": len(statuses) + len(balance_statuses) + int(canonical_retention.get("mandatory_retention_count", 0) or 0),
        "retained_must_retain_count": retained_status_count,
        "missing_critical_count": len(item_issues) + len(balance_issues) + len(canonical_issues),
        "missing_high_count": 0,
        "mandatory_item_count": len(statuses) + len(balance_statuses),
        "retained_mandatory_count": retained_status_count,
        "missing_mandatory_count": len(item_issues) + len(balance_issues) + len(canonical_issues),
        "missing_quantity_count": sum(len(row.get("missing_quantities", [])) for row in [*item_issues, *balance_issues, *canonical_issues]),
        "unresolved_warning_count": len(warning_issues),
        "warning_resolution_report": warning_resolution,
        "item_statuses": statuses,
        "analytical_balance_statuses": balance_statuses,
        "required_analytical_balance_count": len(balance_statuses),
        "retained_analytical_balance_count": sum(1 for row in balance_statuses if row["retained"]),
        "missing_analytical_balance_count": len(balance_issues),
        "evidence_item_statuses": evidence_statuses,
        "missing_evidence_item_count": len(evidence_item_issues),
        "memo_obligation_count": len(all_memo_obligations(packet)),
        "required_memo_obligation_count": len(obligations),
        "warning_issues": warning_issues,
        "canonical_packet_retention_report": canonical_retention,
        "issues": issues,
    }


def build_decision_usefulness_retention_report(memo: str, packet: dict[str, Any]) -> dict[str, Any]:
    usefulness = _decision_usefulness_packet(packet)
    if not usefulness:
        return {
            "schema_id": "decision_usefulness_retention_report_v1",
            "status": "not_available",
            "obligation_count": 0,
            "retained_count": 0,
            "missing_count": 0,
            "issues": [],
        }
    obligations = _decision_usefulness_obligations(usefulness)
    statuses = [_decision_usefulness_obligation_status(memo, row) for row in obligations]
    issues = [row for row in statuses if not row["retained"]]
    return {
        "schema_id": "decision_usefulness_retention_report_v1",
        "status": "ready" if not issues else "warning",
        "answer_shape": usefulness.get("answer_shape", ""),
        "obligation_count": len(statuses),
        "retained_count": sum(1 for row in statuses if row["retained"]),
        "missing_count": len(issues),
        "statuses": statuses,
        "issues": issues,
    }


def run_decision_usefulness_memo_repair(
    memo: str,
    packet: dict[str, Any],
    decision_usefulness_retention: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    issues = _list(decision_usefulness_retention.get("issues"))
    report = {
        "schema_id": "decision_usefulness_memo_repair_report_v1",
        "status": "not_needed" if not issues else "not_run",
        "accepted": False,
        "applied": False,
        "initial_missing_count": len(issues),
        "final_missing_count": len(issues),
        "issues": [],
    }
    if not issues:
        return {"memo": memo, "prompt": "", "raw": "", "report": report}
    prompt = build_decision_usefulness_memo_repair_prompt(memo, packet, decision_usefulness_retention)
    if backend.strip() == "prompt":
        report.update({"status": "skipped_prompt_backend", "issues": ["decision-usefulness repair backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries, json_mode=False)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    candidate = repair_markdown_structure(_extract_markdown(raw))
    if not candidate:
        report.update({"status": "empty_response_kept_original", "issues": ["repair returned no markdown"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    after = build_decision_usefulness_retention_report(candidate, packet)
    structure_issues = markdown_structure_issues(candidate, original=memo)
    improved = int(after.get("missing_count", 0) or 0) < int(decision_usefulness_retention.get("missing_count", 0) or 0)
    retained_regular = _retention_not_worse(
        build_memo_ready_packet_retention_report(memo, packet),
        build_memo_ready_packet_retention_report(candidate, packet),
    )
    applied = improved and retained_regular and not structure_issues
    report.update(
        {
            "status": "accepted" if applied else "no_decision_usefulness_improvement_kept_original",
            "accepted": applied,
            "applied": applied,
            "final_missing_count": after.get("missing_count", 0),
            "final_retention_report": after,
            "structure_issues": structure_issues,
            "regular_retention_not_worse": retained_regular,
            "issues": [] if applied else ["repair did not improve decision-usefulness retention without retention or markdown regression"],
        }
    )
    return {"memo": candidate if applied else memo, "prompt": prompt, "raw": raw, "report": report}


def build_decision_usefulness_memo_repair_prompt(
    memo: str,
    packet: dict[str, Any],
    decision_usefulness_retention: dict[str, Any],
) -> str:
    repair_packet = {
        "schema_id": "decision_usefulness_memo_repair_packet_v1",
        "decision_question": packet.get("decision_question") or _dict(packet.get("canonical_decision_writer_packet")).get("decision_question"),
        "missing_decision_support_moves": [
            _decision_usefulness_repair_row(row)
            for row in _list(decision_usefulness_retention.get("issues"))[:8]
            if isinstance(row, dict)
        ],
    }
    return (
        "Revise the decision memo so it naturally includes the missing decision-support moves.\n"
        "Keep the same headings and overall conclusion. Preserve source_ids exactly as bracketed citations near the claims they support.\n"
        "Use only the missing rows below; do not add new evidence, new sources, or a new matrix.\n"
        "If a row is awkward, integrate its substance in a natural sentence rather than naming the packet field.\n"
        "Return the complete revised memo in markdown only.\n\n"
        f"Current memo:\n{memo.rstrip()}\n\n"
        f"Missing decision-support rows:\n{json.dumps(repair_packet, indent=2, ensure_ascii=False)}\n"
    )


def run_memo_ready_packet_repair(
    memo: str,
    packet: dict[str, Any],
    retention_report: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_memo_ready_packet_repair_prompt(memo, packet, retention_report)
    report = {
        "schema_id": "memo_ready_packet_repair_report_v1",
        "status": "not_needed" if not retention_report.get("issues") else "not_run",
        "accepted": False,
        "initial_missing_mandatory_count": retention_report.get("missing_mandatory_count", 0),
        "initial_unresolved_warning_count": retention_report.get("unresolved_warning_count", 0),
        "issues": [],
    }
    if not retention_report.get("issues"):
        return {"memo": memo, "prompt": "", "raw": "", "report": report}
    if backend.strip() == "prompt":
        report.update({"status": "skipped_prompt_backend", "issues": ["memo-ready repair backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    candidate = repair_markdown_structure(_extract_markdown(raw))
    if not candidate:
        report.update({"status": "empty_response_kept_original", "issues": ["repair returned no markdown"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    after = build_memo_ready_packet_retention_report(candidate, packet)
    structure_issues = markdown_structure_issues(candidate, original=memo)
    strict_contract = _strict_packet_contract(packet)
    improved = _strict_retention_improved(retention_report, after) if strict_contract else _retention_improved(retention_report, after)
    complete = _retention_complete(after)
    accepted = improved and not structure_issues and (complete if strict_contract else True)
    applied = accepted or (strict_contract and improved and not structure_issues)
    status = "accepted" if accepted else "no_retention_improvement_kept_original"
    if strict_contract and applied and not complete:
        status = "partial_retention_improvement_applied_with_warnings"
    report.update(
        {
            "status": status,
            "accepted": accepted,
            "applied": applied,
            "contract_mode": "strict_writer_packet" if strict_contract else "standard_packet",
            "final_missing_mandatory_count": after.get("missing_mandatory_count", 0),
            "final_retained_mandatory_count": after.get("retained_mandatory_count", 0),
            "final_unresolved_warning_count": after.get("unresolved_warning_count", 0),
            "final_retention_report": after,
            "structure_issues": structure_issues,
            "issues": [] if accepted else [_repair_issue(strict_contract, improved=improved, complete=complete, structure_issues=structure_issues)],
        }
    )
    return {"memo": candidate if applied else memo, "prompt": prompt, "raw": raw, "report": report}


def build_memo_ready_packet_repair_prompt(memo: str, packet: dict[str, Any], retention_report: dict[str, Any]) -> str:
    uses_obligations = str(retention_report.get("validation_basis") or "").startswith("memo_obligations")
    strict_contract = _strict_packet_contract(packet)
    limit = 16 if strict_contract else 8
    warning_packet = _dict(packet.get("memo_warning_packet"))
    warning_resolution = _dict(retention_report.get("warning_resolution_report"))
    source_trail = _list(packet.get("source_trail"))
    repair_packet = {
        "decision_question": packet.get("decision_question"),
        "contract_mode": "strict_writer_packet" if strict_contract else "standard_packet",
        "missing_obligations": [
            _repair_obligation(packet, issue)
            for issue in _list(retention_report.get("issues"))[:limit]
            if isinstance(issue, dict) and issue.get("issue_type") == "missing_memo_obligation"
        ],
        "missing_items": [
            _repair_item(packet, issue)
            for issue in _list(retention_report.get("issues"))[:limit]
            if isinstance(issue, dict) and issue.get("issue_type") == "missing_memo_ready_item"
        ],
        "missing_balance_cards": [
            _repair_balance_card(issue)
            for issue in _list(retention_report.get("issues"))[:limit]
            if isinstance(issue, dict) and issue.get("issue_type") == "missing_analytical_balance_card"
        ],
        "missing_canonical_items": canonical_repair_items(retention_report, limit=limit),
        "unresolved_warnings": [] if uses_obligations else unresolved_warning_repair_items(warning_resolution, warning_packet, limit=8),
    }
    repair_packet = project_source_text_to_ids_for_model(project_sources_to_ids_for_model(repair_packet, source_trail), source_trail)
    memo_for_model = replace_source_aliases_with_ids(memo, source_trail)
    return (
        "You are repairing a decision memo using only a memo-ready evidence repair packet.\n"
        "Rewrite the affected paragraph or section naturally so missing evidence is integrated into the reasoning.\n\n"
        "Rules:\n"
        "- Return the full revised memo in Markdown.\n"
        "- Preserve the decision question, source IDs, quantities, and answer stance already present.\n"
        "- Repair missing obligations and balance cards by improving the reasoning around the affected point.\n"
        "- Repair missing canonical items by restoring the affected answer skeleton, counterweight, scope, source, quantity, or evidence claim.\n"
        "- Use only the missing obligations, missing balance cards, or legacy missing items in the repair packet.\n"
        "- For strict writer-packet repairs, every missing obligation in the repair packet is a required decision-writing obligation; include it, merge it with related prose, or explain the scope/uncertainty it creates.\n"
        "- For unresolved warnings, incorporate the source-backed claim if it changes the read; otherwise use it to bound scope, confidence, or remaining uncertainty.\n"
        "- For each quantity you add, explain what it means for the decision.\n"
        "- Keep packet IDs, validation, telemetry, and internal pipeline machinery out of the prose.\n\n"
        f"Repair packet:\n{json.dumps(repair_packet, indent=2, ensure_ascii=False)}\n\n"
        f"Current memo:\n{memo_for_model.strip()}\n"
    )


def run_memo_ready_final_polish(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    before = build_memo_ready_packet_retention_report(memo, packet)
    prompt = build_memo_ready_final_polish_prompt(memo, packet)
    report = {
        "schema_id": "memo_ready_final_polish_report_v1",
        "status": "skipped_prompt_backend" if backend.strip() == "prompt" else "not_run",
        "accepted": False,
        "issues": [],
    }
    if backend.strip() == "prompt":
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    candidate = normalize_memo_ready_polish_text(repair_markdown_structure(_extract_markdown(raw)))
    if not candidate:
        report.update({"status": "empty_response_kept_original", "issues": ["final polish returned no markdown"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    after = build_memo_ready_packet_retention_report(candidate, packet)
    structure_issues = markdown_structure_issues(candidate, original=memo)
    accepted = _retention_not_worse(before, after) and not structure_issues
    report.update(
        {
            "status": "accepted" if accepted else "rejected_kept_original",
            "accepted": accepted,
            "before_missing_mandatory_count": before.get("missing_mandatory_count", 0),
            "after_missing_mandatory_count": after.get("missing_mandatory_count", 0),
            "structure_issues": structure_issues,
            "issues": [] if accepted else ["final polish regressed retention or damaged markdown"],
        }
    )
    return {"memo": candidate if accepted else memo, "prompt": prompt, "raw": raw, "report": report}


def build_memo_ready_final_polish_prompt(memo: str, packet: dict[str, Any]) -> str:
    source_trail = _list(packet.get("source_trail"))
    guardrails = build_memo_ready_final_polish_guardrails(packet)
    guardrails = project_source_text_to_ids_for_model(guardrails, source_trail)
    memo_for_model = replace_source_aliases_with_ids(memo, source_trail)
    return (
        "You are doing a final prose polish on a source-grounded decision memo.\n"
        "Improve flow, sentence rhythm, paragraph order, and transitions without changing the analysis.\n"
        "The guardrails below are validation constraints, not memo content or an outline.\n\n"
        "Rules:\n"
        "- Return the full revised memo in Markdown.\n"
        "- Use the memo as the source of prose; use guardrails only to avoid dropping protected content.\n"
        "- Preserve the decision question, confidence, bottom-line stance, uncertainty, subgroup caveats, counterweights, source IDs, and required quantities.\n"
        "- Do not add new facts, sources, numbers, populations, recommendations, or causal interpretations.\n"
        "- Rewrite at paragraph level when the prose is stiff; preserving meaning does not mean preserving wording.\n"
        "- Do not return a near-identical memo unless the prose is already publication-ready.\n"
        "- Make the opening answer direct, then make the supporting reasoning flow across paragraphs.\n"
        "- Preserve calibrated confidence: prefer bounded, low-concern, compatible with, not associated with, or does not clearly show over absolute safety, safe limit, proven harmless, or high-confidence unless the evidence explicitly warrants that wording.\n"
        "- Remove checklist rhythm, repeated sentence openings, and source-ID-as-subject patterns when they make the memo stiff.\n"
        "- Prefer analyst prose over formulaic labels: for example, use 'The strongest support is...' or 'The main caveat is...' rather than 'The primary evidence stems from...' or 'A significant counterweight is...'.\n"
        "- Shape paragraphs around reader questions: bottom line, why, limits, and practical implication.\n"
        "- Keep citations attached to the claims they support, but avoid citation clutter by placing one source marker at the end of a sentence or clause when several nearby facts come from the same source.\n"
        "- Prefer concrete verbs over stock phrases such as rooted in, stems from, or this conclusion.\n"
        "- Fix obvious citation spacing mistakes without changing source IDs.\n"
        "- Make the memo read like decision-ready analysis.\n\n"
        f"Polish guardrails:\n{json.dumps(guardrails, indent=2, ensure_ascii=False)}\n\n"
        f"Memo:\n{memo_for_model.strip()}\n"
    )


def normalize_memo_ready_polish_text(memo: str) -> str:
    text = str(memo or "")
    if not text.strip():
        return ""
    replacements = [
        (r"\betal\.", "et al."),
        (r"\bet\s+al\s*\.", "et al."),
        (r"\b([A-Z][A-Za-z-]+)\s+et al\.\s*,\s*(\d{4})", r"\1 et al. \2"),
        (r"\b([A-Z][A-Za-z-]+)\s+et al\.\s+(\d{4})\s*\)", r"\1 et al. \2)"),
        (r"\bThe primary support for this conclusion is rooted in\b", "The main support is"),
        (r"\bThe primary support for this conclusion stems from\b", "The main support is"),
        (r"\bThe strongest support for this conclusion stems from\b", "The strongest support is"),
        (r"\bThe primary support for ([^.]{1,120}?) is rooted in\b", r"The main support for \1 is"),
        (r"\bThe primary support for ([^.]{1,120}?) stems from\b", r"The main support for \1 is"),
        (r"\bThe strongest support for ([^.]{1,120}?) stems from\b", r"The strongest support for \1 is"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = normalize_calibrated_language(text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def _item_lines(items: list[Any], roles: set[str]) -> list[str]:
    lines = []
    for item in items:
        if not isinstance(item, dict) or item.get("role") not in roles:
            continue
        source = str(item.get("source_label") or "").strip()
        suffix = f" [{source}]" if source else ""
        quantities = _quantity_clause(item)
        lines.append(f"- {item.get('reader_claim')}{quantities}{suffix}")
    return lines


def _source_lines(packet: dict[str, Any]) -> list[str]:
    rows = []
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        label = str(source.get("source_label") or "").strip()
        url = str(source.get("source_url") or "").strip()
        if label and url:
            rows.append(f"- [{label}]({url})")
        elif label:
            rows.append(f"- {label}")
    return _dedupe(rows)


def _decision_usefulness_packet(packet: dict[str, Any]) -> dict[str, Any]:
    usefulness = _dict(packet.get("decision_usefulness_packet"))
    if usefulness:
        return usefulness
    return _dict(_dict(packet.get("canonical_decision_writer_packet")).get("decision_usefulness_packet"))


def _decision_usefulness_obligations(usefulness: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stance = _dict(usefulness.get("recommended_stance"))
    if str(stance.get("stance") or "").strip():
        rows.append(
            {
                "obligation_type": "recommended_stance",
                "label": "recommended stance",
                "required_text": _join_nonempty([stance.get("stance"), stance.get("scope"), stance.get("why_this_stance")]),
                "source_ids": _string_list(stance.get("source_ids")),
                "evidence_item_ids": _string_list(stance.get("evidence_item_ids")),
                "packet_row": stance,
            }
        )
    for index, row in enumerate(_list(usefulness.get("tradeoffs")), start=1):
        if isinstance(row, dict) and str(row.get("tradeoff") or "").strip():
            rows.append(
                {
                    "obligation_type": "tradeoff",
                    "label": f"tradeoff {index}",
                    "required_text": _join_nonempty([row.get("tradeoff"), row.get("choose_a_if"), row.get("choose_b_if")]),
                    "source_ids": _string_list(row.get("source_ids")),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                    "packet_row": row,
                }
            )
    for index, row in enumerate(_list(usefulness.get("cruxes_and_thresholds")), start=1):
        if isinstance(row, dict) and str(row.get("crux") or "").strip():
            rows.append(
                {
                    "obligation_type": "crux_threshold",
                    "label": f"crux threshold {index}",
                    "required_text": _join_nonempty([row.get("crux"), row.get("current_read"), row.get("would_change_if"), row.get("threshold")]),
                    "source_ids": _string_list(row.get("source_ids")),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                    "packet_row": row,
                }
            )
    for index, row in enumerate(_list(usefulness.get("monitoring_triggers")), start=1):
        if isinstance(row, dict) and str(row.get("trigger") or "").strip():
            rows.append(
                {
                    "obligation_type": "monitoring_trigger",
                    "label": f"monitoring trigger {index}",
                    "required_text": _join_nonempty([row.get("trigger"), row.get("would_update")]),
                    "source_ids": _string_list(row.get("source_ids")),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                    "packet_row": row,
                }
            )
    return rows


def _decision_usefulness_obligation_status(memo: str, obligation: dict[str, Any]) -> dict[str, Any]:
    required_text = str(obligation.get("required_text") or "").strip()
    terms = _decision_usefulness_terms(required_text)
    memo_norm = _norm(memo)
    matched_terms = [term for term in terms if term in memo_norm]
    return {
        "obligation_type": obligation.get("obligation_type"),
        "label": obligation.get("label"),
        "retained": _decision_usefulness_obligation_retained(memo, obligation),
        "required_text": required_text,
        "source_ids": _string_list(obligation.get("source_ids")),
        "evidence_item_ids": _string_list(obligation.get("evidence_item_ids")),
        "matched_terms": matched_terms[:12],
        "missing_terms": [term for term in terms if term not in matched_terms][:12],
        "packet_row": obligation.get("packet_row", {}),
    }


def _decision_usefulness_obligation_retained(memo: str, obligation: dict[str, Any]) -> bool:
    row = _dict(obligation.get("packet_row"))
    obligation_type = str(obligation.get("obligation_type") or "")
    if obligation_type == "monitoring_trigger":
        trigger_retained = _decision_usefulness_text_retained(memo, str(row.get("trigger") or ""), ratio=0.6)
        update_retained = _decision_usefulness_text_retained(memo, str(row.get("would_update") or ""), ratio=0.55)
        return trigger_retained and update_retained and _has_update_cue(memo)
    if obligation_type == "crux_threshold":
        return _decision_usefulness_text_retained(memo, str(obligation.get("required_text") or ""), ratio=0.45) and _has_crux_cue(memo)
    return _decision_usefulness_text_retained(memo, str(obligation.get("required_text") or ""), ratio=0.45)


def _decision_usefulness_text_retained(memo: str, text: str, *, ratio: float = 0.45) -> bool:
    memo_norm = _norm(memo)
    text_norm = _norm(text)
    if not text_norm:
        return True
    if text_norm in memo_norm:
        return True
    terms = _decision_usefulness_terms(text)
    if not terms:
        return False
    matched = sum(1 for term in terms if term in memo_norm)
    return matched >= max(2, min(len(terms), int(round(len(terms) * ratio))))


def _has_update_cue(memo: str) -> bool:
    memo_norm = _norm(memo)
    return any(cue in memo_norm for cue in ("new evidence", "would change", "would update", "would shift", "monitor", "trigger"))


def _has_crux_cue(memo: str) -> bool:
    memo_norm = _norm(memo)
    return any(cue in memo_norm for cue in ("hinges on", "rests on", "crux", "would change", "threshold", "bounded by", "bound the answer"))


def _decision_usefulness_terms(text: str) -> list[str]:
    stop = {
        "about",
        "adult",
        "adults",
        "because",
        "between",
        "could",
        "current",
        "decision",
        "evidence",
        "focus",
        "general",
        "rather",
        "should",
        "source",
        "stance",
        "their",
        "there",
        "these",
        "those",
        "would",
    }
    return _dedupe(
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]{3,}", _norm(text))
        if token not in stop
    )[:24]


def _decision_usefulness_repair_row(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "obligation_type": issue.get("obligation_type"),
        "required_text": issue.get("required_text"),
        "source_ids": _string_list(issue.get("source_ids")),
        "evidence_item_ids": _string_list(issue.get("evidence_item_ids")),
        "packet_row": issue.get("packet_row", {}),
    }


def _join_nonempty(values: list[Any]) -> str:
    return " ".join(str(value).strip() for value in values if str(value or "").strip())


def _source_alias_replacements(packet: dict[str, Any]) -> dict[str, str]:
    labels = _packet_source_labels(packet)
    common_prefix = _common_token_prefix(labels)
    replacements: dict[str, str] = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        source_label = str(source.get("source_label") or "").strip()
        display = _preferred_source_display(source, common_prefix=common_prefix)
        if not display:
            continue
        aliases = [
            str(source.get("source_id") or "").strip(),
            source_label,
            str(source.get("display_label") or "").strip(),
            str(source.get("citation_label") or "").strip(),
        ]
        for alias in aliases:
            for variant in _source_label_variants(alias):
                if variant and variant != display:
                    replacements[variant] = display
    for source_label in labels:
        if not source_label:
            continue
        display = _preferred_source_display({"source_label": source_label}, common_prefix=common_prefix)
        if display and display != source_label:
            for alias in _source_label_variants(source_label):
                replacements[alias] = display
    return replacements


def _packet_source_labels(packet: dict[str, Any]) -> list[str]:
    labels = [
        str(source.get("source_label") or "").strip()
        for source in _list(packet.get("source_trail"))
        if isinstance(source, dict) and str(source.get("source_label") or "").strip()
    ]
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        labels.extend(_string_list(item.get("source_labels")))
        labels.append(str(item.get("source_label") or "").strip())
    for obligation in all_memo_obligations(packet):
        labels.extend(_string_list(obligation.get("source_labels")))
        labels.append(str(obligation.get("source_label") or "").strip())
    return _dedupe(label for label in labels if label)


def _source_label_variants(source_label: str) -> list[str]:
    variants = [source_label]
    if "_" in source_label:
        variants.append(source_label.replace("_", " "))
    if " " in source_label:
        variants.append(source_label.replace(" ", "_"))
        variants.append(source_label.replace(" Sources ", "_Sources "))
        variants.append(source_label.replace(" sources ", "_sources "))
    if "_Sources " in source_label:
        variants.append(source_label.replace("_Sources ", " Sources "))
    if "_sources " in source_label:
        variants.append(source_label.replace("_sources ", " sources "))
    return list(dict.fromkeys(variant for variant in variants if variant))


def _source_alias_lookup(packet: dict[str, Any]) -> dict[str, list[str]]:
    replacements = _source_alias_replacements(packet)
    aliases: dict[str, list[str]] = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        source_label = str(source.get("source_label") or "").strip()
        source_id = str(source.get("source_id") or "").strip()
        if not source_label and not source_id:
            continue
        values = [
            source_label,
            source_id,
            compact_source_display(source),
            replacements.get(source_label, ""),
            replacements.get(source_id, ""),
            str(source.get("display_label") or "").strip(),
            str(source.get("citation_label") or "").strip(),
        ]
        alias_values = _exact_dedupe(value for value in values if value)
        for key in (source_label, source_id, *alias_values):
            if key:
                aliases[key] = alias_values
    return aliases


def _exact_dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value or "").strip() for value in values if str(value or "").strip()))


def _source_aliases_for_label(source_label: str, source_aliases: dict[str, list[str]]) -> list[str]:
    if source_label in source_aliases:
        return source_aliases[source_label]
    normalized = _norm(source_label)
    for label, aliases in source_aliases.items():
        if _norm(label) == normalized:
            return aliases
    return []


def _preferred_source_display(source: dict[str, Any], *, common_prefix: list[str]) -> str:
    label = str(source.get("source_label") or "").strip()
    for key in ("citation_label", "display_label"):
        value = str(source.get(key) or "").strip()
        if value and value != label:
            return value
    if common_prefix:
        tokens = label.replace("_", " ").split()
        if [token.lower() for token in tokens[: len(common_prefix)]] == [token.lower() for token in common_prefix]:
            stripped = " ".join(tokens[len(common_prefix) :]).strip()
            if stripped:
                return stripped
    artifact_stripped = _strip_artifact_source_prefix(label)
    if artifact_stripped != label:
        return artifact_stripped
    return label


def _strip_artifact_source_prefix(label: str) -> str:
    tokens = str(label or "").replace("_", " ").split()
    lowered = [token.lower() for token in tokens]
    if len(tokens) >= 5 and lowered[:2] == ["deep", "research"] and "sources" in lowered[2:5]:
        source_index = lowered.index("sources", 2, 5)
        stripped = " ".join(tokens[source_index + 1 :]).strip()
        if len(stripped.split()) >= 2:
            return stripped
    return label


def _common_token_prefix(labels: list[str]) -> list[str]:
    tokenized = [label.replace("_", " ").split() for label in labels if label.strip()]
    if len(tokenized) < 2:
        return []
    prefix: list[str] = []
    for tokens in zip(*tokenized):
        lowered = {token.lower() for token in tokens}
        if len(lowered) != 1:
            break
        prefix.append(tokens[0])
    if len(prefix) < 2:
        return []
    shortest_remainder = min((len(tokens) - len(prefix) for tokens in tokenized), default=0)
    return prefix if shortest_remainder >= 2 else []


def _quantity_clause(item: dict[str, Any]) -> str:
    quantities = []
    for quantity in _list(item.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        interpretation = str(quantity.get("interpretation") or "").strip()
        if value and interpretation:
            quantities.append(f"{value}: {interpretation}")
        elif value:
            quantities.append(value)
    return f" ({'; '.join(quantities)})" if quantities else ""


def _spine_text(value: Any) -> str:
    if isinstance(value, dict):
        return _best_spine_field(value)
    text = str(value or "").strip()
    parsed = _parse_python_literal(text)
    if isinstance(parsed, dict):
        return _best_spine_field(parsed)
    return text


def _best_spine_field(value: dict[str, Any]) -> str:
    for key in ("current_read", "default_read", "primary_answer", "answer_stance", "classification"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""


def _parse_python_literal(text: str) -> Any:
    if not text.startswith("{"):
        return None
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None


def _mandatory_items(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(packet.get("evidence_items")) if isinstance(item, dict) and item.get("must_use")]


def _item_retention_status(memo: str, item: dict[str, Any], source_aliases: dict[str, list[str]] | None = None) -> dict[str, Any]:
    claim = str(item.get("reader_claim") or "").strip()
    source = str(item.get("source_label") or "").strip()
    quantities = retention_quantity_rows(item)
    missing_quantities = [quantity["value"] for quantity in quantities if not quantity_retained(memo, quantity)]
    aliases = _exact_dedupe([source, *(_source_aliases_for_label(source, source_aliases or {}) if source else [])])
    source_retained = not source or any(_contains_text(memo, alias) for alias in aliases)
    claim_retained = _mentions_enough_content_terms(memo, claim, minimum=4)
    retained = source_retained and claim_retained and not missing_quantities
    return {
        "item_id": item.get("item_id"),
        "severity": "critical",
        "issue_type": "missing_memo_ready_item",
        "role": item.get("role"),
        "retained": retained,
        "source_retained": source_retained,
        "claim_retained": claim_retained,
        "missing_quantities": missing_quantities,
        "reader_claim": claim,
        "source_label": source,
    }


def _obligation_retention_status(
    memo: str,
    obligation: dict[str, Any],
    source_aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    statement = str(obligation.get("statement") or "").strip()
    source_labels = _string_list(obligation.get("source_labels"))
    quantities = retention_quantity_rows(obligation)
    missing_quantities = [quantity["value"] for quantity in quantities if not quantity_retained(memo, quantity)]
    source_retained = not source_labels or any(
        _contains_text(memo, alias)
        for source in source_labels
        for alias in _source_aliases_for_label(source, source_aliases or {})
    )
    if not source_retained and source_labels:
        source_retained = any(_contains_text(memo, source) for source in source_labels)
    mode = str(obligation.get("validation_mode") or "claim_terms")
    if mode == "scope_signal":
        source_retained = True
    terms = _string_list(obligation.get("validation_terms")) or _content_terms(statement)
    if mode == "scope_signal":
        claim_retained = any(_contains_text(memo, term) for term in terms)
    else:
        claim_retained = _mentions_enough_terms(memo, terms, minimum=min(4, max(2, len(terms) // 2)))
    retained = source_retained and claim_retained and not missing_quantities
    return {
        "obligation_id": obligation.get("obligation_id"),
        "severity": "critical",
        "issue_type": "missing_memo_obligation",
        "obligation_type": obligation.get("obligation_type"),
        "role": obligation.get("role"),
        "retained": retained,
        "source_retained": source_retained,
        "claim_retained": claim_retained,
        "missing_quantities": missing_quantities,
        "statement": statement,
        "source_labels": source_labels,
        "validation_terms": terms,
    }


def _analytical_balance_retention_status(
    memo: str,
    card: dict[str, Any],
    source_aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    statement = str(card.get("statement") or "").strip()
    source_labels = _string_list(card.get("source_labels"))
    source_retained = not source_labels or any(
        _contains_text(memo, alias)
        for source in source_labels
        for alias in _source_aliases_for_label(source, source_aliases or {})
    )
    if not source_retained and source_labels:
        source_retained = any(_contains_text(memo, source) for source in source_labels)
    terms = _string_list(card.get("validation_terms")) or _content_terms(statement)
    claim_retained = _mentions_enough_terms(memo, terms, minimum=min(4, max(2, len(terms) // 2)))
    numbers = _string_list(card.get("surface_numbers"))
    number_retained = not numbers or any(_contains_text(memo, value) for value in numbers)
    retained = source_retained and claim_retained and number_retained
    return {
        "balance_card_id": card.get("card_id"),
        "severity": "critical",
        "issue_type": "missing_analytical_balance_card",
        "role": card.get("role"),
        "retained": retained,
        "source_retained": source_retained,
        "claim_retained": claim_retained,
        "number_retained": number_retained,
        "missing_quantities": [] if number_retained else numbers,
        "statement": statement,
        "decision_relevance": card.get("decision_relevance"),
        "source_labels": source_labels,
        "validation_terms": terms,
        "writing_job": card.get("writing_job"),
    }


def _repair_item(packet: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    item_id = str(issue.get("item_id") or "")
    item = next((row for row in _mandatory_items(packet) if str(row.get("item_id") or "") == item_id), {})
    return {
        "item_id": item_id,
        "preferred_role": item.get("role"),
        "reader_claim": item.get("reader_claim"),
        "source_label": item.get("source_label"),
        "quantities": item.get("quantities", []),
        "decision_relevance": item.get("decision_relevance"),
        "caveat": item.get("caveat"),
        "missing_quantities": issue.get("missing_quantities", []),
    }


def _repair_balance_card(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "balance_card_id": issue.get("balance_card_id"),
        "role": issue.get("role"),
        "statement": issue.get("statement"),
        "decision_relevance": issue.get("decision_relevance"),
        "source_labels": issue.get("source_labels", []),
        "validation_terms": issue.get("validation_terms", []),
        "writing_job": issue.get("writing_job"),
        "missing_quantities": issue.get("missing_quantities", []),
    }


def _repair_obligation(packet: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    obligation_id = str(issue.get("obligation_id") or "")
    obligation = next(
        (row for row in required_memo_obligations(packet) if str(row.get("obligation_id") or "") == obligation_id),
        {},
    )
    evidence_item = _evidence_item_for_obligation(packet, obligation)
    return {
        "obligation_id": obligation_id,
        "obligation_type": obligation.get("obligation_type") or issue.get("obligation_type"),
        "role": obligation.get("role") or issue.get("role"),
        "statement": obligation.get("statement") or issue.get("statement"),
        "prose_instruction": obligation.get("prose_instruction"),
        "source_labels": obligation.get("source_labels", issue.get("source_labels", [])),
        "quantities": obligation.get("quantities", []),
        "missing_quantities": issue.get("missing_quantities", []),
        "decision_relevance": evidence_item.get("decision_relevance"),
        "caveat": evidence_item.get("caveat"),
        "reader_claim": evidence_item.get("reader_claim"),
    }


def _evidence_item_for_obligation(packet: dict[str, Any], obligation: dict[str, Any]) -> dict[str, Any]:
    item_ids = {str(item_id) for item_id in _string_list(obligation.get("evidence_item_ids")) if str(item_id).strip()}
    if not item_ids:
        return {}
    for item in _list(packet.get("evidence_items")):
        if isinstance(item, dict) and str(item.get("item_id") or "") in item_ids:
            return item
    return {}


def _retention_quantities(row: dict[str, Any]) -> list[str]:
    return [quantity["value"] for quantity in retention_quantity_rows(row)]


def _acceptable_synthesis(memo: str, retention: dict[str, Any], *, strict_contract: bool = False) -> bool:
    if not memo.strip():
        return False
    if strict_contract:
        return _retention_complete(retention)
    return int(retention.get("missing_mandatory_count", 0) or 0) <= 2


def _retention_improved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_missing = int(before.get("missing_mandatory_count", 0) or 0)
    after_missing = int(after.get("missing_mandatory_count", 0) or 0)
    if after_missing < before_missing:
        return True
    before_warnings = int(before.get("unresolved_warning_count", 0) or 0)
    after_warnings = int(after.get("unresolved_warning_count", 0) or 0)
    if after_warnings < before_warnings:
        return True
    return int(after.get("missing_quantity_count", 0) or 0) < int(before.get("missing_quantity_count", 0) or 0)


def _strict_retention_improved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_missing = int(before.get("missing_mandatory_count", 0) or 0)
    after_missing = int(after.get("missing_mandatory_count", 0) or 0)
    if after_missing < before_missing:
        return True
    before_warnings = int(before.get("unresolved_warning_count", 0) or 0)
    after_warnings = int(after.get("unresolved_warning_count", 0) or 0)
    return after_warnings < before_warnings


def _retention_complete(retention: dict[str, Any]) -> bool:
    return (
        int(retention.get("missing_mandatory_count", 0) or 0) == 0
        and int(retention.get("unresolved_warning_count", 0) or 0) == 0
    )


def _strict_packet_contract(packet: dict[str, Any]) -> bool:
    return str(packet.get("method") or "") == "global_decision_writer_packet_adapter" and isinstance(packet.get("writer_packet"), dict)


def _repair_issue(
    strict_contract: bool,
    *,
    improved: bool,
    complete: bool,
    structure_issues: list[str],
) -> str:
    if structure_issues:
        return "repair damaged markdown structure"
    if strict_contract and improved and not complete:
        return "repair improved retention but did not satisfy all strict writer-packet obligations"
    return "repair did not improve packet retention without markdown damage"


def _retention_not_worse(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return (
        int(after.get("missing_mandatory_count", 0) or 0) <= int(before.get("missing_mandatory_count", 0) or 0)
        and int(after.get("unresolved_warning_count", 0) or 0) <= int(before.get("unresolved_warning_count", 0) or 0)
    )


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


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    return not needle or needle.lower() in text.lower()


def _mentions_enough_content_terms(text: str, statement: str, *, minimum: int) -> bool:
    terms = _content_terms(statement)
    if not terms:
        return True
    return _mentions_enough_terms(text, terms, minimum=minimum)


def _mentions_enough_terms(text: str, terms: list[str], *, minimum: int) -> bool:
    if not terms:
        return True
    required = min(minimum, len(terms))
    lowered = text.lower()
    return sum(1 for term in terms if term and term.lower() in lowered) >= required


def _content_terms(text: str) -> list[str]:
    stop = {"about", "after", "also", "because", "before", "between", "could", "from", "have", "into", "only", "should", "that", "their", "there", "this", "when", "where", "with", "would"}
    return _dedupe([term.lower() for term in re.findall(r"[A-Za-z][A-Za-z-]{2,}", text) if term.lower() not in stop])
