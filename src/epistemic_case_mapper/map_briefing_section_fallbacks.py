from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_section_prompt_contract import model_facing_section_markdown
from epistemic_case_mapper.map_briefing_section_structure import (
    structured_practical_read,
    structured_scope_and_exceptions,
)


def structured_section_fallback(section: dict[str, str], contract: dict[str, Any]) -> str:
    title = section["title"].lower()
    if "practical read" in title:
        cleaned = model_facing_section_markdown(section["markdown"], contract)
        if cleaned.strip() and cleaned != section["markdown"]:
            return cleaned
        return structured_practical_read(contract)
    if "evidence carrying" in title:
        return _structured_evidence_carrying_section(contract)
    if "scope" in title and "exception" in title:
        return structured_scope_and_exceptions(contract)
    if "limit" in title:
        return _structured_limits_section(contract)
    if "why this read" in title:
        return _structured_why_this_read_section(contract)
    return section["markdown"]


def _structured_evidence_carrying_section(contract: dict[str, Any]) -> str:
    rows = [row for row in contract.get("required_evidence", []) if isinstance(row, dict)]
    obligations = [row for row in contract.get("required_main_memo_obligations", []) if isinstance(row, dict)]
    lines = ["## Evidence Carrying the Conclusion", ""]
    if rows:
        lines.append("The conclusion rests on the evidence roles below rather than on a single isolated claim.")
        lines.append("")
        for row in rows[:6]:
            slot = _reader_label(str(row.get("slot", "Evidence")).strip() or "Evidence")
            claim = _sentence(str(row.get("claim", "")).strip())
            if claim:
                lines.append(f"- **{slot}:** {claim}")
    for obligation in obligations[:4]:
        statement = _sentence(str(obligation.get("statement", "")).strip())
        if statement and not _text_already_covered(statement, "\n".join(lines)):
            label = _reader_label(str(obligation.get("category", "Required anchor")).replace("_", " "))
            lines.append(f"- **{label}:** {statement}")
    if len(lines) <= 2:
        lines.append("The current packet does not contain a separate owned evidence line for this section.")
    return "\n".join(lines)


def _structured_why_this_read_section(contract: dict[str, Any]) -> str:
    packet = contract.get("model_section_packet", {}) if isinstance(contract.get("model_section_packet"), dict) else {}
    thesis = _sentence(str(packet.get("section_thesis") or contract.get("section_job") or "").strip())
    refs = [row for row in contract.get("evidence_references", []) if isinstance(row, dict)]
    lines = ["## Why This Read", ""]
    if thesis:
        lines.append(thesis)
    else:
        lines.append("The read follows from how the source packet separates direct evidence, counterweights, and scope boundaries.")
    if refs:
        summaries = [
            str(row.get("role_summary") or row.get("reference_instruction") or "").strip()
            for row in refs[:3]
            if str(row.get("role_summary") or row.get("reference_instruction") or "").strip()
        ]
        if summaries:
            lines.append("")
            lines.append("The evidence details are carried in the evidence and scope sections; this section uses them only to explain the reasoning path.")
    return "\n".join(lines)


def _structured_limits_section(contract: dict[str, Any]) -> str:
    gaps = [str(gap).strip() for gap in contract.get("required_gaps", []) if str(gap).strip()]
    obligations = [row for row in contract.get("required_main_memo_obligations", []) if isinstance(row, dict)]
    lines = ["## Limits of the Current Map", ""]
    if gaps:
        lines.append("The main limits are the places where the current source packet leaves decision-relevant uncertainty.")
        lines.append("")
        lines.extend(f"- {_sentence(gap)}" for gap in gaps[:5])
    for obligation in obligations[:4]:
        statement = _sentence(str(obligation.get("statement", "")).strip())
        if statement and not _text_already_covered(statement, "\n".join(lines)):
            lines.append(f"- {statement}")
    if len(lines) <= 2:
        lines.append("The map is usable as a decision aid, but unresolved extraction gaps and source coverage limits should be reviewed before treating it as final.")
    return "\n".join(lines)


def _reader_label(text: str) -> str:
    cleaned = re.sub(r"[_-]+", " ", str(text)).strip()
    if not cleaned:
        return "Evidence"
    return " ".join(word[:1].upper() + word[1:] for word in cleaned.split())


def _text_already_covered(statement: str, text: str) -> bool:
    return _content_overlap(text, statement) >= min(5, max(2, len(_content_terms(statement)) // 2))


def _content_overlap(text: str, reference: str) -> int:
    text_terms = set(_content_terms(text))
    return sum(1 for term in _content_terms(reference) if term in text_terms)


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


def _sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned or _looks_incomplete(cleaned):
        return ""
    return cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."


def _looks_incomplete(text: str) -> bool:
    cleaned = text.strip().rstrip(".").lower()
    if text.count("(") != text.count(")") or text.count("[") != text.count("]"):
        return True
    return bool(re.search(r"\b(?:and|or|of|with|to|than|as|between|including|other|vs)\s*$", cleaned))
