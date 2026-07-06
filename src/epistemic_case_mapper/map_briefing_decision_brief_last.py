from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.decision_argument_artifacts import compact_decision_argument_artifacts
from epistemic_case_mapper.main_memo_obligations import (
    first_top_line_obligation,
    section_obligations_for_title,
)
from epistemic_case_mapper.map_briefing_reader_polish import clean_reader_memo_text
from epistemic_case_mapper.map_briefing_memo_slots import _rewrite_has_raw_identifiers
from epistemic_case_mapper.map_briefing_section_packets import compact_argument_model


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)


def decision_brief_last_packet(contract: dict[str, Any], body_memo: str) -> dict[str, Any]:
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
        "body_practical_read": markdown_section_with_heading(body_memo, "Practical Read"),
        "body_decision_cruxes": markdown_section_with_heading(body_memo, "Decision Cruxes"),
        "first_page_required_obligations": section_obligations_for_title(
            "Decision Brief",
            contract.get("_main_memo_obligation_plan", []),
            limit=4,
        ),
    }


def deterministic_final_decision_brief(contract: dict[str, Any], body_memo: str) -> str:
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


def decision_brief_last_issues(section: str, contract: dict[str, Any], body_memo: str) -> list[str]:
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


def markdown_section_with_heading(markdown: str, title: str) -> str:
    for section in _split_sections(markdown):
        if section["title"].strip().lower() == title.strip().lower():
            return section["markdown"].strip()
    return ""


def _decision_brief_slots(contract: dict[str, Any], body_memo: str) -> dict[str, str]:
    obligations = section_obligations_for_title("Decision Brief", contract.get("_main_memo_obligation_plan", []), limit=4)
    answer = _default_answer_from_body(body_memo) or _default_answer_from_contract(contract)
    evidence_obligation = first_top_line_obligation(obligations, ("quantitative_anchor", "strongest_support", "evidence_family_balance"))
    caveat_obligation = first_top_line_obligation(obligations, ("scope_boundary", "strongest_counterargument", "decision_crux"))
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
    practical = markdown_section_with_heading(body_memo, "Practical Read")
    paragraphs = _paragraphs_without_heading(practical)
    for paragraph in paragraphs:
        if paragraph.startswith(("-", "*", "|")):
            continue
        if paragraph and not _exception_led_answer(paragraph):
            return paragraph
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", practical, flags=re.MULTILINE)
    for bullet in bullets:
        lead = _clean_bullet(bullet)
        if _exception_led_answer(lead):
            continue
        return re.sub(r"^the default practical read is\b", "For the default case, the current read is", lead, flags=re.IGNORECASE)
    why = markdown_section_with_heading(body_memo, "Why This Read")
    paragraphs = _paragraphs_without_heading(why)
    return paragraphs[0] if paragraphs else ""


def _default_answer_from_contract(contract: dict[str, Any]) -> str:
    scaffold = (
        contract.get("_section_synthesis_scaffold", {})
        if isinstance(contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    for row in synthesis.get("recommendations", []) if isinstance(synthesis.get("recommendations"), list) else []:
        text = str(row.get("recommendation", "")).strip() if isinstance(row, dict) else ""
        if text and not _exception_led_answer(text):
            return _readerize_instruction(text)
    bottom = synthesis.get("bottom_line", {}) if isinstance(synthesis.get("bottom_line"), dict) else {}
    current = str(bottom.get("current_read", "")).strip()
    if current:
        return _readerize_instruction(current)
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    return str(answer_frame.get("direct_answer") or "Use the source packet for a conditional decision read.").strip()


def _decision_caveats_from_body(body_memo: str) -> list[str]:
    practical = markdown_section_with_heading(body_memo, "Practical Read")
    bullets = [_clean_bullet(item) for item in re.findall(r"^\s*[-*]\s+(.+)$", practical, flags=re.MULTILINE)]
    caveats = [item for item in bullets[1:] if item]
    if caveats:
        return caveats[:4]
    scope = markdown_section_with_heading(body_memo, "Practical Scope and Exceptions")
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
    for row in evidence_rows:
        if row.get("top_line_eligible") and str(row.get("section", "")) == "main_support" and str(row.get("claim", "")).strip():
            return _short_text(str(row["claim"]).strip(), 220)
    for row in evidence_rows:
        if not row.get("appendix_only") and str(row.get("claim", "")).strip():
            return _short_text(str(row["claim"]).strip(), 220)
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


def _clean_bullet(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


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


def _split_sections(markdown: str) -> list[dict[str, str]]:
    matches = list(SECTION_RE.finditer(markdown))
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append({"title": match.group(1).strip(), "markdown": markdown[start:end].strip()})
    return sections


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= max_chars else cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _content_overlap(text: str, reference: str) -> int:
    text_terms = set(re.findall(r"[a-z0-9]{4,}", str(text).lower()))
    reference_terms = set(re.findall(r"[a-z0-9]{4,}", str(reference).lower()))
    return len(text_terms & reference_terms)
