from __future__ import annotations

import re
from typing import Any


VAGUE_ANALYST_PHRASES = (
    "nuanced approach",
    "nuanced practical application",
    "specific population dynamics",
    "it is important to note",
    "worth noting",
    "various factors",
    "complex interplay",
    "significant implications",
)
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)


def section_role_quality_issues(markdown: str, contract: dict[str, Any] | None = None) -> list[str]:
    contract = contract or {}
    title = str(contract.get("heading") or _section_title(markdown)).strip()
    body = _body_without_heading(markdown)
    issues: list[str] = []
    issues.extend(_vague_phrase_issues(body))
    issues.extend(_role_specific_issues(title, body, contract))
    return issues


def section_role_quality_report(memo: str, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = contract or {}
    issues = []
    for section in _sections(memo):
        section_contract = {**contract, "heading": section["title"]}
        for issue in section_role_quality_issues(section["markdown"], section_contract):
            issues.append({"section": section["title"], "issue": issue})
    return {
        "schema_id": "section_role_quality_report_v1",
        "status": "warning" if issues else "pass",
        "issue_count": len(issues),
        "issues": issues,
    }


def _role_specific_issues(title: str, body: str, contract: dict[str, Any]) -> list[str]:
    key = title.lower()
    if "decision brief" in key:
        return _decision_brief_issues(body)
    if "practical read" in key:
        return _practical_read_issues(body, contract)
    if "why this read" in key:
        return _why_this_read_issues(body)
    if "evidence carrying" in key:
        return _evidence_carrying_issues(body, contract)
    if "scope" in key or "exception" in key:
        return _scope_issues(body)
    return []


def _decision_brief_issues(body: str) -> list[str]:
    first = _first_paragraph(body).lower()
    if not first:
        return ["Decision Brief lacks a direct opening answer"]
    if first.startswith(("this analysis", "the evidence suggests a nuanced", "it depends")):
        return ["Decision Brief opens with generic setup instead of an answer"]
    return []


def _practical_read_issues(body: str, contract: dict[str, Any]) -> list[str]:
    issues = []
    if _unsupported_advice_verbs(body) and not _has_practical_actions(contract):
        issues.append("Practical Read drifts into unsupported implementation advice")
    if "practical considerations" in body.lower() and "do not infer" not in body.lower() and "should not infer" not in body.lower():
        issues.append("Practical Read uses generic considerations without a non-inference boundary")
    return issues


def _why_this_read_issues(body: str) -> list[str]:
    first = _first_paragraph(body).lower()
    if first.startswith(("explain why", "the evidence details are carried")):
        return ["Why This Read contains scaffold instructions instead of reasoning"]
    return []


def _evidence_carrying_issues(body: str, contract: dict[str, Any]) -> list[str]:
    issues = []
    lowered = body.lower()
    has_owned = bool(_model_packet(contract).get("owned_evidence"))
    if has_owned and not any(term in lowered for term in ("support", "supports", "counter", "weakens", "bounded", "limited", "indirect", "direct")):
        issues.append("Evidence Carrying section does not distinguish support, counterweight, or evidence limits")
    if "evidence mix matters" in lowered:
        issues.append("Evidence Carrying opens with generic evidence-mix language")
    return issues


def _scope_issues(body: str) -> list[str]:
    lowered = body.lower()
    if "where" not in lowered and "applies" not in lowered and "exception" not in lowered and "boundary" not in lowered:
        return ["Scope section does not state where the answer applies or fails"]
    return []


def _vague_phrase_issues(text: str) -> list[str]:
    lowered = text.lower()
    return [f"section uses vague analyst phrase: {phrase}" for phrase in VAGUE_ANALYST_PHRASES if phrase in lowered]


def _unsupported_advice_verbs(text: str) -> bool:
    lowered = text.lower()
    return any(
        re.search(rf"\b{verb}\b", lowered)
        for verb in ("monitor", "prioritize", "implement", "adopt", "roll out", "optimize", "ensure")
    )


def _has_practical_actions(contract: dict[str, Any]) -> bool:
    if contract.get("practical_actions"):
        return True
    packet = _model_packet(contract)
    return bool(packet.get("owned_evidence")) and "practical read" not in str(contract.get("heading", "")).lower()


def _model_packet(contract: dict[str, Any]) -> dict[str, Any]:
    packet = contract.get("model_section_packet", {})
    return packet if isinstance(packet, dict) else {}


def _section_title(markdown: str) -> str:
    match = SECTION_RE.search(markdown)
    return match.group(1).strip() if match else ""


def _body_without_heading(markdown: str) -> str:
    return re.sub(r"^##\s+.+?\s*$", "", markdown, count=1, flags=re.MULTILINE).strip()


def _first_paragraph(text: str) -> str:
    for paragraph in re.split(r"\n\s*\n", text):
        stripped = re.sub(r"\s+", " ", paragraph).strip()
        if stripped and not stripped.startswith("**Confidence:**"):
            return stripped
    return ""


def _sections(memo: str) -> list[dict[str, str]]:
    matches = list(SECTION_RE.finditer(memo))
    sections = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(memo)
        sections.append({"title": match.group(1).strip(), "markdown": memo[match.start():end].strip()})
    return sections
