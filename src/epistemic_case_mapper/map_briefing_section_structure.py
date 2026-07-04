from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_practical_text import reader_facing_practical_items


def filter_primary_practical_actions(actions: list[str], scaffold: dict[str, Any] | None = None) -> list[str]:
    """Keep practical-read actions focused on the asked decision."""
    context = _decision_context(scaffold or {})
    if not context:
        return actions
    filtered = [action for action in actions if not _low_relevance_downside_action(action, context)]
    return filtered or actions


def repair_reader_memo_sections(markdown: str, contract: dict[str, Any], scaffold: dict[str, Any] | None = None) -> str:
    sections = _split_sections(markdown)
    if not sections:
        return markdown
    repaired: list[str] = []
    for title, body in sections:
        section = f"## {title}\n\n{body.strip()}".strip()
        section_contract = _reader_section_contract(title, contract, scaffold or {})
        repaired.append(repair_structured_section(section, section_contract))
    return "\n\n".join(repaired)


def repair_structured_section(markdown: str, contract: dict[str, Any]) -> str:
    title = str(contract.get("heading", "")).strip().lower()
    if title == "practical read" and _practical_read_needs_structure(markdown, contract):
        if _practical_bullet_count(markdown) >= _minimum_existing_practical_bullets(contract):
            return _keep_existing_practical_bullets(markdown)
        return structured_practical_read(contract)
    if "scope" in title and "exception" in title and _scope_section_needs_structure(markdown, contract):
        return structured_scope_and_exceptions(contract)
    return markdown


def section_structure_issues(markdown: str, contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    title = str(contract.get("heading", "")).strip().lower()
    if title == "practical read":
        if _starts_with_dangling_transition(markdown):
            issues.append("Practical Read opens with a dangling transition")
        if _practical_bullet_count(markdown) < _minimum_practical_bullets(contract):
            issues.append("Practical Read does not preserve enough practical bullets")
    if "scope" in title and "exception" in title and _scope_section_needs_structure(markdown, contract):
        issues.append("Practical Scope and Exceptions is too compressed")
    return issues


def structured_practical_read(contract: dict[str, Any]) -> str:
    actions = _primary_practical_actions(contract)
    if not actions:
        actions = ["Use the source-grounded answer as conditional guidance rather than a settled all-context recommendation."]
    lines = ["## Practical Read", ""]
    lines.extend(f"- {item}" for item in actions[:4])
    return "\n".join(lines)


def structured_scope_and_exceptions(contract: dict[str, Any]) -> str:
    packet = contract.get("section_synthesis_packet", {}) if isinstance(contract.get("section_synthesis_packet"), dict) else {}
    synthesis = packet.get("decision_synthesis", {}) if isinstance(packet.get("decision_synthesis"), dict) else {}
    boundaries = [row for row in synthesis.get("scope_boundaries", []) if isinstance(row, dict)]
    exceptions = [row for row in synthesis.get("exceptions", []) if isinstance(row, dict)]
    required = [row for row in contract.get("required_evidence", []) if isinstance(row, dict)]
    refs = [row for row in contract.get("evidence_references", []) if isinstance(row, dict)]

    default_scope = _first_claim(required + refs, ("study population", "free of", "default", "healthy", "population")) or _first_match(boundaries, ("population", "default", "setting"))
    comparator = _first_claim(required + refs, ("comparator", "replacing", "substitut", "compared")) or _first_match(boundaries, ("comparator", "substitution"))
    exception = _first_claim(required + refs, ("subgroup", "people with", "patients with", "individuals with", "higher risk", "higher-risk", "high-risk")) or _first_match(exceptions, ("subgroup", "risk", "exception"))
    change = _first_match(boundaries, ("dose", "endpoint", "study_design")) or _first_claim(required + refs, ("dose", "endpoint", "biomarker", "risk"))

    lines = ["## Practical Scope and Exceptions", ""]
    for label, value in (
        ("Default scope", default_scope),
        ("Comparator effects", comparator),
        ("Exception groups", exception),
        ("What would change this", change),
    ):
        if value:
            lines.append(f"- **{label}:** {_sentence(value)}")
    if len(lines) <= 2:
        lines.append("- **Default scope:** Apply the recommendation only within the population, comparator, and evidence limits represented in the source packet.")
    return "\n".join(lines)


def _reader_section_contract(title: str, contract: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    section_contract = {
        "heading": title,
        "practical_actions": contract.get("practical_actions", []),
        "required_evidence": contract.get("required_evidence", []),
        "_section_synthesis_scaffold": scaffold,
    }
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    if synthesis:
        section_contract["section_synthesis_packet"] = {
            "decision_synthesis": {
                "scope_boundaries": synthesis.get("scope_boundaries", []),
                "exceptions": synthesis.get("exceptions", []),
            }
        }
    return section_contract


def _primary_practical_actions(contract: dict[str, Any]) -> list[str]:
    scaffold = contract.get("_section_synthesis_scaffold", {}) if isinstance(contract.get("_section_synthesis_scaffold"), dict) else {}
    packet = contract.get("section_synthesis_packet", {}) if isinstance(contract.get("section_synthesis_packet"), dict) else {}
    synthesis = packet.get("decision_synthesis", {}) if isinstance(packet.get("decision_synthesis"), dict) else {}
    raw_actions = [
        str(row.get("recommendation", "")).strip()
        for row in synthesis.get("recommendations", [])
        if isinstance(row, dict) and str(row.get("recommendation", "")).strip()
    ]
    raw_actions.extend(str(item).strip() for item in contract.get("practical_actions", []) if str(item).strip())
    actions = reader_facing_practical_items(filter_primary_practical_actions(raw_actions, scaffold))
    return _dedupe(actions)


def _practical_read_needs_structure(markdown: str, contract: dict[str, Any]) -> bool:
    return _starts_with_dangling_transition(markdown) or _practical_bullet_count(markdown) < _minimum_practical_bullets(contract)


def _scope_section_needs_structure(markdown: str, contract: dict[str, Any]) -> bool:
    body = _body_without_heading(markdown)
    if not (contract.get("required_evidence") or contract.get("evidence_references") or contract.get("practical_actions")):
        return False
    return _paragraph_count(body) <= 1 and _practical_bullet_count(markdown) < 2 and body.count("**") < 4


def _starts_with_dangling_transition(markdown: str) -> bool:
    first = _first_body_text(markdown).lower()
    return first.startswith(("however,", "but ", "therefore,", "consequently,", "furthermore,", "additionally,"))


def _minimum_practical_bullets(contract: dict[str, Any]) -> int:
    actions = [item for item in contract.get("practical_actions", []) if str(item).strip()]
    if actions:
        return min(2, len(actions))
    packet = contract.get("section_synthesis_packet", {}) if isinstance(contract.get("section_synthesis_packet"), dict) else {}
    synthesis = packet.get("decision_synthesis", {}) if isinstance(packet.get("decision_synthesis"), dict) else {}
    recommendations = [row for row in synthesis.get("recommendations", []) if isinstance(row, dict)]
    return 2 if recommendations else 0


def _minimum_existing_practical_bullets(contract: dict[str, Any]) -> int:
    return max(1, _minimum_practical_bullets(contract))


def _low_relevance_downside_action(action: str, context: str) -> bool:
    lowered = f" {action.lower()} "
    action_terms = set(_content_terms(action))
    if not (
        any(marker in lowered for marker in (" increased risk ", " higher risk ", " adverse ", " harm ", " downside ", " safety "))
        or ("increased" in action_terms and "risk" in action_terms)
        or ("associated" in action_terms and "risk" in action_terms)
    ):
        return False
    if any(marker in lowered for marker in ("subgroup", "high-risk", "higher-risk", "people with", "patients with", "individuals with")):
        return False
    context_terms = set(_content_terms(context))
    return len(action_terms & context_terms) < 3


def _keep_existing_practical_bullets(markdown: str) -> str:
    bullets = [line.strip() for line in markdown.splitlines() if re.match(r"^\s*[-*]\s+", line)]
    lines = ["## Practical Read", ""]
    lines.extend(re.sub(r"^\*\s+", "- ", bullet) for bullet in bullets)
    return "\n".join(lines)


def _decision_context(scaffold: dict[str, Any]) -> str:
    frame = scaffold.get("decision_frame", {}) if isinstance(scaffold.get("decision_frame"), dict) else {}
    answer = frame.get("direct_answer", "") if isinstance(frame, dict) else ""
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    bottom = synthesis.get("bottom_line", {}) if isinstance(synthesis.get("bottom_line"), dict) else {}
    return " ".join(str(part) for part in (scaffold.get("question", ""), answer, bottom.get("current_read", "")) if str(part).strip())


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown, flags=re.MULTILINE))
    if not matches:
        return []
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append((match.group(1).strip(), markdown[match.end() : end].strip()))
    return sections


