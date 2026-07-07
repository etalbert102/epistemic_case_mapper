from __future__ import annotations

import re
from typing import Any


def spine_memo_validation_issues(rendered: str, scaffold: dict[str, Any]) -> list[dict[str, str]]:
    spine = _dict(scaffold.get("canonical_decision_spine"))
    if not spine:
        return []
    validation = _dict(scaffold.get("canonical_decision_spine_validation"))
    projection = _dict(scaffold.get("section_projection_readiness_report"))
    issues: list[dict[str, str]] = []
    if validation.get("status") == "invalid":
        issues.append(_issue("error", "canonical_spine_invalid", "The canonical decision spine failed schema/provenance validation."))
    if projection.get("status") == "not_synthesis_ready":
        issues.append(_issue("error", "spine_projection_not_synthesis_ready", "Canonical spine projections were not synthesis-ready."))
    default = _dict(spine.get("default_answer"))
    if _should_check_default_visibility(default):
        answer = _decision_brief_answer(rendered)
        if answer and _content_overlap(answer, str(default.get("claim", ""))) < 2:
            issues.append(
                _issue(
                    "warning",
                    "canonical_default_answer_not_visible",
                    "The Decision Brief opening does not visibly preserve the canonical default answer.",
                )
            )
    if _spine_missing_slot_used_as_answer(rendered, spine):
        issues.append(
            _issue(
                "warning",
                "missing_slot_used_as_answer",
                "A missing decision slot appears to be used as main-answer evidence rather than a limitation.",
            )
        )
    return issues


def _should_check_default_visibility(default: dict[str, Any]) -> bool:
    return bool(default.get("claim")) and str(default.get("role")) != "missing_slot"


def _spine_missing_slot_used_as_answer(rendered: str, spine: dict[str, Any]) -> bool:
    main = _main_answer_sections(rendered)
    for field in spine.get("missing_decision_slots", []) if isinstance(spine.get("missing_decision_slots"), list) else []:
        if not isinstance(field, dict):
            continue
        claim = str(field.get("claim", ""))
        if _content_overlap(main, claim) >= 4 and "limits of the current map" not in main.lower():
            return True
    return False


def _decision_brief_answer(markdown: str) -> str:
    section = _markdown_section(markdown, "Decision Brief")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", section) if part.strip()]
    for paragraph in paragraphs[1:]:
        if paragraph.startswith("**Decision question:**") or paragraph.startswith("**Confidence:**"):
            continue
        return paragraph
    return ""


def _main_answer_sections(markdown: str) -> str:
    return "\n\n".join(
        section
        for title in ("Decision Brief", "Why This Read", "Evidence Carrying the Conclusion")
        if (section := _markdown_section(markdown, title))
    )


def _markdown_section(markdown: str, title: str) -> str:
    match = re.search(
        rf"(^##\s+{re.escape(title)}\s*$.*?)(?=^##\s+|\Z)",
        markdown,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _content_overlap(text: str, reference: str) -> int:
    text_terms = set(_content_terms(text))
    reference_terms = set(_content_terms(reference))
    return len(text_terms & reference_terms)


def _content_terms(text: str) -> list[str]:
    stopwords = {"answer", "brief", "current", "decision", "evidence", "question", "source", "support"}
    terms = []
    for term in re.findall(r"[a-z0-9]{4,}", str(text).lower()):
        if term not in stopwords and term not in terms:
            terms.append(term)
    return terms


def _issue(severity: str, issue_type: str, message: str) -> dict[str, str]:
    return {"severity": severity, "issue_type": issue_type, "message": message}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
