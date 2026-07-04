from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
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
from epistemic_case_mapper.map_briefing_section_quantities import section_quantitative_anchors
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
    report: dict[str, Any] = {
        "schema_id": "section_rewrite_report_v1",
        "status": "not_run",
        "accepted_section_count": 0,
        "section_count": 0,
        "sections": [],
        "whole_validation_status": "not_run",
    }
    if backend.strip() == "prompt":
        report["status"] = "skipped_prompt_backend"
        return {"memo": memo, "report": report}
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
    rewritten_sections: list[str] = []
    deferred_decision_section: dict[str, str] | None = None
    for index, section in enumerate(sections):
        if section["title"] == "Decision Brief":
            deferred_decision_section = section
            continue
        section_contract = _section_contract(section, contract)
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
    report["accepted_section_count"] = sum(1 for item in report["sections"] if item.get("accepted"))
    if validation.get("status") == "needs_review":
        report["status"] = "global_validation_failed_fallback"
        return {"memo": memo, "report": report}
    report["status"] = "accepted_partial" if report["accepted_section_count"] else "no_sections_accepted"
    return {"memo": candidate, "report": report}


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
    }
    if not _should_rewrite_section(section, section_contract):
        section_report["status"] = "skipped_low_value_section"
        return {"section": section["markdown"], "prompt": prompt, "raw": "", "report": section_report}
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
    prompt = _decision_brief_last_prompt(contract, body_memo, fallback)
    section_report: dict[str, Any] = {
        "title": "Decision Brief",
        "status": "not_run",
        "accepted": False,
        "issues": [],
        "required_evidence_count": 0,
        "required_gap_count": 0,
        "required_crux_count": 0,
        "generated_last": True,
    }
    attempt_result = run_section_model_attempts(
        prompt=prompt, expected_title="Decision Brief", backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries,
        validate=lambda rewritten: _validate_final_decision_brief(rewritten, contract, body_memo), run_backend=run_model_backend,
    )
    _apply_attempt_report(section_report, attempt_result, deterministic_text=fallback)
    if attempt_result["accepted"]:
        status = "accepted_final_brief_after_repair" if attempt_result["section"] != attempt_result["rewritten"] else "accepted_final_brief"
        section_report["status"] = status
        return {"section": clean_reader_memo_text(str(attempt_result["section"])), "prompt": attempt_result["prompt"], "raw": attempt_result["raw"], "report": section_report}
    section_report["status"] = "rejected_final_brief_fallback"
    return {"section": fallback, "prompt": attempt_result["prompt"], "raw": attempt_result["raw"], "report": section_report}


def _decision_brief_last_prompt(contract: dict[str, Any], body_memo: str, fallback: str) -> str:
    packet = _decision_brief_last_packet(contract, body_memo)
    return (
        "You are writing the opening Decision Brief for a decision-support memo after the body sections are already written.\n"
        "Use the body sections as the source of truth. Do not introduce new facts, sources, numbers, or recommendations.\n"
        "Write only the Decision Brief section. The first substantive sentence after the question must directly answer the decision question for the default case; put caveats after that answer.\n"
        "Return only valid JSON with this schema: {\"section_markdown\": \"## Decision Brief\\n\\n**Decision question:** ...\\n\\nDirect answer...\\n\\n**Confidence:** medium\"}.\n\n"
        "Executive answer packet:\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n\n"
        "Deterministic fallback section, for structure:\n"
        f"{fallback.strip()}\n\n"
        "Section to rewrite:\n"
        f"{fallback.strip()}\n\n"
        "Accepted body sections to summarize:\n"
        f"{_compact_body_for_prompt(body_memo)}\n"
    )


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
        "bottom_line": synthesis.get("bottom_line"),
        "recommendations": synthesis.get("recommendations", [])[:5],
        "scope_boundaries": synthesis.get("scope_boundaries", [])[:3],
        "exceptions": synthesis.get("exceptions", [])[:3],
        "cruxes": synthesis.get("cruxes", [])[:3],
        "body_practical_read": _markdown_section_with_heading(body_memo, "Practical Read"),
        "body_decision_cruxes": _markdown_section_with_heading(body_memo, "Decision Cruxes"),
    }