def _first_match(rows: list[dict[str, Any]], markers: tuple[str, ...]) -> str:
    for row in rows:
        text = " ".join(str(row.get(key, "")) for key in ("boundary_type", "condition", "current_read"))
        if any(marker in text.lower() for marker in markers):
            return str(row.get("current_read", "")).strip()
    return ""


def _first_claim(rows: list[dict[str, Any]], markers: tuple[str, ...]) -> str:
    for row in rows:
        text = str(row.get("claim") or row.get("role_summary") or "").strip()
        if text and any(marker in text.lower() for marker in markers):
            source = str(row.get("source", "")).strip() if row.get("claim") else ""
            if source and source.lower() not in text.lower():
                return f"{text.rstrip('.')} ({source})"
            return text
    return ""


def _first_body_text(markdown: str) -> str:
    for paragraph in re.split(r"\n\s*\n", _body_without_heading(markdown)):
        text = paragraph.strip()
        if text and not text.startswith(("-", "*", "|")):
            return text
    return ""


def _body_without_heading(markdown: str) -> str:
    return re.sub(r"^##\s+.+?\s*$", "", markdown.strip(), count=1, flags=re.MULTILINE).strip()


def _paragraph_count(text: str) -> int:
    return len([part for part in re.split(r"\n\s*\n", text.strip()) if part.strip()])


def _practical_bullet_count(markdown: str) -> int:
    return len(re.findall(r"^\s*[-*]\s+", markdown, flags=re.MULTILINE))


def _content_terms(text: str) -> list[str]:
    stop = {"the", "and", "that", "this", "with", "from", "into", "than", "when", "where", "which", "should"}
    return [term for term in re.findall(r"[a-z0-9]+", text.lower()) if len(term) >= 4 and term not in stop]


def _sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip().rstrip(".")
    return cleaned + "." if cleaned else ""


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        key = re.sub(r"\W+", " ", item).strip().lower()
        if key and key not in seen:
            seen.add(key)
            kept.append(item)
    return kept
