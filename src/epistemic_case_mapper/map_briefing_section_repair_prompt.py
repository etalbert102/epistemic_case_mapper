from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_section_prompt_contract import model_facing_section_contract


def section_repair_prompt(
    section: dict[str, str],
    contract: dict[str, Any],
    rejected_section: str,
    issues: list[str],
) -> str:
    model_contract = model_facing_section_contract(contract)
    feedback = "\n".join(f"- {_safe_repair_issue(issue)}" for issue in issues[:8]) or "- The section did not pass validation."
    section_guidance = _section_specific_guidance(section, issues)
    return (
        "You are correcting one rejected section of a source-grounded decision memo.\n"
        "Do not start over. Repair the rejected section below with the smallest changes needed to pass validation.\n"
        "Use only the section contract and the rejected section. Do not add new facts, sources, quantities, or claims.\n"
        "If the section drifted into advice, convert it into a bounded inference about what the source packet supports.\n"
        "If the section repeated source detail without adding section-specific value, either compress the source detail or add the section's distinct analytic move.\n"
        "If the section used vague analyst phrasing, replace it with concrete language tied to support, counterweight, scope, or missing evidence.\n"
        f"{section_guidance}"
        "Return regular Markdown only, beginning with exactly the same ## heading. Do not use JSON or a code fence.\n\n"
        "Validation failures to fix:\n"
        f"{feedback}\n\n"
        "Section contract:\n"
        f"{json.dumps(model_contract, indent=2, ensure_ascii=False)}\n\n"
        "Rejected section to correct. The text under Section to rewrite is the rejected section:\n"
        "Section to rewrite:\n"
        f"{rejected_section.strip()}\n"
    )


def _section_specific_guidance(section: dict[str, str], issues: list[str]) -> str:
    title = str(section.get("title", "")).strip().lower()
    issue_text = " ".join(str(issue).lower() for issue in issues)
    if title == "practical read" and ("unsupported implementation advice" in issue_text or "generic considerations" in issue_text):
        return (
            "For Practical Read repairs, use one short paragraph plus at most three bullets framed as evidence-bounded implications, not recommendations. "
            "Do not use the phrase practical considerations. Do not use imperative advice verbs such as monitor, prioritize, implement, adopt, optimize, ensure, focus, replace, or manage. "
            "Acceptable bullet stems include: Evidence supports treating..., Evidence does not establish..., The boundary is...\n"
        )
    return ""


def _safe_repair_issue(issue: str) -> str:
    text = re.sub(r"\s+", " ", str(issue)).strip()
    if text.startswith("section repeats evidence owned by ") or text.startswith("section repeats source detail without adding "):
        return "section repeated source detail without adding this section's distinct analytic value"
    if text.startswith("section dropped required main-memo obligation:"):
        match = re.search(r"\b([a-z]+_[a-z]+_\d+)\b", text)
        return f"section dropped required main-memo obligation {match.group(1)}" if match else "section dropped a required main-memo obligation"
    if text.startswith("section rewrite introduces unsupported source label"):
        return "section introduced an unsupported source label"
    return text.split(":", 1)[0]
