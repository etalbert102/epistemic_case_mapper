from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.main_memo_obligations import (
    build_main_memo_obligation_plan,
    obligation_issues_for_text,
    section_obligations_for_title,
)
from epistemic_case_mapper.decision_argument_artifacts import compact_decision_argument_artifacts
from epistemic_case_mapper.map_briefing_memo_slots import (
    _replace_internal_reader_phrases,
    _repair_overclaim_strength_language,
    _repair_unbalanced_markdown_strong,
    _rewrite_has_raw_identifiers,
    _rewrite_mentions_anchor_row,
    _rewrite_mentions_gap,
)
from epistemic_case_mapper.map_briefing_reader_contracts import build_reader_memo_rewrite_contract
from epistemic_case_mapper.map_briefing_reader_polish import clean_reader_memo_text
from epistemic_case_mapper.map_briefing_section_attempts import run_section_model_attempts
from epistemic_case_mapper.map_briefing_section_ownership import (
    build_section_evidence_ownership,
    compact_evidence_reference,
    section_owns_evidence,
)
from epistemic_case_mapper.map_briefing_section_packets import (
    compact_argument_model,
    section_synthesis_packet,
    write_section_packets_artifact,
)
from epistemic_case_mapper.map_briefing_section_structure import (
    repair_structured_section,
    section_structure_issues,
    structured_scope_and_exceptions,
)
from epistemic_case_mapper.map_briefing_validation import validate_briefing_against_scaffold
from epistemic_case_mapper.model_backends import run_model_backend


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)


def rewrite_reader_memo_by_section(
    memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifacts: Any | None = None,
) -> dict[str, Any]:
    """Rewrite memo sections independently, accepting only locally valid sections."""
    contract = build_reader_memo_rewrite_contract(memo, scaffold)
    contract["_section_synthesis_scaffold"] = scaffold
    contract["_main_memo_obligation_plan"] = build_main_memo_obligation_plan(scaffold=scaffold)
    report: dict[str, Any] = {
        "schema_id": "section_rewrite_report_v1",
        "status": "not_run",
        "accepted_section_count": 0,
        "section_count": 0,
        "sections": [],
        "whole_validation_status": "not_run",
    }
    leading, sections = _split_sections(memo)
    report["section_count"] = len(sections)
    if not sections:
        report["status"] = "no_sections"
        return {"memo": memo, "report": report}
    contract["_section_evidence_ownership"] = build_section_evidence_ownership(sections, contract)
    report["evidence_ownership"] = {
        "owned_row_count": len(contract["_section_evidence_ownership"].get("rows", {})),
        "owner_counts": contract["_section_evidence_ownership"].get("owner_counts", {}),
    }
    if backend.strip() == "prompt":
        section_packets = _report_only_section_packets(sections, contract)
        report["status"] = "skipped_prompt_backend"
        report["section_packet_count"] = len(section_packets)
        section_packet_path = None
        if artifacts is not None:
            section_packet_path = write_section_packets_artifact(artifacts, section_packets)
            report["section_packets_path"] = str(section_packet_path)
        return {"memo": memo, "report": report, "section_packets_path": section_packet_path}
    section_packets: list[dict[str, Any]] = []
    rewritten_sections: list[str] = []
    deferred_decision_section: dict[str, str] | None = None
    for index, section in enumerate(sections):
        if section["title"] == "Decision Brief":
            deferred_decision_section = section
            continue
        section_contract = _section_contract(section, contract)
        section_packets.append(
            {
                "title": section["title"],
                "section_job": section_contract.get("section_job"),
                "packet": section_contract.get("section_synthesis_packet", {}),
            }
        )
        result = _rewrite_one_section(
            section,
            section_contract,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            previous_title=sections[index - 1]["title"] if index else "",
            next_title=sections[index + 1]["title"] if index + 1 < len(sections) else "",
        )
        if artifacts is not None:
            _write_section_debug_artifacts(artifacts, index, section["title"], result)
        report["sections"].append(result["report"])
        rewritten_sections.append(str(result["section"]))
    body_candidate = clean_reader_memo_text("\n\n".join(part for part in rewritten_sections if part.strip()))
    if deferred_decision_section is not None:
        section_packets.insert(
            0,
            {
                "title": "Decision Brief",
                "section_job": "Write the opening answer after the body sections are accepted.",
                "packet": _decision_brief_last_packet(contract, body_candidate),
            },
        )
        brief_result = _rewrite_decision_brief_last(
            deferred_decision_section,
            contract,
            body_candidate,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
        )
        if artifacts is not None:
            _write_section_debug_artifacts(artifacts, 0, "Decision Brief Final", brief_result)
        report["sections"].insert(0, brief_result["report"])
        candidate = clean_reader_memo_text(
            "\n\n".join(part for part in [leading.strip(), str(brief_result["section"]), body_candidate] if part.strip())
        )
    else:
        candidate = clean_reader_memo_text("\n\n".join(part for part in [leading.strip(), body_candidate] if part.strip()))
    validation = validate_briefing_against_scaffold(candidate.rstrip() + "\n\n" + evidence_appendix.rstrip() + "\n", scaffold, candidate_map)
    report["whole_validation_status"] = validation.get("status", "unknown")
    report["whole_validation_issues"] = validation.get("issues", [])
    report["main_memo_obligation_validation"] = _post_synthesis_obligation_validation(candidate, contract)
    report["accepted_section_count"] = sum(1 for item in report["sections"] if item.get("accepted"))
    report["section_packet_count"] = len(section_packets)
    section_packet_path = None
    if artifacts is not None:
        section_packet_path = write_section_packets_artifact(artifacts, section_packets)
        report["section_packets_path"] = str(section_packet_path)
    if validation.get("status") == "needs_review":
        report["status"] = "global_validation_failed_fallback"
        return {"memo": memo, "report": report, "section_packets_path": section_packet_path}
    report["status"] = "accepted_partial" if report["accepted_section_count"] else "no_sections_accepted"
    return {"memo": candidate, "report": report, "section_packets_path": section_packet_path}


