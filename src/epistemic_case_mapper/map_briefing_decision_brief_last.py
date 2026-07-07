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
        "canonical_decision_spine": _compact_canonical_spine(scaffold),
        "decision_brief_projection": _decision_brief_projection(scaffold),
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


def decision_brief_answer_frame_guidance(contract: dict[str, Any]) -> str:
    frame = _answer_frame_parts(contract)
    lines: list[str] = []
    for label, value in (
        ("Canonical default", _canonical_default_answer(contract)),
        ("Current read", frame.get("current_read", "")),
        ("Why this frame", frame.get("why_this_frame", "")),
        ("Plain-language guardrail", frame.get("plain_language_instruction", "")),
        ("Reader contract", frame.get("direct_answer", "")),
    ):
        if value:
            lines.append(f"- {label}: {value}")
    requirements = frame.get("prose_requirements", [])
    if isinstance(requirements, list):
        for requirement in requirements[:3]:
            if str(requirement).strip():
                lines.append(f"- Prose requirement: {requirement}")
    return "\n".join(lines) or "- Use the accepted body sections to give a scoped decision answer."


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
    if answer:
        issues.extend(_answer_frame_alignment_issues(answer, contract))
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
    canonical = _canonical_default_answer(contract)
    if canonical:
        return _readerize_instruction(canonical)
    frame = _answer_frame_parts(contract)
    if frame.get("current_read"):
        return _readerize_instruction(str(frame["current_read"]))
    if frame.get("plain_language_instruction"):
        return _readerize_instruction(str(frame["plain_language_instruction"]))
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


def _answer_frame_parts(contract: dict[str, Any]) -> dict[str, Any]:
    scaffold = (
        contract.get("_section_synthesis_scaffold", {})
        if isinstance(contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    bottom = synthesis.get("bottom_line", {}) if isinstance(synthesis.get("bottom_line"), dict) else {}
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    default = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    return {
        "classification": str(bottom.get("classification") or default.get("classification") or "").strip(),
        "current_read": str(bottom.get("current_read") or "").strip(),
        "why_this_frame": str(default.get("why_this_frame") or "").strip(),
        "plain_language_instruction": str(default.get("plain_language_instruction") or "").strip(),
        "direct_answer": str(answer_frame.get("direct_answer") or "").strip(),
        "prose_requirements": decision_model.get("prose_requirements", []),
    }


def _answer_frame_alignment_issues(answer: str, contract: dict[str, Any]) -> list[str]:
    frame = _answer_frame_parts(contract)
    frame_text = " ".join(str(value) for key, value in frame.items() if key != "classification")
    frame_norm = frame_text.lower()
    answer_norm = answer.lower()
    issues: list[str] = []
    conditional_frame = any(
        marker in frame_norm
        for marker in (
            "context-dependent",
            "conditional",
            "insufficient",
            "uncertain",
            "low-concern",
            "neutral",
            "not shown",
            "do not frame",
            "avoid benefit",
        )
    )
    unsupported_favorable = _has_unnegated_favorable_verdict(answer_norm)
    if conditional_frame and unsupported_favorable and not any(marker in frame_norm for marker in ("beneficial_under", "state benefit only")):
        issues.append("final brief upgrades the controlling answer frame into an unsupported favorable verdict")
    if frame_text and _content_overlap(answer, frame_text) < 2 and conditional_frame:
        issues.append("final brief does not preserve the controlling conditional answer frame")
    canonical = _canonical_default_answer(contract)
    if canonical and _content_overlap(answer, canonical) < 2:
        issues.append("final brief does not preserve the canonical default answer")
    return issues


def _has_unnegated_favorable_verdict(text: str) -> bool:
    if any(marker in text for marker in ("clearly safe", "proven safe", "favorable default", "lower-risk default")):
        return True
    for marker in ("beneficial", "protective"):
        for match in re.finditer(rf"\b{re.escape(marker)}\b", text):
            prefix = text[max(0, match.start() - 42): match.start()]
            if re.search(r"\b(?:not|no|avoid|without|should not|do not|does not|isn't|not be|not framed as|not treated as)\b", prefix):
                continue
            return True
    return False


def _canonical_default_answer(contract: dict[str, Any]) -> str:
    spine = _canonical_spine(contract)
    default = spine.get("default_answer", {}) if isinstance(spine.get("default_answer"), dict) else {}
    if str(default.get("role", "")) == "missing_slot":
        return ""
    return str(default.get("claim", "")).strip()


def _compact_canonical_spine(scaffold: dict[str, Any]) -> dict[str, Any]:
    spine = scaffold.get("canonical_decision_spine", {}) if isinstance(scaffold.get("canonical_decision_spine"), dict) else {}
    default = spine.get("default_answer", {}) if isinstance(spine.get("default_answer"), dict) else {}
    return {
        "status": spine.get("status"),
        "confidence": spine.get("confidence"),
        "default_answer": _compact_spine_field(default),
        "exception_answers": [_compact_spine_field(row) for row in _list(spine.get("exception_answers"))[:2]],
        "evidence_quality_limits": [_compact_spine_field(row) for row in _list(spine.get("evidence_quality_limits"))[:3]],
        "missing_decision_slots": [_compact_spine_field(row) for row in _list(spine.get("missing_decision_slots"))[:3]],
    }


def _decision_brief_projection(scaffold: dict[str, Any]) -> dict[str, Any]:
    projections = scaffold.get("section_projection_packets", {}) if isinstance(scaffold.get("section_projection_packets"), dict) else {}
    for section in _list(projections.get("sections")):
        if isinstance(section, dict) and str(section.get("section", "")).strip().lower() == "decision brief":
            return {
                "context_status": section.get("context_status"),
                "section_thesis": section.get("section_thesis"),
                "owned_spine_field_ids": section.get("owned_spine_field_ids", []),
                "owned_evidence": section.get("owned_evidence", [])[:3] if isinstance(section.get("owned_evidence"), list) else [],
            }
    return {}


def _compact_spine_field(field: Any) -> dict[str, Any]:
    if not isinstance(field, dict):
        return {}
    return {
        "field_id": field.get("field_id"),
        "role": field.get("role"),
        "claim": _short_text(str(field.get("claim", "")), 300),
        "source_ids": field.get("source_ids", [])[:4] if isinstance(field.get("source_ids"), list) else [],
        "candidate_card_ids": field.get("candidate_card_ids", [])[:4] if isinstance(field.get("candidate_card_ids"), list) else [],
        "confidence": field.get("confidence"),
        "limits": field.get("limits", [])[:3] if isinstance(field.get("limits"), list) else [],
    }


def _canonical_spine(contract: dict[str, Any]) -> dict[str, Any]:
    scaffold = (
        contract.get("_section_synthesis_scaffold", {})
        if isinstance(contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    spine = scaffold.get("canonical_decision_spine", {})
    return spine if isinstance(spine, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
        (r"^state that the answer is context-dependent, then identify\b", "The answer is context-dependent; the decision turns on"),
        (r"^state that the evidence is insufficient or uncertain, then name\b", "The evidence is insufficient or uncertain; the decision turns on"),
        (r"^state the supportive answer and immediately name\b", "The current read is supportive, with"),
        (r"^state benefit only under\b", "Any benefit claim applies only under"),
        (r"^state that caution is warranted under\b", "Caution is warranted under"),
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