def _deterministic_final_decision_brief(contract: dict[str, Any], body_memo: str) -> str:
    question = str(contract.get("question", "")).strip()
    confidence = str(contract.get("confidence") or "medium").strip()
    answer = _default_answer_from_body(body_memo) or _default_answer_from_contract(contract)
    caveats = _decision_caveats_from_body(body_memo) or _decision_caveats_from_contract(contract)
    support = _support_evidence_from_contract(contract)
    answer = _sentence(answer)
    if caveats:
        answer = f"{answer} Key caveats: {'; '.join(caveats[:3])}."
    if support and support.lower() not in (answer + " " + body_memo).lower():
        answer = f"{answer} Key supporting evidence: {_sentence(support)}"
    lines = ["## Decision Brief", ""]
    if question:
        lines.extend([f"**Decision question:** {question}", ""])
    lines.extend([answer, "", f"**Confidence:** {confidence}"])
    return clean_reader_memo_text("\n".join(lines))


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
        "When quantitative_anchors include key_quantities, use one relevant card-level estimate in evidence-bearing sections instead of only qualitative phrasing.\n"
        "Preserve every required local evidence anchor, gap, confidence line, and crux item in the section contract.\n"
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
    original_words = max(1, len(original["markdown"].split()))
    if contract["has_obligations"] and len(rewritten.split()) < max(35, int(original_words * 0.45)):
        issues.append("section rewrite is too short for its local contract")
    issues.extend(section_structure_issues(rewritten, contract))
    return issues


def _validate_rewritten_section(rewritten: str, section: dict[str, str], contract: dict[str, Any]) -> tuple[str, list[str]]:
    repaired = repair_structured_section(_repair_section(rewritten), contract)
    return repaired, _section_rewrite_issues(repaired, section, contract)