def _rewrite_one_section(
    section: dict[str, str],
    section_contract: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    previous_title: str,
    next_title: str,
) -> dict[str, Any]:
    prompt = _section_rewrite_prompt(section, section_contract, previous_title=previous_title, next_title=next_title)
    section_report: dict[str, Any] = {
        "title": section["title"],
        "status": "not_run",
        "accepted": False,
        "issues": [],
        "required_evidence_count": len(section_contract["required_evidence"]),
        "evidence_reference_count": len(section_contract.get("evidence_references", [])),
        "required_gap_count": len(section_contract["required_gaps"]),
        "required_crux_count": len(section_contract["required_cruxes"]),
        "required_main_memo_obligation_count": len(section_contract.get("required_main_memo_obligations", [])),
    }
    if not _should_rewrite_section(section, section_contract):
        section_report["status"] = "skipped_low_value_section"
        return {"section": section["markdown"], "prompt": prompt, "raw": "", "report": section_report}
    if section["title"].strip().lower() == "decision cruxes":
        structured = _structured_decision_crux_section(section_contract)
        repaired, issues = _validate_rewritten_section(structured, section, section_contract)
        if not issues:
            section_report.update({"status": "accepted_structured_cruxes", "accepted": True, "issues": [], "structured_cruxes": True})
            return {"section": clean_reader_memo_text(repaired), "prompt": prompt, "raw": "", "report": section_report}
    attempt_result = run_section_model_attempts(
        prompt=prompt, expected_title=section["title"], backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries,
        validate=lambda rewritten: _validate_rewritten_section(rewritten, section, section_contract), run_backend=run_model_backend,
    )
    _apply_attempt_report(section_report, attempt_result, deterministic_text=section["markdown"])
    if attempt_result["accepted"]:
        return {"section": clean_reader_memo_text(str(attempt_result["section"])), "prompt": attempt_result["prompt"], "raw": attempt_result["raw"], "report": section_report}
    structured = _structured_section_fallback(section, section_contract)
    if structured != section["markdown"] and not _section_rewrite_issues(structured, section, section_contract):
        section_report.update({"status": "accepted_structured_fallback", "accepted": True, "structured_fallback": True})
        return {"section": clean_reader_memo_text(structured), "prompt": attempt_result["prompt"], "raw": attempt_result["raw"], "report": section_report}
    section_report["status"] = "rejected_fallback"
    return {"section": section["markdown"], "prompt": attempt_result["prompt"], "raw": attempt_result["raw"], "report": section_report}


def _report_only_section_packets(sections: list[dict[str, str]], contract: dict[str, Any]) -> list[dict[str, Any]]:
    body_memo = clean_reader_memo_text(
        "\n\n".join(section["markdown"] for section in sections if section["title"] != "Decision Brief")
    )
    packets: list[dict[str, Any]] = []
    for section in sections:
        if section["title"] == "Decision Brief":
            packets.append(
                {
                    "title": "Decision Brief",
                    "section_job": "Write the opening answer after the body sections are accepted.",
                    "packet": _decision_brief_last_packet(contract, body_memo),
                }
            )
            continue
        section_contract = _section_contract(section, contract)
        packets.append(
            {
                "title": section["title"],
                "section_job": section_contract.get("section_job"),
                "packet": section_contract.get("section_synthesis_packet", {}),
            }
        )
    return packets


def _rewrite_decision_brief_last(
    original: dict[str, str],
    contract: dict[str, Any],
    body_memo: str,
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    fallback = _deterministic_final_decision_brief(contract, body_memo)
    prompt = "Deterministic Decision Brief slot packet:\n" + json.dumps(_decision_brief_last_packet(contract, body_memo), indent=2, ensure_ascii=False)
    section_report: dict[str, Any] = {
        "title": "Decision Brief",
        "status": "accepted_deterministic_slots",
        "accepted": True,
        "issues": [],
        "required_evidence_count": 0,
        "required_gap_count": 0,
        "required_crux_count": 0,
        "required_main_memo_obligation_count": len(
            section_obligations_for_title("Decision Brief", contract.get("_main_memo_obligation_plan", []))
        ),
        "generated_last": True,
        "deterministic_slots": True,
    }
    return {"section": fallback, "prompt": prompt, "raw": "", "report": section_report}


def _decision_brief_last_packet(contract: dict[str, Any], body_memo: str) -> dict[str, Any]:
    scaffold = (
        contract.get("_section_synthesis_scaffold", {})
        if isinstance(contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    return {
        "question": contract.get("question"),
        "confidence": contract.get("confidence"),
        "answer_frame": contract.get("answer_frame"),
        "argument_model": compact_argument_model(scaffold, "decision brief"),
        "decision_argument_artifacts": compact_decision_argument_artifacts(scaffold, "decision brief"),
        "bottom_line": synthesis.get("bottom_line"),
        "recommendations": synthesis.get("recommendations", [])[:5],
        "scope_boundaries": synthesis.get("scope_boundaries", [])[:3],
        "exceptions": synthesis.get("exceptions", [])[:3],
        "cruxes": synthesis.get("cruxes", [])[:3],
        "body_practical_read": _markdown_section_with_heading(body_memo, "Practical Read"),
        "body_decision_cruxes": _markdown_section_with_heading(body_memo, "Decision Cruxes"),
        "first_page_required_obligations": section_obligations_for_title(
            "Decision Brief",
            contract.get("_main_memo_obligation_plan", []),
            limit=4,
        ),
    }


def _deterministic_final_decision_brief(contract: dict[str, Any], body_memo: str) -> str:
    question = str(contract.get("question", "")).strip()
    confidence = str(contract.get("confidence") or "medium").strip()
    slots = _decision_brief_slots(contract, body_memo)
    answer = _sentence(slots.get("answer", "Use the source packet for a conditional decision read."))
    evidence = _sentence(slots.get("evidence", ""))
    caveat = _sentence(slots.get("caveat", ""))
    paragraph_parts = [answer]
    if evidence:
        paragraph_parts.append(f"Key evidence: {evidence}")
    if caveat:
        paragraph_parts.append(f"Key caveat: {caveat}")
    lines = ["## Decision Brief", ""]
    if question:
        lines.extend([f"**Decision question:** {question}", ""])
    lines.extend([" ".join(paragraph_parts), "", f"**Confidence:** {confidence}"])
    return clean_reader_memo_text("\n".join(lines))


def _decision_brief_slots(contract: dict[str, Any], body_memo: str) -> dict[str, str]:
    obligations = section_obligations_for_title("Decision Brief", contract.get("_main_memo_obligation_plan", []), limit=4)
    by_category = {str(row.get("category", "")): row for row in obligations}
    answer = _default_answer_from_body(body_memo) or _default_answer_from_contract(contract)
    evidence_obligation = by_category.get("quantitative_anchor") or by_category.get("strongest_support")
    caveat_obligation = by_category.get("scope_boundary") or by_category.get("strongest_counterargument")
    evidence = _obligation_slot_text(evidence_obligation) or _support_evidence_from_contract(contract)
    caveat = _obligation_slot_text(caveat_obligation) or (_decision_caveats_from_body(body_memo) or _decision_caveats_from_contract(contract) or [""])[0]
    return {
        "answer": _short_text(_readerize_instruction(answer), 220),
        "evidence": _short_text(_readerize_instruction(evidence), 260),
        "caveat": _short_text(_readerize_instruction(caveat), 260),
    }


def _obligation_slot_text(obligation: dict[str, Any] | None) -> str:
    if not isinstance(obligation, dict):
        return ""
    statement = str(obligation.get("statement", "")).strip()
    if statement:
        return statement
    terms = obligation.get("search_terms", [])
    if isinstance(terms, list) and terms:
        return str(terms[0])
    return ""


def _default_answer_from_body(body_memo: str) -> str:
    practical = _markdown_section_with_heading(body_memo, "Practical Read")
    paragraphs = _paragraphs_without_heading(practical)
    for paragraph in paragraphs:
        if paragraph.startswith(("-", "*", "|")):
            continue
        if paragraph and not _exception_led_answer(paragraph):
            return paragraph
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", practical, flags=re.MULTILINE)
    if bullets:
        for bullet in bullets:
            lead = _clean_bullet(bullet)
            if _exception_led_answer(lead):
                continue
            lead = re.sub(r"^the default practical read is\b", "For the default case, the current read is", lead, flags=re.IGNORECASE)
            return lead
    why = _markdown_section_with_heading(body_memo, "Why This Read")
    paragraphs = _paragraphs_without_heading(why)
    return paragraphs[0] if paragraphs else ""


def _default_answer_from_contract(contract: dict[str, Any]) -> str:
    scaffold = (
        contract.get("_section_synthesis_scaffold", {})
        if isinstance(contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    recommendations = [row for row in synthesis.get("recommendations", []) if isinstance(row, dict)]
    for row in recommendations:
        text = str(row.get("recommendation", "")).strip()
        if text and not _exception_led_answer(text):
            return _readerize_instruction(text)
    bottom = synthesis.get("bottom_line", {}) if isinstance(synthesis.get("bottom_line"), dict) else {}
    current = str(bottom.get("current_read", "")).strip()
    if current:
        return _readerize_instruction(current)
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    return str(answer_frame.get("direct_answer") or "Use the source packet for a conditional decision read.").strip()


def _decision_caveats_from_body(body_memo: str) -> list[str]:
    practical = _markdown_section_with_heading(body_memo, "Practical Read")
    bullets = [_clean_bullet(item) for item in re.findall(r"^\s*[-*]\s+(.+)$", practical, flags=re.MULTILINE)]
    caveats = [item for item in bullets[1:] if item]
    if caveats:
        return caveats[:4]
    scope = _markdown_section_with_heading(body_memo, "Practical Scope and Exceptions")
    return _first_sentences(scope, limit=3)


def _decision_caveats_from_contract(contract: dict[str, Any]) -> list[str]:
    scaffold = (
        contract.get("_section_synthesis_scaffold", {})
        if isinstance(contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    exceptions = [row for row in synthesis.get("exceptions", []) if isinstance(row, dict)]
    caveats = [str(row.get("current_read", "")).strip() for row in exceptions if str(row.get("current_read", "")).strip()]
    cruxes = [row for row in synthesis.get("cruxes", []) if isinstance(row, dict)]
    caveats.extend(str(row.get("crux", "")).strip() for row in cruxes if str(row.get("crux", "")).strip())
    return [_sentence(_readerize_instruction(item)) for item in caveats if item][:4]


def _support_evidence_from_contract(contract: dict[str, Any]) -> str:
    rows = [row for row in contract.get("required_evidence", []) if isinstance(row, dict)]
    for preferred in ("Main support", "Direct outcome evidence", "Evidence carrying the conclusion"):
        for row in rows:
            if str(row.get("slot", "")) == preferred and str(row.get("claim", "")).strip():
                return _short_text(str(row["claim"]).strip(), 220)
    for row in rows:
        if str(row.get("claim", "")).strip():
            return _short_text(str(row["claim"]).strip(), 220)
    scaffold = (
        contract.get("_section_synthesis_scaffold", {})
        if isinstance(contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    evidence_rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)]
    for role in ("conclusion_support", "main_support"):
        for row in evidence_rows:
            if str(row.get("role", "")) == role and str(row.get("claim", "")).strip():
                return _short_text(str(row["claim"]).strip(), 220)
    for row in evidence_rows:
        if str(row.get("claim", "")).strip():
            return _short_text(str(row["claim"]).strip(), 220)
    return ""


def _decision_brief_last_issues(section: str, contract: dict[str, Any], body_memo: str) -> list[str]:
    issues: list[str] = []
    if not section.lstrip().startswith("## Decision Brief"):
        issues.append("decision brief heading changed or dropped")
    if str(contract.get("question", "")).strip() and "**Decision question:**" not in section:
        issues.append("decision question missing from final brief")
    if "**Confidence:**" not in section:
        issues.append("confidence line missing from final brief")
    if SECTION_RE.findall(section) != ["Decision Brief"]:
        issues.append("final brief included extra top-level sections")
    answer = _first_answer_paragraph(section)
    if not answer:
        issues.append("final brief missing answer paragraph")
    elif _exception_led_answer(answer):
        issues.append("final brief opens with an exception instead of the default answer")
    if answer and _content_overlap(answer, _default_answer_from_body(body_memo) or _default_answer_from_contract(contract)) < 2:
        issues.append("final brief does not preserve the body default answer")
    if len(section.split()) > 190:
        issues.append("final brief is too long for an executive opening")
    if _rewrite_has_raw_identifiers(section):
        issues.append("final brief contains raw map identifiers")
    issues.extend(
        obligation_issues_for_text(
            section_obligations_for_title("Decision Brief", contract.get("_main_memo_obligation_plan", []), limit=4),
            section,
            prefix="final brief dropped first-page obligation",
        )
    )
    return issues


def _markdown_section_with_heading(markdown: str, title: str) -> str:
    leading, sections = _split_sections(markdown)
    _ = leading
    for section in sections:
        if section["title"].strip().lower() == title.strip().lower():
            return section["markdown"].strip()
    return ""


def _paragraphs_without_heading(markdown: str) -> list[str]:
    text = re.sub(r"^##\s+.+?\s*$", "", markdown.strip(), count=1, flags=re.MULTILINE).strip()
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]


def _first_answer_paragraph(section: str) -> str:
    for paragraph in _paragraphs_without_heading(section):
        if paragraph.startswith("**Decision question:**") or paragraph.startswith("**Confidence:**"):
            continue
        return paragraph
    return ""


def _compact_body_for_prompt(body_memo: str) -> str:
    kept: list[str] = []
    for title in (
        "Practical Read",
        "Why This Read",
        "Evidence Carrying the Conclusion",
        "Practical Scope and Exceptions",
        "Decision Cruxes",
        "Limits of the Current Map",
    ):
        section = _markdown_section_with_heading(body_memo, title)
        if section:
            kept.append(_short_text(section, 1800))
    return "\n\n".join(kept)


def _clean_bullet(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned.rstrip(".")


def _first_sentences(markdown: str, *, limit: int) -> list[str]:
    text = re.sub(r"^##\s+.+?\s*$", "", markdown.strip(), count=1, flags=re.MULTILINE)
    text = re.sub(r"^\s*#+\s+.+$", "", text, flags=re.MULTILINE)
    sentences = re.findall(r"[^.!?]+[.!?]", re.sub(r"\s+", " ", text))
    return [_sentence(sentence) for sentence in sentences[:limit]]


def _sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."


def _readerize_instruction(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip().rstrip(".")
    replacements = (
        (r"^state the default as\b", "The default case is"),
        (r"^preserve this dose/intensity boundary in practical guidance:\s*", "The practical boundary is "),
        (r"^name this subgroup separately from the default case:\s*", "Treat this as a separate caveat: "),
    )
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


def _exception_led_answer(text: str) -> bool:
    lowered = str(text).lower().strip()
    if any(marker in lowered[:180] for marker in ("default", "overall", "generally", "under the stated", "for the target", "for the main")):
        return False
    return any(
        marker in lowered[:180]
        for marker in (
            "high-risk",
            "subgroup",
            "exception",
            "caveat",
            "people with",
            "patients with",
            "associated with a higher risk",
        )
    )


def _section_rewrite_prompt(section: dict[str, str], contract: dict[str, Any], *, previous_title: str, next_title: str) -> str:
    return (
        "You are writing one section of a decision-support memo from a local source-grounded synthesis packet.\n"
        "Rewrite only the supplied section. You may reorganize and synthesize within this section, but do not add facts.\n"
        "Use the section synthesis packet as the primary structure: issue clusters, load-bearing claims, bridge claims, and tensions should become coherent prose.\n"
        "Use decision_argument_artifacts first when present: summary_of_findings carries the evidence rows, competing_reads shows rejected alternatives, argument_case_top_claim anchors the answer, and traceability_requirements shows obligations that must not disappear.\n"
        "When quantitative_anchors include key_quantities, use one relevant card-level estimate in evidence-bearing sections instead of only qualitative phrasing.\n"
        "Preserve every required local evidence anchor, gap, confidence line, crux item, and main-memo obligation in the section contract.\n"
        "A main-memo obligation is satisfied by carrying one listed search term or by a faithful source-grounded paraphrase of its statement.\n"
        "Return only valid JSON with this schema: {\"section_markdown\": \"## Same Heading\\n\\nRewritten section\"}.\n\n"
        f"Previous section heading: {previous_title or 'none'}\n"
        f"Next section heading: {next_title or 'none'}\n\n"
        "Section contract:\n"
        f"{json.dumps(contract, indent=2, ensure_ascii=False)}\n\n"
        "The section below is the deterministic draft to improve using the section synthesis packet.\n"
        "Section to rewrite:\n"
        f"{section['markdown'].strip()}\n"
    )


def _section_rewrite_issues(rewritten: str, original: dict[str, str], contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not rewritten.strip():
        return ["missing section_markdown"]
    if not rewritten.lstrip().startswith(f"## {original['title']}"):
        issues.append("section heading changed or dropped")
    headings = SECTION_RE.findall(rewritten)
    if len(headings) != 1:
        issues.append("section rewrite included extra top-level sections")
    if contract["requires_confidence"] and "**Confidence:**" not in rewritten:
        issues.append("section dropped confidence line")
    if _rewrite_has_raw_identifiers(rewritten):
        issues.append("section contains raw map identifiers")
    if "crux" in original["title"].lower() and _has_generic_crux_language(rewritten):
        issues.append("section crux table contains generic placeholder language")
    min_decision_cruxes = int(contract.get("min_decision_changing_cruxes", 0) or 0)
    if min_decision_cruxes and _decision_changing_crux_count(rewritten) < min_decision_cruxes:
        issues.append("section does not preserve enough decision-changing crux conditions")
    for row in contract["required_evidence"]:
        if not _rewrite_mentions_anchor_row(rewritten, row):
            issues.append(f"section dropped required evidence: {str(row.get('claim', ''))[:90]}")
    for gap in contract["required_gaps"]:
        if not _rewrite_mentions_gap(rewritten, gap):
            issues.append(f"section dropped required gap: {gap[:90]}")
    for crux in contract["required_cruxes"]:
        crux_text = str(crux.get("crux", "")).strip()
        if crux_text and _content_overlap(rewritten, crux_text) < 2:
            issues.append(f"section dropped required crux: {crux_text[:90]}")
    issues.extend(
        obligation_issues_for_text(
            contract.get("required_main_memo_obligations", []),
            rewritten,
            prefix="section dropped required main-memo obligation",
        )
    )
    original_words = max(1, len(original["markdown"].split()))
    if "crux" not in original["title"].lower() and contract["has_obligations"] and len(rewritten.split()) < max(35, int(original_words * 0.45)):
        issues.append("section rewrite is too short for its local contract")
    issues.extend(section_structure_issues(rewritten, contract))
    return issues


def _validate_rewritten_section(rewritten: str, section: dict[str, str], contract: dict[str, Any]) -> tuple[str, list[str]]:
    repaired = repair_structured_section(_repair_section(rewritten), contract)
    return repaired, _section_rewrite_issues(repaired, section, contract)


def _validate_final_decision_brief(rewritten: str, contract: dict[str, Any], body_memo: str) -> tuple[str, list[str]]:
    repaired = _repair_section(rewritten)
    return repaired, _decision_brief_last_issues(repaired, contract, body_memo)


def _post_synthesis_obligation_validation(memo: str, contract: dict[str, Any]) -> dict[str, Any]:
    _, sections = _split_sections(memo)
    missing: list[dict[str, Any]] = []
    plan = contract.get("_main_memo_obligation_plan", [])
    for section in sections:
        if section["title"].lower() in {"evidence trail", "sources"}:
            continue
        obligations = section_obligations_for_title(section["title"], plan, limit=4 if section["title"] == "Decision Brief" else 5)
        if section["title"].strip().lower() == "decision cruxes":
            obligations = []
        issues = obligation_issues_for_text(obligations, section["markdown"], prefix="post-synthesis section missing obligation")
        for issue in issues:
            missing.append({"section": section["title"], "issue": issue})
    return {
        "schema_id": "section_obligation_validation_v1",
        "status": "passes" if not missing else "has_missing_obligations",
        "missing_count": len(missing),
        "missing": missing[:20],
    }


def _apply_attempt_report(report: dict[str, Any], result: dict[str, Any], *, deterministic_text: str) -> None:
    report.update({
        "status": result["status"],
        "accepted": bool(result["accepted"]),
        "issues": result["issues"],
        "attempts": result["attempts"],
        "attempt_count": result["attempt_count"],
    })
    if result.get("rewritten"):
        report["raw_word_count"] = len(str(result["rewritten"]).split())
        report["deterministic_word_count"] = len(deterministic_text.split())


def _structured_section_fallback(section: dict[str, str], contract: dict[str, Any]) -> str:
    title = section["title"].lower()
    if "scope" in title and "exception" in title:
        return structured_scope_and_exceptions(contract)
    return section["markdown"]


def _section_contract(section: dict[str, str], full_contract: dict[str, Any]) -> dict[str, Any]:
    text = section["markdown"]
    title = section["title"]
    frame = full_contract.get("decision_frame", {}) if isinstance(full_contract.get("decision_frame"), dict) else {}
    section_jobs = frame.get("section_jobs", {}) if isinstance(frame.get("section_jobs"), dict) else {}
    required_evidence = [
        row for row in full_contract.get("required_evidence", [])
        if isinstance(row, dict)
        and _rewrite_mentions_anchor_row(text, row)
        and section_owns_evidence(title, row, full_contract)
    ]
    evidence_references = [
        compact_evidence_reference(row, full_contract)
        for row in full_contract.get("required_evidence", [])
        if isinstance(row, dict)
        and _rewrite_mentions_anchor_row(text, row)
        and not section_owns_evidence(title, row, full_contract)
    ]
    required_gaps = [
        gap for gap in _string_list(full_contract.get("required_gaps"))
        if _rewrite_mentions_gap(text, gap) or "limit" in title.lower()
    ]
    required_cruxes = _section_required_cruxes(full_contract) if "crux" in title.lower() else []
    practical_actions = full_contract.get("practical_actions", []) if "practical" in title.lower() else []
    main_memo_obligations = section_obligations_for_title(
        title,
        full_contract.get("_main_memo_obligation_plan", []),
    )
    if title.strip().lower() == "decision cruxes":
        main_memo_obligations = []
    synthesis_packet = section_synthesis_packet(title, full_contract)
    synthesis_packet["required_main_memo_obligations"] = main_memo_obligations
    return {
        "heading": title,
        "confidence": full_contract.get("confidence"),
        "requires_confidence": "**Confidence:**" in text,
        "required_evidence": required_evidence,
        "evidence_references": evidence_references,
        "required_gaps": required_gaps,
        "required_cruxes": required_cruxes if isinstance(required_cruxes, list) else [],
        "required_main_memo_obligations": main_memo_obligations,
        "practical_actions": practical_actions if isinstance(practical_actions, list) else [],
        "min_decision_changing_cruxes": min(2, len(required_cruxes)) if "crux" in title.lower() else 0,
        "section_synthesis_packet": synthesis_packet,
        "decision_frame": frame,
        "section_job": section_jobs.get(title, "Smooth this section while preserving its local evidence obligations."),
        "has_obligations": bool(required_evidence or required_gaps or required_cruxes or practical_actions or main_memo_obligations),
        "style": [
            "Keep the same heading.",
            "Use concrete prose; avoid internal phrases such as mapped support, map-backed read, and decision role.",
            "Prefer the decision-frame terms over generic intervention/option language when the frame provides them.",
            "For evidence_references, mention only the role-level implication when useful; do not restate full source details unless this section owns that evidence.",
            "Use short transition language only when it helps connect to adjacent sections.",
        ],
    }


def _section_required_cruxes(full_contract: dict[str, Any]) -> list[dict[str, Any]]:
    scaffold = (
        full_contract.get("_section_synthesis_scaffold", {})
        if isinstance(full_contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    artifacts = scaffold.get("decision_argument_artifacts", {}) if isinstance(scaffold.get("decision_argument_artifacts"), dict) else {}
    structured = artifacts.get("structured_decision_cruxes", {}) if isinstance(artifacts.get("structured_decision_cruxes"), dict) else {}
    structured_cruxes = [row for row in structured.get("cruxes", []) if isinstance(row, dict)]
    if structured_cruxes:
        return structured_cruxes[:3]
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    synthesis_cruxes = [row for row in synthesis.get("cruxes", []) if isinstance(row, dict)]
    if synthesis_cruxes:
        return synthesis_cruxes[:3]
    required = full_contract.get("required_cruxes", [])
    return [row for row in required if isinstance(row, dict)] if isinstance(required, list) else []


def _structured_decision_crux_section(contract: dict[str, Any]) -> str:
    cruxes = [row for row in contract.get("required_cruxes", []) if isinstance(row, dict)]
    if not cruxes:
        packet = contract.get("section_synthesis_packet", {}) if isinstance(contract.get("section_synthesis_packet"), dict) else {}
        artifacts = packet.get("decision_argument_artifacts", {}) if isinstance(packet.get("decision_argument_artifacts"), dict) else {}
        cruxes = [row for row in artifacts.get("structured_decision_cruxes", []) if isinstance(row, dict)]
    rows: list[list[str]] = []
    for row in cruxes[:3]:
        crux = _clean_crux_cell(str(row.get("crux", "")))
        why = _clean_crux_cell(str(row.get("why_it_matters", "")))
        current = _clean_crux_cell(str(row.get("current_read", "")))
        change = _clean_crux_cell(str(row.get("would_change_if", "")))
        if crux and current and change:
            rows.append([crux, why or "This condition could change the recommendation.", current, change])
    if not rows:
        rows.append([
            "Whether the strongest counterevidence generalizes to the default case.",
            "This determines whether the answer should become narrower or more cautious.",
            "The current read treats the counterevidence as a boundary rather than the whole answer.",
            "The recommendation would change if stronger evidence showed the counterevidence applies broadly.",
        ])
    lines = [
        "## Decision Cruxes",
        "",
        "| Crux | Why it matters | Current read | Would change if |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _clean_crux_cell(text: str) -> str:
    cleaned = re.sub(r"\bClaim\s+[A-Z]\b[:\s-]*", "", text, flags=re.I)
    cleaned = re.sub(r"\b(?:claim|relation|source)_?[a-z]*\d+\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        return ""
    return _sentence(cleaned)


def _markdown_cell(text: str) -> str:
    return _short_text(re.sub(r"\|", "/", text).strip(), 220)


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _decision_changing_crux_count(text: str) -> int:
    lowered = text.lower()
    explicit = len(re.findall(r"\b(?:would|could)\s+change\s+if\b|\brecommendation\s+would\s+change\b|\badvice\s+would\s+change\b", lowered))
    table_rows = 0
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        lowered = line.lower()
        if "crux" in lowered and "current" in lowered:
            continue
        if set(line.strip()) <= {"|", "-", ":", " "}:
            continue
        if "would change" in lowered and "if" in lowered:
            table_rows += 1
    return max(explicit, table_rows)


def _should_rewrite_section(section: dict[str, str], contract: dict[str, Any]) -> bool:
    words = len(section["markdown"].split())
    if words < 35 and not contract["has_obligations"]:
        return False
    if section["title"].lower() in {"evidence trail", "sources"}:
        return False
    return True


def _split_sections(markdown: str) -> tuple[str, list[dict[str, str]]]:
    matches = list(SECTION_RE.finditer(markdown))
    if not matches:
        return markdown, []
    leading = markdown[: matches[0].start()]
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        title = match.group(1).strip()
        sections.append({"title": title, "markdown": markdown[start:end].strip()})
    return leading, sections


def _repair_section(text: str) -> str:
    repaired = clean_reader_memo_text(text)
    repaired = _replace_internal_reader_phrases(repaired)
    repaired = _repair_overclaim_strength_language(repaired)
    repaired = _repair_unbalanced_markdown_strong(repaired)
    return clean_reader_memo_text(repaired)


def _content_overlap(text: str, reference: str) -> int:
    text_terms = set(_content_terms(text))
    return sum(1 for term in _content_terms(reference) if term in text_terms)


def _has_generic_crux_language(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "current packet treats this condition",
            "new evidence showed the condition did not materially affect",
            "recommendation holds only where the actor can keep the intervention usable",
        )
    )


def _content_terms(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "into",
        "than",
        "when",
        "where",
        "which",
        "should",
        "whether",
        "recommendation",
        "change",
        "changes",
        "changed",
        "changing",
        "crux",
        "current",
        "would",
    }
    return [term for term in re.findall(r"[a-z0-9]{4,}", text.lower()) if term not in stop]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _write_section_debug_artifacts(artifacts: Any, index: int, title: str, result: dict[str, Any]) -> None:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or f"section_{index + 1}"
    prefix = f"section_rewrite_{index + 1:02d}_{slug}"
    if result.get("prompt"):
        write_markdown(artifacts / f"{prefix}_prompt.txt", str(result.get("prompt", "")))
    if result.get("raw"):
        write_markdown(artifacts / f"{prefix}_raw.txt", str(result.get("raw", "")))
    write_json(artifacts / f"{prefix}_report.json", result.get("report", {}))