def _validate_final_decision_brief(rewritten: str, contract: dict[str, Any], body_memo: str) -> tuple[str, list[str]]:
    repaired = _repair_section(rewritten)
    return repaired, _decision_brief_last_issues(repaired, contract, body_memo)


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
    return {
        "heading": title,
        "confidence": full_contract.get("confidence"),
        "requires_confidence": "**Confidence:**" in text,
        "required_evidence": required_evidence,
        "evidence_references": evidence_references,
        "required_gaps": required_gaps,
        "required_cruxes": required_cruxes if isinstance(required_cruxes, list) else [],
        "practical_actions": practical_actions if isinstance(practical_actions, list) else [],
        "min_decision_changing_cruxes": min(2, len(required_cruxes)) if "crux" in title.lower() else 0,
        "section_synthesis_packet": _section_synthesis_packet(title, full_contract),
        "decision_frame": frame,
        "section_job": section_jobs.get(title, "Smooth this section while preserving its local evidence obligations."),
        "has_obligations": bool(required_evidence or required_gaps or required_cruxes or practical_actions),
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
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    synthesis_cruxes = [row for row in synthesis.get("cruxes", []) if isinstance(row, dict)]
    if synthesis_cruxes:
        return synthesis_cruxes[:3]
    required = full_contract.get("required_cruxes", [])
    return [row for row in required if isinstance(row, dict)] if isinstance(required, list) else []


def _section_synthesis_packet(title: str, full_contract: dict[str, Any]) -> dict[str, Any]:
    scaffold = (
        full_contract.get("_section_synthesis_scaffold", {})
        if isinstance(full_contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    title_key = title.lower()
    packet = {
        "section_goal": _section_goal(title_key),
        "graph_summary": graph_packet.get("graph_summary", {}),
        "issue_clusters": _section_issue_clusters(title_key, graph_packet),
        "load_bearing_claims": _section_claims(title_key, graph_packet.get("load_bearing_claims", [])),
        "bridge_claims": _section_claims(title_key, graph_packet.get("bridge_claims", [])),
        "central_tensions": _section_tensions(title_key, graph_packet.get("central_tensions", [])),
        "decision_synthesis": _section_decision_synthesis(title_key, synthesis),
        "quantitative_anchors": section_quantitative_anchors(title_key, scaffold),
        "style_instruction": _section_style_instruction(title_key),
    }
    return _drop_empty_packet_values(packet)


def _section_goal(title_key: str) -> str:
    if "decision brief" in title_key:
        return "State the answer frame directly, with confidence and the one or two reasons that carry the read."
    if "practical read" in title_key:
        return "Translate the graph into concrete practical implications and exception checks."
    if "why this read" in title_key:
        return "Explain the reasoning path from load-bearing claims through the central tensions."
    if "evidence carrying" in title_key:
        return "Group the carrying evidence by issue cluster rather than listing isolated claims."
    if "scope" in title_key or "exception" in title_key:
        return "Separate the default case from boundaries, exceptions, and bridge conditions."
    if "crux" in title_key:
        return "Convert central graph tensions and bridge claims into human-readable cruxes."
    if "limit" in title_key:
        return "Name what the map does not establish and keep orphan claims out of the main answer."
    return "Improve this section while preserving its local source-grounded obligations."


def _section_issue_clusters(title_key: str, graph_packet: dict[str, Any]) -> list[dict[str, Any]]:
    clusters = [item for item in graph_packet.get("issue_clusters", []) if isinstance(item, dict)]
    if "decision brief" in title_key or "practical read" in title_key:
        return _compact_issue_clusters(clusters[:3])
    if "evidence carrying" in title_key or "why this read" in title_key:
        return _compact_issue_clusters(clusters[:5])
    if "scope" in title_key or "exception" in title_key:
        return _compact_issue_clusters([item for item in clusters if _cluster_has_scope_signal(item)][:4] or clusters[:3])
    if "crux" in title_key:
        return _compact_issue_clusters([item for item in clusters if _cluster_has_tension(item)][:4] or clusters[:3])
    return _compact_issue_clusters(clusters[:3])


def _compact_issue_clusters(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for cluster in clusters:
        compact.append(
            {
                "label": cluster.get("label"),
                "claim_count": cluster.get("claim_count"),
                "relation_mix": cluster.get("relation_mix", {}),
                "synthesis_job": cluster.get("synthesis_job"),
                "representative_claims": _compact_claims(cluster.get("representative_claims", []), limit=3),
            }
        )
    return compact


def _section_claims(title_key: str, value: Any) -> list[dict[str, Any]]:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    if "limit" in title_key:
        return []
    if "crux" in title_key or "why this read" in title_key:
        return _compact_claims(rows, limit=5)
    return _compact_claims(rows, limit=3)


def _section_tensions(title_key: str, value: Any) -> list[dict[str, Any]]:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    if "decision brief" in title_key:
        return _compact_tensions(rows, limit=2)
    if "crux" in title_key or "scope" in title_key or "why this read" in title_key:
        return _compact_tensions(rows, limit=5)
    if "evidence carrying" in title_key:
        return _compact_tensions(rows, limit=3)
    return _compact_tensions(rows, limit=2)


def _section_decision_synthesis(title_key: str, synthesis: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(synthesis, dict):
        return {}
    if "decision brief" in title_key:
        return {"bottom_line": synthesis.get("bottom_line"), "central_tensions": synthesis.get("central_tensions", [])[:2]}
    if "practical read" in title_key:
        return {"recommendations": synthesis.get("recommendations", [])[:4], "exceptions": synthesis.get("exceptions", [])[:3]}
    if "scope" in title_key or "exception" in title_key:
        return {"scope_boundaries": synthesis.get("scope_boundaries", [])[:5], "exceptions": synthesis.get("exceptions", [])[:5]}
    if "crux" in title_key:
        return {"cruxes": synthesis.get("cruxes", [])[:5], "central_tensions": synthesis.get("central_tensions", [])[:4]}
    if "limit" in title_key:
        return {"limits": synthesis.get("limits", [])[:5]}
    return {
        "evidence_lines": synthesis.get("evidence_lines", [])[:5],
        "central_tensions": synthesis.get("central_tensions", [])[:3],
    }


def _section_style_instruction(title_key: str) -> str:
    if "crux" in title_key:
        return "Use concrete crux names; avoid generic relation labels and internal graph language."
    if "evidence carrying" in title_key:
        return "Lead with the strongest cluster-level proposition, then name the counterweight or scope boundary."
    if "decision brief" in title_key:
        return "Keep the opening short, direct, and calibrated."
    return "Prefer polished human prose over internal map terminology."


def _compact_claims(value: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    compact: list[dict[str, Any]] = []
    for row in rows[:limit]:
        compact.append(
            {
                "claim_id": row.get("claim_id"),
                "claim": _short_text(str(row.get("claim", "")), 260),
                "source": row.get("source"),
                "weight": row.get("weight"),
                "role": row.get("role"),
                "evidence_family": row.get("evidence_family"),
            }
        )
    return compact


def _compact_tensions(value: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    compact: list[dict[str, Any]] = []
    for row in rows[:limit]:
        left = row.get("left", {}) if isinstance(row.get("left"), dict) else {}
        right = row.get("right", {}) if isinstance(row.get("right"), dict) else {}
        compact.append(
            {
                "relation_id": row.get("relation_id"),
                "relation_type": row.get("relation_type"),
                "left_claim": _short_text(str(left.get("claim", "")), 220),
                "right_claim": _short_text(str(right.get("claim", "")), 220),
                "why_it_matters": _short_text(str(row.get("why_it_matters") or row.get("rationale", "")), 260),
                "failure_condition": _short_text(str(row.get("failure_condition", "")), 220),
            }
        )
    return compact


def _drop_empty_packet_values(packet: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in packet.items() if value not in ({}, [], "", None)}


def _cluster_has_scope_signal(cluster: dict[str, Any]) -> bool:
    text = json.dumps(cluster, ensure_ascii=False).lower()
    return any(marker in text for marker in ("scope", "subgroup", "boundary", "implementation", "condition", "exception"))


def _cluster_has_tension(cluster: dict[str, Any]) -> bool:
    mix = cluster.get("relation_mix", {}) if isinstance(cluster.get("relation_mix"), dict) else {}
    return int(mix.get("negative", 0)) > 0


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
